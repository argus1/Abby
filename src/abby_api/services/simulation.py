"""Optional GROMACS-CIF simulation execution service.

Phase 5A of the Abby roadmap: Simulation worker enablement.

This module provides:
- An optional GROMACS-CIF execution path that stays off the critical prediction path.
- Parameterization workflow hooks for non-standard residues (AMBER/Antechamber/LigParGen-style).
- Run-time simulation provenance capture and artifact persistence to object storage.

GROMACS and AMBER tools are checked at call time. If they are not available the
functions return explicit ``SimulationUnavailableError`` or stub results rather
than silently failing, so callers can branch on availability.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from abby_api.schemas.common import ArtifactReference, ArtifactRegistry, SimulationProvenance
from abby_api.storage.object_store import ObjectStore

# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

GROMACS_EXECUTABLES = ("gmx", "gmx_mpi", "gmx_d")
ANTECHAMBER_EXECUTABLE = "antechamber"
LIGPARGEN_EXECUTABLE = "ligpargen"

# Allowlist for residue names passed to external parameterization tools.
# Only alphanumeric characters and underscores, max 10 characters.
_SAFE_RESIDUE_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,10}$")


class SimulationUnavailableError(RuntimeError):
    """Raised when a required simulation runtime is not installed or reachable."""


def is_gromacs_available() -> bool:
    """Return True if any GROMACS executable is found on PATH."""
    return any(shutil.which(exe) is not None for exe in GROMACS_EXECUTABLES)


def _gromacs_executable() -> str:
    """Return the first available GROMACS executable name."""
    for exe in GROMACS_EXECUTABLES:
        if shutil.which(exe):
            return exe
    raise SimulationUnavailableError(
        "GROMACS is not available. Install GROMACS and ensure 'gmx' (or 'gmx_mpi' / 'gmx_d') "
        "is on PATH before requesting simulation-backed workflows."
    )


def is_antechamber_available() -> bool:
    """Return True if the AmberTools antechamber executable is found on PATH."""
    return shutil.which(ANTECHAMBER_EXECUTABLE) is not None


def is_ligpargen_available() -> bool:
    """Return True if the LigParGen executable is found on PATH."""
    return shutil.which(LIGPARGEN_EXECUTABLE) is not None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulationRunConfig:
    """User-specified parameters for a GROMACS simulation run.

    All fields have sensible defaults so callers only need to override what
    they care about.  This is the internal representation; the public API
    schema is ``SimulationRunRequest``.
    """

    force_field: str = "amber99sb-ildn"
    water_model: str = "tip3p"
    ionization: str = "0.15M NaCl"
    minimization_protocol: str = "steepest_descent"
    seed: int | None = None
    engine: str = "gromacs"
    engine_version: str | None = None
    max_steps: int = 500
    structure_format: str = "pdb"
    extra_grompp_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParameterizationResult:
    """Outcome of a non-standard residue parameterization attempt.

    ``available`` is False when neither antechamber nor LigParGen could be
    found; ``method`` reflects whichever tool was used (or ``"stub"`` for
    the offline fallback).
    """

    available: bool
    method: str
    residues_parameterized: list[str]
    artifact_keys: list[str]
    notes: list[str]


@dataclass(frozen=True)
class SimulationRunResult:
    """Structured result returned by a completed (or stubbed) simulation run.

    When ``gromacs_available`` is False the run did not execute but returned
    stub provenance so callers can store it without special-casing.
    """

    gromacs_available: bool
    provenance: SimulationProvenance
    artifact_registry: ArtifactRegistry
    trajectory_artifact_key: str | None
    energy_artifact_key: str | None
    notes: list[str]


# ---------------------------------------------------------------------------
# Parameterization hooks
# ---------------------------------------------------------------------------


def parameterize_non_standard_residues(
    non_standard_residues: dict[str, Any],
    *,
    work_dir: Path | None = None,
    method: str = "auto",
) -> ParameterizationResult:
    """Attempt to parameterize non-standard residues using available tools.

    Resolution order (when ``method="auto"``):
    1. Antechamber (AmberTools)
    2. LigParGen
    3. Stub (offline bookkeeping only)

    Returns a ``ParameterizationResult`` in all cases.  The stub fallback
    records which residues need parameterization without actually computing
    parameters, providing an audit trail for later manual review.

    Parameters
    ----------
    non_standard_residues:
        Mapping of residue names → per-chain counts as returned by
        ``StructureSummary.metadata["unsupported_residue_counts"]``.
    work_dir:
        Optional working directory for tool invocations.  A temporary
        directory is used when not provided.
    method:
        One of ``"auto"``, ``"antechamber"``, ``"ligpargen"``, ``"stub"``.
    """

    def _sanitize(name: str) -> str:
        if not _SAFE_RESIDUE_NAME_RE.match(name):
            raise ValueError(
                f"Residue name {name!r} contains disallowed characters. "
                "Only alphanumeric characters and underscores (max 10) are permitted."
            )
        return name

    try:
        residue_names = sorted(_sanitize(name) for name in non_standard_residues.keys())
    except ValueError as exc:
        return ParameterizationResult(
            available=False,
            method="stub",
            residues_parameterized=[],
            artifact_keys=[],
            notes=[f"PARAMETERIZATION_REJECTED_INVALID_RESIDUE_NAME:{exc}"],
        )

    if not residue_names:
        return ParameterizationResult(
            available=False,
            method="none",
            residues_parameterized=[],
            artifact_keys=[],
            notes=["NO_NON_STANDARD_RESIDUES"],
        )

    use_antechamber = method in {"auto", "antechamber"} and is_antechamber_available()
    use_ligpargen = (
        (not use_antechamber) and method in {"auto", "ligpargen"} and is_ligpargen_available()
    )

    notes: list[str] = []

    if use_antechamber:
        return _parameterize_with_antechamber(residue_names, work_dir=work_dir, notes=notes)

    if use_ligpargen:
        return _parameterize_with_ligpargen(residue_names, work_dir=work_dir, notes=notes)

    # Stub fallback: record residues that need parameterization.
    notes.append("PARAMETERIZATION_STUB_NO_TOOL_AVAILABLE")
    notes.append(f"RESIDUES_REQUIRING_PARAMETERIZATION:{','.join(residue_names)}")
    return ParameterizationResult(
        available=False,
        method="stub",
        residues_parameterized=[],
        artifact_keys=[],
        notes=notes,
    )


def _parameterize_with_antechamber(
    residue_names: list[str],
    *,
    work_dir: Path | None,
    notes: list[str],
) -> ParameterizationResult:
    """Invoke antechamber for each residue; record artifact paths."""
    import tempfile

    parameterized: list[str] = []
    artifact_keys: list[str] = []
    base_dir = work_dir or Path(tempfile.mkdtemp(prefix="abby_antechamber_"))

    for residue_name in residue_names:
        out_mol2 = base_dir / f"{residue_name}.mol2"
        cmd = [
            ANTECHAMBER_EXECUTABLE,
            "-i",
            f"{residue_name}.pdb",
            "-fi",
            "pdb",
            "-o",
            str(out_mol2),
            "-fo",
            "mol2",
            "-c",
            "bcc",
            "-s",
            "2",
        ]
        try:
            subprocess.run(cmd, cwd=str(base_dir), capture_output=True, timeout=120, check=True)
            parameterized.append(residue_name)
            artifact_keys.append(str(out_mol2))
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            notes.append(f"ANTECHAMBER_FAILED_{residue_name}:{exc}")

    notes.append("PARAMETERIZATION_METHOD_ANTECHAMBER")
    return ParameterizationResult(
        available=True,
        method="antechamber",
        residues_parameterized=parameterized,
        artifact_keys=artifact_keys,
        notes=notes,
    )


def _parameterize_with_ligpargen(
    residue_names: list[str],
    *,
    work_dir: Path | None,
    notes: list[str],
) -> ParameterizationResult:
    """Invoke LigParGen for each residue; record artifact paths."""
    import tempfile

    parameterized: list[str] = []
    artifact_keys: list[str] = []
    base_dir = work_dir or Path(tempfile.mkdtemp(prefix="abby_ligpargen_"))

    for residue_name in residue_names:
        out_itp = base_dir / f"{residue_name}.itp"
        cmd = [
            LIGPARGEN_EXECUTABLE,
            "-r",
            residue_name,
            "-o",
            str(out_itp),
        ]
        try:
            subprocess.run(cmd, cwd=str(base_dir), capture_output=True, timeout=120, check=True)
            parameterized.append(residue_name)
            artifact_keys.append(str(out_itp))
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            notes.append(f"LIGPARGEN_FAILED_{residue_name}:{exc}")

    notes.append("PARAMETERIZATION_METHOD_LIGPARGEN")
    return ParameterizationResult(
        available=True,
        method="ligpargen",
        residues_parameterized=parameterized,
        artifact_keys=artifact_keys,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# GROMACS-CIF execution path
# ---------------------------------------------------------------------------


def _gromacs_version(gmx_exe: str) -> str | None:
    """Query GROMACS for its version string."""
    try:
        result = subprocess.run(
            [gmx_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if "GROMACS version" in line:
                return line.split(":")[-1].strip()
    except Exception:
        pass
    return None


def _build_stub_run_result(
    *,
    config: SimulationRunConfig,
    notes: list[str],
    prediction_id: UUID,
    project_id: UUID,
    object_store: ObjectStore,
) -> SimulationRunResult:
    """Return a stub result when GROMACS is unavailable but persist provenance."""
    provenance = SimulationProvenance(
        source="gromacs_stub",
        imported=False,
        force_field=config.force_field,
        water_model=config.water_model,
        ionization=config.ionization,
        minimization_protocol=config.minimization_protocol,
        seed=config.seed,
        engine=config.engine,
        engine_version=None,
        notes=notes,
    )
    artifact_key = f"projects/{project_id}/predictions/{prediction_id}/simulation/provenance.json"
    object_store.put_json(
        artifact_key,
        {
            "prediction_id": str(prediction_id),
            "gromacs_available": False,
            "provenance": {
                "source": provenance.source,
                "force_field": provenance.force_field,
                "water_model": provenance.water_model,
                "ionization": provenance.ionization,
                "minimization_protocol": provenance.minimization_protocol,
                "seed": provenance.seed,
                "engine": provenance.engine,
                "notes": provenance.notes,
            },
        },
    )
    provenance_artifact = ArtifactReference(
        artifact_type="simulation_provenance",
        artifact_key=artifact_key,
        artifact_url=object_store.signed_download_url(artifact_key),
        format="json",
    )
    registry = ArtifactRegistry(topology_reference=provenance_artifact)
    return SimulationRunResult(
        gromacs_available=False,
        provenance=provenance,
        artifact_registry=registry,
        trajectory_artifact_key=None,
        energy_artifact_key=None,
        notes=notes,
    )


def run_gromacs_cif_simulation(
    structure_file: Path,
    config: SimulationRunConfig,
    *,
    prediction_id: UUID,
    project_id: UUID,
    object_store: ObjectStore | None = None,
) -> SimulationRunResult:
    """Run an optional GROMACS energy-minimization workflow on a structure file.

    This path is kept off the critical prediction flow — it is only invoked
    when a user explicitly requests simulation-backed processing via the
    ``POST /predictions/{id}/simulation:run`` endpoint.

    When GROMACS is not installed the function returns a stub
    ``SimulationRunResult`` with ``gromacs_available=False`` and persists
    provenance metadata so callers can store the outcome without special-casing.

    Parameters
    ----------
    structure_file:
        Path to an mmCIF or PDB structure file to simulate.
    config:
        Simulation parameters (force field, water model, etc.).
    prediction_id:
        UUID of the parent prediction (used for artifact key namespacing).
    project_id:
        UUID of the parent project.
    object_store:
        Object store to persist run artifacts.  A new default ``ObjectStore``
        is created when not provided.
    """
    if object_store is None:
        object_store = ObjectStore()

    notes: list[str] = []

    if not is_gromacs_available():
        notes.append("GROMACS_NOT_AVAILABLE")
        notes.append("SIMULATION_STUB_RESULT")
        return _build_stub_run_result(
            config=config,
            notes=notes,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
        )

    import tempfile

    gmx_exe = _gromacs_executable()
    engine_version = _gromacs_version(gmx_exe)
    work_dir = Path(tempfile.mkdtemp(prefix="abby_gromacs_"))

    try:
        return _execute_gromacs_workflow(
            gmx_exe=gmx_exe,
            engine_version=engine_version,
            structure_file=structure_file,
            config=config,
            work_dir=work_dir,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
            notes=notes,
        )
    except Exception as exc:
        notes.append(f"GROMACS_WORKFLOW_FAILED:{exc}")
        return _build_stub_run_result(
            config=config,
            notes=notes,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
        )


def _execute_gromacs_workflow(
    *,
    gmx_exe: str,
    engine_version: str | None,
    structure_file: Path,
    config: SimulationRunConfig,
    work_dir: Path,
    prediction_id: UUID,
    project_id: UUID,
    object_store: ObjectStore,
    notes: list[str],
) -> SimulationRunResult:
    """Internal: run the GROMACS minimization pipeline in ``work_dir``."""
    import shutil as _shutil

    # Copy the structure to the working directory.
    local_struct = work_dir / structure_file.name
    _shutil.copy2(structure_file, local_struct)

    # Generate minimal MDP file for energy minimization.
    mdp_path = work_dir / "em.mdp"
    mdp_content = (
        f"integrator = {config.minimization_protocol}\n"
        f"nsteps = {config.max_steps}\n"
        "emtol = 1000.0\n"
        "emstep = 0.01\n"
    )
    mdp_path.write_text(mdp_content)

    # pdb2gmx: generate topology.
    topol_path = work_dir / "topol.top"
    conf_path = work_dir / "conf.gro"
    pdb2gmx_cmd = [
        gmx_exe,
        "pdb2gmx",
        "-f",
        str(local_struct),
        "-o",
        str(conf_path),
        "-p",
        str(topol_path),
        "-ff",
        config.force_field,
        "-water",
        config.water_model,
        "-nointer",
    ]
    subprocess.run(pdb2gmx_cmd, cwd=str(work_dir), capture_output=True, timeout=120, check=True)

    # grompp: assemble TPR.
    tpr_path = work_dir / "em.tpr"
    grompp_cmd = [
        gmx_exe,
        "grompp",
        "-f",
        str(mdp_path),
        "-c",
        str(conf_path),
        "-p",
        str(topol_path),
        "-o",
        str(tpr_path),
        *config.extra_grompp_flags,
    ]
    subprocess.run(grompp_cmd, cwd=str(work_dir), capture_output=True, timeout=60, check=True)

    # mdrun: run energy minimization.
    em_prefix = work_dir / "em"
    mdrun_cmd = [
        gmx_exe,
        "mdrun",
        "-v",
        "-deffnm",
        str(em_prefix),
    ]
    subprocess.run(mdrun_cmd, cwd=str(work_dir), capture_output=True, timeout=600, check=True)

    # Identify output files.
    trajectory_path = work_dir / "em.trr"
    energy_path = work_dir / "em.edr"

    # Persist provenance.
    provenance = SimulationProvenance(
        source="gromacs_local",
        imported=False,
        force_field=config.force_field,
        water_model=config.water_model,
        ionization=config.ionization,
        minimization_protocol=config.minimization_protocol,
        seed=config.seed,
        engine=config.engine,
        engine_version=engine_version,
        notes=notes,
    )
    provenance_key = f"projects/{project_id}/predictions/{prediction_id}/simulation/provenance.json"
    object_store.put_json(
        provenance_key,
        {
            "prediction_id": str(prediction_id),
            "gromacs_available": True,
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": {
                "source": provenance.source,
                "force_field": provenance.force_field,
                "water_model": provenance.water_model,
                "ionization": provenance.ionization,
                "minimization_protocol": provenance.minimization_protocol,
                "seed": provenance.seed,
                "engine": provenance.engine,
                "engine_version": provenance.engine_version,
                "notes": provenance.notes,
            },
        },
    )

    # Persist trajectory if present.
    trajectory_artifact_key: str | None = None
    if trajectory_path.exists():
        trajectory_artifact_key = (
            f"projects/{project_id}/predictions/{prediction_id}/simulation/trajectory.trr"
        )
        object_store.put_bytes(trajectory_artifact_key, trajectory_path.read_bytes())

    # Persist energy file if present.
    energy_artifact_key: str | None = None
    if energy_path.exists():
        energy_artifact_key = (
            f"projects/{project_id}/predictions/{prediction_id}/simulation/energy.edr"
        )
        object_store.put_bytes(energy_artifact_key, energy_path.read_bytes())

    provenance_artifact = ArtifactReference(
        artifact_type="simulation_provenance",
        artifact_key=provenance_key,
        artifact_url=object_store.signed_download_url(provenance_key),
        format="json",
    )
    trajectory_artifact = (
        ArtifactReference(
            artifact_type="trajectory",
            artifact_key=trajectory_artifact_key,
            artifact_url=object_store.signed_download_url(trajectory_artifact_key),
            format="trr",
        )
        if trajectory_artifact_key
        else None
    )
    registry = ArtifactRegistry(
        topology_reference=provenance_artifact,
        trajectory_summary=trajectory_artifact,
    )

    notes.append("GROMACS_MINIMIZATION_COMPLETED")
    return SimulationRunResult(
        gromacs_available=True,
        provenance=provenance,
        artifact_registry=registry,
        trajectory_artifact_key=trajectory_artifact_key,
        energy_artifact_key=energy_artifact_key,
        notes=notes,
    )
