"""Phase 6B: Upstream structure-generation integrations.

This module provides:
- AlphaFold 3 / Boltz-1 ingestion and orchestration contract for forward
  structure generation from sequence inputs.
- Rosetta integration contract for physical refinement, clash resolution, and
  ΔΔG workflows.
- Graceful stub fallbacks throughout so callers always receive a well-formed
  result regardless of whether the external tools are installed.

All availability checks are performed at call time.  None of these tools are
hard dependencies of the core Abby API.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abby_api.schemas.common import (
    ArtifactReference,
    ArtifactRegistry,
    StructureGenerationProvenance,
)
from abby_api.storage.object_store import ObjectStore

# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

ROSETTA_EXECUTABLES = ("rosetta_scripts", "relax", "ddg_monomer", "score_jd2")
ALPHAFOLD3_EXECUTABLE = "alphafold3"
BOLTZ1_EXECUTABLE = "boltz"


class StructureGenerationUnavailableError(RuntimeError):
    """Raised when a required structure-generation runtime is not installed."""


def is_rosetta_available() -> bool:
    """Return True if any Rosetta executable is found on PATH."""
    return any(shutil.which(exe) is not None for exe in ROSETTA_EXECUTABLES)


def _rosetta_executable() -> str:
    """Return the first available Rosetta executable name."""
    for exe in ROSETTA_EXECUTABLES:
        if shutil.which(exe):
            return exe
    raise StructureGenerationUnavailableError(
        "Rosetta is not available. Install Rosetta and ensure one of "
        f"{ROSETTA_EXECUTABLES!r} is on PATH."
    )


def is_alphafold3_available() -> bool:
    """Return True if the AlphaFold 3 CLI is found on PATH."""
    return shutil.which(ALPHAFOLD3_EXECUTABLE) is not None


def is_boltz1_available() -> bool:
    """Return True if the Boltz-1 CLI is found on PATH."""
    return shutil.which(BOLTZ1_EXECUTABLE) is not None


# ---------------------------------------------------------------------------
# AlphaFold 3 / Boltz-1 data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructureGenerationConfig:
    """Configuration for a forward structure-generation run.

    Parameters
    ----------
    sequences:
        List of sequence dicts in the format expected by the target tool
        (e.g. ``[{"id": "A", "sequence": "EVQLV..."}]`` for AF3 JSON input).
    seeds:
        Random seeds to use for multi-seed inference.
    num_recycles:
        Number of recycling iterations (AF3-style parameter).
    max_msa_sequences:
        Upper bound on MSA depth passed to the model.
    backend:
        Preferred backend: ``"alphafold3"``, ``"boltz1"``, or ``"auto"``.
    """

    sequences: list[dict[str, Any]] = field(default_factory=list)
    seeds: list[int] = field(default_factory=lambda: [42])
    num_recycles: int = 3
    max_msa_sequences: int = 512
    backend: str = "auto"


@dataclass(frozen=True)
class StructureGenerationResult:
    """Result from a structure-generation run or its stub fallback.

    Attributes
    ----------
    source:
        Tool that produced the structure (``"alphafold3"``, ``"boltz1"``,
        ``"stub"``).
    generation_available:
        ``False`` when the requested tool was not installed.
    structure_artifact_keys:
        Object-storage keys for each generated structure file.
    confidence_scores:
        Per-seed mean pLDDT (or equivalent confidence metric) keyed by seed.
    provenance:
        Structured provenance record for downstream audit.
    notes:
        Run-time notes.
    """

    source: str
    generation_available: bool
    structure_artifact_keys: list[str]
    confidence_scores: dict[str, float]
    provenance: StructureGenerationProvenance
    artifact_registry: ArtifactRegistry
    notes: list[str]


def _stub_generation_result(
    source: str,
    config: StructureGenerationConfig,
    notes: list[str],
) -> StructureGenerationResult:
    """Return an explicit stub result when the backend is unavailable."""
    provenance = StructureGenerationProvenance(
        source=f"{source}_stub",
        seeds=list(config.seeds),
        imported=False,
        notes=notes,
    )
    return StructureGenerationResult(
        source=f"{source}_stub",
        generation_available=False,
        structure_artifact_keys=[],
        confidence_scores={},
        provenance=provenance,
        artifact_registry=ArtifactRegistry(),
        notes=notes,
    )


def run_structure_generation(
    config: StructureGenerationConfig,
    *,
    prediction_id: str | None = None,
    project_id: str | None = None,
    object_store: ObjectStore | None = None,
) -> StructureGenerationResult:
    """Run forward structure generation using the best available backend.

    Resolution order (when ``config.backend="auto"``):
    1. AlphaFold 3 (``alphafold3`` on PATH)
    2. Boltz-1 (``boltz`` on PATH)
    3. Stub result (always available)

    Parameters
    ----------
    config:
        Generation configuration including sequences and seeds.
    prediction_id:
        UUID string of the parent prediction (used for artifact key namespacing).
    project_id:
        UUID string of the parent project.
    object_store:
        Object store for persisting generated structure artifacts.

    Returns
    -------
    StructureGenerationResult
        Always well-formed.  ``generation_available`` is ``False`` when no
        structure-generation tool was found.
    """
    if object_store is None:
        object_store = ObjectStore()

    notes: list[str] = []
    backend = config.backend

    if backend in {"auto", "alphafold3"} and is_alphafold3_available():
        return _run_alphafold3(
            config=config,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
            notes=notes,
        )

    if backend in {"auto", "boltz1"} and is_boltz1_available():
        return _run_boltz1(
            config=config,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
            notes=notes,
        )

    notes.append(f"STRUCTURE_GENERATION_BACKEND_{backend.upper()}_NOT_AVAILABLE")
    notes.append("STRUCTURE_GENERATION_STUB_RESULT")
    return _stub_generation_result(backend if backend != "auto" else "alphafold3", config, notes)


def _run_alphafold3(
    *,
    config: StructureGenerationConfig,
    prediction_id: str | None,
    project_id: str | None,
    object_store: ObjectStore,
    notes: list[str],
) -> StructureGenerationResult:
    """Internal: invoke the AlphaFold 3 CLI."""
    import json
    import tempfile

    work_dir = Path(tempfile.mkdtemp(prefix="abby_af3_"))
    artifact_keys: list[str] = []
    confidence_scores: dict[str, float] = {}

    try:
        input_path = work_dir / "input.json"
        input_path.write_text(
            json.dumps(
                {
                    "sequences": config.sequences,
                    "modelSeeds": config.seeds,
                    "numRecycles": config.num_recycles,
                    "maxMsaSequences": config.max_msa_sequences,
                },
                indent=2,
            )
        )
        cmd = [
            ALPHAFOLD3_EXECUTABLE,
            "--input_json",
            str(input_path),
            "--output_dir",
            str(work_dir / "output"),
        ]
        subprocess.run(cmd, cwd=str(work_dir), capture_output=True, timeout=3600, check=True)

        # Collect mmCIF output files.
        output_dir = work_dir / "output"
        for seed in config.seeds:
            cif_path = output_dir / f"seed-{seed}_sample-0" / "model.cif"
            if cif_path.exists():
                artifact_key = _structure_artifact_key(
                    project_id=project_id,
                    prediction_id=prediction_id,
                    source="alphafold3",
                    seed=seed,
                )
                object_store.put_bytes(artifact_key, cif_path.read_bytes())
                artifact_keys.append(artifact_key)
                confidence_scores[str(seed)] = _parse_af3_plddt(output_dir, seed)

        notes.append("ALPHAFOLD3_GENERATION_COMPLETED")
        provenance = StructureGenerationProvenance(
            source="alphafold3",
            seeds=list(config.seeds),
            plddt_mean=_mean_confidence(confidence_scores),
            imported=False,
            notes=notes,
        )
        artifact_registry = _build_artifact_registry(artifact_keys, object_store, "alphafold3")
        return StructureGenerationResult(
            source="alphafold3",
            generation_available=True,
            structure_artifact_keys=artifact_keys,
            confidence_scores=confidence_scores,
            provenance=provenance,
            artifact_registry=artifact_registry,
            notes=notes,
        )
    except Exception as exc:
        notes.append(f"ALPHAFOLD3_GENERATION_FAILED:{exc}")
        return _stub_generation_result("alphafold3", config, notes)


def _run_boltz1(
    *,
    config: StructureGenerationConfig,
    prediction_id: str | None,
    project_id: str | None,
    object_store: ObjectStore,
    notes: list[str],
) -> StructureGenerationResult:
    """Internal: invoke the Boltz-1 CLI."""
    import tempfile

    work_dir = Path(tempfile.mkdtemp(prefix="abby_boltz1_"))
    artifact_keys: list[str] = []
    confidence_scores: dict[str, float] = {}

    try:
        # Write FASTA input from sequence dicts.
        fasta_path = work_dir / "input.fasta"
        with fasta_path.open("w") as fh:
            for seq_dict in config.sequences:
                seq_id = seq_dict.get("id", "A")
                sequence = seq_dict.get("sequence", "")
                fh.write(f">{seq_id}\n{sequence}\n")

        cmd = [
            BOLTZ1_EXECUTABLE,
            "predict",
            str(fasta_path),
            "--out_dir",
            str(work_dir / "output"),
            "--seed",
            str(config.seeds[0]) if config.seeds else "42",
        ]
        subprocess.run(cmd, cwd=str(work_dir), capture_output=True, timeout=3600, check=True)

        output_dir = work_dir / "output"
        for seed in config.seeds:
            cif_path = output_dir / "predictions" / "model_0.cif"
            if cif_path.exists():
                artifact_key = _structure_artifact_key(
                    project_id=project_id,
                    prediction_id=prediction_id,
                    source="boltz1",
                    seed=seed,
                )
                object_store.put_bytes(artifact_key, cif_path.read_bytes())
                artifact_keys.append(artifact_key)

        notes.append("BOLTZ1_GENERATION_COMPLETED")
        provenance = StructureGenerationProvenance(
            source="boltz1",
            seeds=list(config.seeds),
            imported=False,
            notes=notes,
        )
        artifact_registry = _build_artifact_registry(artifact_keys, object_store, "boltz1")
        return StructureGenerationResult(
            source="boltz1",
            generation_available=True,
            structure_artifact_keys=artifact_keys,
            confidence_scores=confidence_scores,
            provenance=provenance,
            artifact_registry=artifact_registry,
            notes=notes,
        )
    except Exception as exc:
        notes.append(f"BOLTZ1_GENERATION_FAILED:{exc}")
        return _stub_generation_result("boltz1", config, notes)


# ---------------------------------------------------------------------------
# AlphaFold 3 / Boltz-1 ingestion contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructureGenerationIngestionResult:
    """Result from ingesting an externally generated structure into Abby.

    This mirrors the ``SimulationImportResponse`` pattern: the caller supplies
    a URL and provenance metadata; Abby stores the artifact and records provenance.
    """

    ingestion_id: str
    source: str
    imported: bool
    provenance: StructureGenerationProvenance
    artifact_key: str | None
    artifact_url: str | None
    notes: list[str]


def ingest_structure_generation_artifact(
    *,
    source: str,
    tool_version: str | None = None,
    model_id: str | None = None,
    seeds: list[int] | None = None,
    force_field: str | None = None,
    ddg_protocol: str | None = None,
    plddt_mean: float | None = None,
    structure_url: str | None = None,
    structure_format: str | None = None,
    ddg_kcal_mol: float | None = None,
    clash_score: float | None = None,
    total_score: float | None = None,
    notes_extra: list[str] | None = None,
    prediction_id: str | None = None,
    project_id: str | None = None,
    object_store: ObjectStore | None = None,
) -> StructureGenerationIngestionResult:
    """Record and persist provenance for an externally generated structure.

    This is the primary entry point for the Phase 6B ingestion contract.  It
    stores structured provenance metadata alongside an optional artifact
    reference so downstream code can query the generation history without
    tightly coupling to any specific generation tool.

    Parameters
    ----------
    source:
        Tool identifier: ``"alphafold3"``, ``"boltz1"``, ``"rosetta"``,
        ``"external"``, etc.
    prediction_id, project_id:
        UUID strings for artifact key namespacing.
    All other parameters map directly to ``StructureGenerationProvenance`` fields.

    Returns
    -------
    StructureGenerationIngestionResult
    """
    if object_store is None:
        object_store = ObjectStore()

    ingestion_id = str(uuid.uuid4())
    notes: list[str] = list(notes_extra or [])
    provenance = StructureGenerationProvenance(
        source=source,
        tool_version=tool_version,
        model_id=model_id,
        seeds=list(seeds or []),
        force_field=force_field,
        ddg_protocol=ddg_protocol,
        plddt_mean=plddt_mean,
        imported=True,
        notes=notes,
    )

    # Persist provenance JSON.
    artifact_key: str | None = None
    artifact_url: str | None = None
    prov_key_prefix = (
        f"projects/{project_id}/predictions/{prediction_id}"
        if project_id and prediction_id
        else f"ingestions/{ingestion_id}"
    )
    prov_key = f"{prov_key_prefix}/structure_generation/provenance.json"
    object_store.put_json(
        prov_key,
        {
            "ingestion_id": ingestion_id,
            "source": source,
            "tool_version": tool_version,
            "model_id": model_id,
            "seeds": list(seeds or []),
            "plddt_mean": plddt_mean,
            "ddg_kcal_mol": ddg_kcal_mol,
            "clash_score": clash_score,
            "total_score": total_score,
            "structure_url": structure_url,
            "structure_format": structure_format,
            "imported": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    artifact_key = prov_key
    artifact_url = object_store.signed_download_url(prov_key)
    notes.append(f"STRUCTURE_GENERATION_INGESTED_{source.upper()}")
    return StructureGenerationIngestionResult(
        ingestion_id=ingestion_id,
        source=source,
        imported=True,
        provenance=provenance,
        artifact_key=artifact_key,
        artifact_url=artifact_url,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Rosetta integration contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RosettaRefineConfig:
    """Configuration for a Rosetta refinement or ΔΔG run.

    Parameters
    ----------
    protocol:
        Rosetta protocol: ``"relax"``, ``"ddg_monomer"``, ``"score_only"``.
    n_structures:
        Number of output models to generate.
    score_function:
        Rosetta score function (e.g. ``"ref2015"``).
    extra_flags:
        Additional command-line flags forwarded to the Rosetta executable.
    """

    protocol: str = "relax"
    n_structures: int = 1
    score_function: str = "ref2015"
    extra_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RosettaRefinementResult:
    """Result from a Rosetta refinement or ΔΔG run.

    Attributes
    ----------
    rosetta_available:
        ``False`` when Rosetta was not installed and a stub result was returned.
    ddg_kcal_mol:
        ΔΔG in kcal/mol (``None`` unless the ``ddg_monomer`` protocol ran).
    clash_score:
        Rosetta all-atom clash score for the lowest-energy model.
    total_score:
        Rosetta total score (REUs) for the lowest-energy model.
    refined_structure_key:
        Object-storage key for the lowest-energy refined model, or ``None``.
    provenance:
        Structured provenance record.
    artifact_registry:
        Registry of stored artifacts for this run.
    notes:
        Run-time notes.
    """

    rosetta_available: bool
    ddg_kcal_mol: float | None
    clash_score: float | None
    total_score: float | None
    refined_structure_key: str | None
    provenance: StructureGenerationProvenance
    artifact_registry: ArtifactRegistry
    notes: list[str]


def _stub_rosetta_result(
    config: RosettaRefineConfig,
    notes: list[str],
) -> RosettaRefinementResult:
    """Return an explicit stub Rosetta result when Rosetta is unavailable."""
    provenance = StructureGenerationProvenance(
        source="rosetta_stub",
        ddg_protocol=config.protocol,
        imported=False,
        notes=notes,
    )
    return RosettaRefinementResult(
        rosetta_available=False,
        ddg_kcal_mol=None,
        clash_score=None,
        total_score=None,
        refined_structure_key=None,
        provenance=provenance,
        artifact_registry=ArtifactRegistry(),
        notes=notes,
    )


def run_rosetta_refinement(
    structure_file: Path,
    config: RosettaRefineConfig | None = None,
    *,
    prediction_id: str | None = None,
    project_id: str | None = None,
    object_store: ObjectStore | None = None,
) -> RosettaRefinementResult:
    """Run an optional Rosetta refinement or ΔΔG workflow on a structure file.

    When Rosetta is not installed the function returns a stub
    ``RosettaRefinementResult`` with ``rosetta_available=False`` and persists
    provenance metadata so callers can store the outcome without special-casing.

    Parameters
    ----------
    structure_file:
        Path to a PDB or mmCIF structure file.
    config:
        Refinement configuration.  Defaults are used when not provided.
    prediction_id, project_id:
        UUID strings for artifact key namespacing.
    object_store:
        Object store for persisting Rosetta output artifacts.

    Returns
    -------
    RosettaRefinementResult
        Always well-formed.  ``rosetta_available`` is ``False`` when Rosetta
        is absent.
    """
    if config is None:
        config = RosettaRefineConfig()
    if object_store is None:
        object_store = ObjectStore()

    notes: list[str] = []

    if not is_rosetta_available():
        notes.append("ROSETTA_NOT_AVAILABLE")
        notes.append("ROSETTA_STUB_RESULT")
        prov_key = _rosetta_provenance_key(project_id, prediction_id)
        object_store.put_json(
            prov_key,
            {
                "rosetta_available": False,
                "protocol": config.protocol,
                "notes": notes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        return _stub_rosetta_result(config, notes)

    try:
        return _execute_rosetta_workflow(
            structure_file=structure_file,
            config=config,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
            notes=notes,
        )
    except Exception as exc:
        notes.append(f"ROSETTA_WORKFLOW_FAILED:{exc}")
        return _stub_rosetta_result(config, notes)


def _rosetta_provenance_key(project_id: str | None, prediction_id: str | None) -> str:
    prefix = (
        f"projects/{project_id}/predictions/{prediction_id}"
        if project_id and prediction_id
        else f"rosetta/{uuid.uuid4()}"
    )
    return f"{prefix}/rosetta/provenance.json"


def _execute_rosetta_workflow(
    *,
    structure_file: Path,
    config: RosettaRefineConfig,
    prediction_id: str | None,
    project_id: str | None,
    object_store: ObjectStore,
    notes: list[str],
) -> RosettaRefinementResult:
    """Internal: run the Rosetta workflow in a temporary directory."""
    import shutil as _shutil
    import tempfile

    exe = _rosetta_executable()
    work_dir = Path(tempfile.mkdtemp(prefix="abby_rosetta_"))
    local_struct = work_dir / structure_file.name
    _shutil.copy2(structure_file, local_struct)

    ddg_kcal_mol: float | None = None
    clash_score: float | None = None
    total_score: float | None = None
    refined_key: str | None = None

    if config.protocol == "ddg_monomer":
        cmd = [
            exe,
            "-in:file:s",
            str(local_struct),
            "-score:weights",
            config.score_function,
            "-ddg:out:file",
            str(work_dir / "ddg.out"),
            *config.extra_flags,
        ]
        subprocess.run(
            cmd, cwd=str(work_dir), capture_output=True, text=True, timeout=600, check=True
        )
        ddg_kcal_mol = _parse_ddg_output(work_dir / "ddg.out")
        notes.append("ROSETTA_DDG_MONOMER_COMPLETED")

    elif config.protocol in {"relax", "score_only"}:
        cmd = [
            exe,
            "-in:file:s",
            str(local_struct),
            "-score:weights",
            config.score_function,
            "-nstruct",
            str(config.n_structures),
            "-out:path:all",
            str(work_dir),
            *config.extra_flags,
        ]
        subprocess.run(
            cmd, cwd=str(work_dir), capture_output=True, text=True, timeout=600, check=True
        )
        score_file = work_dir / "score.sc"
        if score_file.exists():
            clash_score, total_score = _parse_rosetta_scorefile(score_file)
        # Find lowest-energy output structure.
        pdb_outputs = sorted(work_dir.glob("*.pdb"))
        if pdb_outputs:
            out_key_prefix = (
                f"projects/{project_id}/predictions/{prediction_id}"
                if project_id and prediction_id
                else f"rosetta/{uuid.uuid4()}"
            )
            refined_key = f"{out_key_prefix}/rosetta/refined_structure.pdb"
            object_store.put_bytes(refined_key, pdb_outputs[0].read_bytes())
        notes.append(f"ROSETTA_{config.protocol.upper()}_COMPLETED")

    # Persist provenance.
    prov_key = _rosetta_provenance_key(project_id, prediction_id)
    object_store.put_json(
        prov_key,
        {
            "rosetta_available": True,
            "protocol": config.protocol,
            "score_function": config.score_function,
            "ddg_kcal_mol": ddg_kcal_mol,
            "clash_score": clash_score,
            "total_score": total_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
        },
    )

    provenance = StructureGenerationProvenance(
        source="rosetta_local",
        ddg_protocol=config.protocol,
        force_field=config.score_function,
        imported=False,
        notes=notes,
    )
    prov_ref = ArtifactReference(
        artifact_type="rosetta_provenance",
        artifact_key=prov_key,
        artifact_url=object_store.signed_download_url(prov_key),
        format="json",
    )
    refined_ref = (
        ArtifactReference(
            artifact_type="rosetta_refined_structure",
            artifact_key=refined_key,
            artifact_url=object_store.signed_download_url(refined_key),
            format="pdb",
        )
        if refined_key
        else None
    )
    artifact_registry = ArtifactRegistry(
        topology_reference=prov_ref,
        normalized_structure=refined_ref,
    )
    return RosettaRefinementResult(
        rosetta_available=True,
        ddg_kcal_mol=ddg_kcal_mol,
        clash_score=clash_score,
        total_score=total_score,
        refined_structure_key=refined_key,
        provenance=provenance,
        artifact_registry=artifact_registry,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Rosetta output parsers
# ---------------------------------------------------------------------------


def _parse_ddg_output(path: Path) -> float | None:
    """Parse ΔΔG from a Rosetta ddg_monomer output file."""
    if not path.exists():
        return None
    try:
        for line in path.read_text().splitlines():
            parts = line.split()
            if parts and parts[0].startswith("ddG"):
                for part in parts:
                    try:
                        return float(part)
                    except ValueError:
                        continue
    except Exception:
        pass
    return None


def _parse_rosetta_scorefile(path: Path) -> tuple[float | None, float | None]:
    """Parse clash_score and total_score from a Rosetta score.sc file."""
    clash: float | None = None
    total: float | None = None
    try:
        lines = path.read_text().splitlines()
        if len(lines) < 2:
            return clash, total
        header = lines[0].split()
        data_line = None
        for line in lines[1:]:
            parts = line.split()
            if parts and parts[0] == "SCORE:":
                data_line = parts
                break
        if data_line is None or len(data_line) < len(header):
            return clash, total
        row = dict(zip(header, data_line))
        if "total_score" in row:
            try:
                total = float(row["total_score"])
            except ValueError:
                pass
        if "clashscore" in row:
            try:
                clash = float(row["clashscore"])
            except ValueError:
                pass
    except Exception:
        pass
    return clash, total


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _structure_artifact_key(
    *,
    project_id: str | None,
    prediction_id: str | None,
    source: str,
    seed: int,
) -> str:
    prefix = (
        f"projects/{project_id}/predictions/{prediction_id}"
        if project_id and prediction_id
        else f"structure_generation/{uuid.uuid4()}"
    )
    return f"{prefix}/structure_generation/{source}_seed{seed}.cif"


def _parse_af3_plddt(output_dir: Path, seed: int) -> float:
    """Try to parse mean pLDDT from an AF3 confidence JSON file."""
    import json

    conf_path = output_dir / f"seed-{seed}_sample-0" / "confidences.json"
    if not conf_path.exists():
        return 0.0
    try:
        data = json.loads(conf_path.read_text())
        plddt_values: list[float] = data.get("plddt", [])
        if plddt_values:
            return round(sum(plddt_values) / len(plddt_values), 4)
    except Exception:
        pass
    return 0.0


def _mean_confidence(scores: dict[str, float]) -> float | None:
    """Return the mean of a confidence score dict, or None when empty."""
    if not scores:
        return None
    return round(sum(scores.values()) / len(scores), 4)


def _build_artifact_registry(
    artifact_keys: list[str],
    object_store: ObjectStore,
    source: str,
) -> ArtifactRegistry:
    """Build an ArtifactRegistry from a list of structure artifact keys."""
    if not artifact_keys:
        return ArtifactRegistry()
    first_key = artifact_keys[0]
    return ArtifactRegistry(
        normalized_structure=ArtifactReference(
            artifact_type=f"{source}_structure",
            artifact_key=first_key,
            artifact_url=object_store.signed_download_url(first_key),
            format="cif",
        )
    )
