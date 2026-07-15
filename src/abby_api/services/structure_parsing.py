from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from Bio.PDB import MMCIFIO, MMCIFParser, PDBParser, Structure
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict

    BIOPYTHON_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without BioPython
    MMCIFParser = None  # type: ignore[assignment]
    MMCIFIO = None  # type: ignore[assignment]
    PDBParser = None  # type: ignore[assignment]
    Structure = None  # type: ignore[assignment]
    MMCIF2Dict = None  # type: ignore[assignment]
    BIOPYTHON_AVAILABLE = False

from abby_api.schemas.structures import StructureSummary, StructureValidationIssue
from abby_api.services.cdr_annotation import annotate_cdr_h3
from abby_api.services.cdr_telemetry import record_cdr_annotation_telemetry
from abby_api.services.feature_extraction import classify_residue


@dataclass
class _SimpleResidue:
    id: tuple[str, int, str]
    _resname: str
    _atoms: list[tuple[float, float, float]]

    def get_resname(self) -> str:
        return self._resname

    def get_atoms(self):
        return iter(self._atoms)


@dataclass
class _SimpleChain:
    id: str
    _residues: list[_SimpleResidue]

    def get_residues(self):
        return iter(self._residues)


@dataclass
class _SimpleModel:
    id: int
    _chains: list[_SimpleChain]

    def get_chains(self):
        return iter(self._chains)


@dataclass
class _SimpleStructure:
    id: str
    _models: list[_SimpleModel]

    def get_models(self):
        return iter(self._models)

    def get_chains(self):
        for model in self._models:
            for chain in model.get_chains():
                yield chain


def _parse_pdb_without_biopython(file_path: Path) -> _SimpleStructure:
    model_maps: dict[
        int,
        dict[str, dict[tuple[str, int, str], dict[str, Any]]],
    ] = {}
    current_model = 0

    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            record = line[:6].strip().upper()
            if record == "MODEL":
                try:
                    current_model = int(line[10:14].strip() or "0")
                except ValueError:
                    current_model = 0
                model_maps.setdefault(current_model, {})
                continue
            if record in {"ENDMDL", "END"}:
                continue
            if record not in {"ATOM", "HETATM"}:
                continue

            chain_id = line[21:22].strip() or ""
            resname = line[17:20].strip().upper() or "UNK"
            residue_number_text = line[22:26].strip()
            insertion_code = line[26:27].strip() or " "

            try:
                residue_number = int(residue_number_text)
            except ValueError:
                continue

            hetflag = " " if record == "ATOM" else f"H_{resname}"
            residue_id = (hetflag, residue_number, insertion_code)

            model_map = model_maps.setdefault(current_model, {})
            chain_map = model_map.setdefault(chain_id, {})
            record_entry = chain_map.setdefault(residue_id, {"resname": resname, "atoms": []})

            try:
                x = float(line[30:38].strip())
                y = float(line[38:46].strip())
                z = float(line[46:54].strip())
            except ValueError:
                continue
            record_entry["atoms"].append((x, y, z))

    models: list[_SimpleModel] = []
    for model_id, chain_map in sorted(model_maps.items(), key=lambda item: item[0]):
        chains: list[_SimpleChain] = []
        for chain_id, residues in sorted(chain_map.items(), key=lambda item: item[0]):
            simple_residues = [
                _SimpleResidue(
                    id=residue_id,
                    _resname=entry["resname"],
                    _atoms=entry["atoms"],
                )
                for residue_id, entry in sorted(residues.items(), key=lambda item: item[0])
            ]
            chains.append(_SimpleChain(id=chain_id, _residues=simple_residues))
        models.append(_SimpleModel(id=model_id, _chains=chains))

    if not models:
        models = [_SimpleModel(id=0, _chains=[])]

    return _SimpleStructure(id=file_path.stem, _models=models)


def select_parser(format_name: str):
    if not BIOPYTHON_AVAILABLE:
        return None, "PDBParser" if format_name == "pdb" else "MMCIFParser"
    if format_name == "mmcif":
        return MMCIFParser(QUIET=True), "MMCIFParser"
    return PDBParser(QUIET=True), "PDBParser"


def parse_structure_file(file_path: Path, format_name: str) -> tuple[Any, str]:
    parser, parser_name = select_parser(format_name)
    if parser is None:
        if format_name != "pdb":
            raise RuntimeError("BioPython is required for mmCIF parsing in this environment.")
        return _parse_pdb_without_biopython(file_path), parser_name
    structure = parser.get_structure(file_path.stem, str(file_path))
    return structure, parser_name


def convert_pdb_to_mmcif(file_path: Path, destination: Path) -> Path:
    if not BIOPYTHON_AVAILABLE or PDBParser is None or MMCIFIO is None:
        raise RuntimeError("BioPython is required for PDB to mmCIF conversion.")
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure(file_path.stem, str(file_path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = MMCIFIO()
    writer.set_structure(structure)
    writer.save(str(destination))
    return destination


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _extract_mmcif_connectivity(file_path: Path) -> dict[str, Any]:
    if not BIOPYTHON_AVAILABLE or MMCIF2Dict is None:
        return {
            "available": False,
            "reason": "BIOPYTHON_UNAVAILABLE",
            "connection_count": 0,
            "disulfide_count": 0,
            "glycan_link_count": 0,
            "connections": [],
            "disulfide_connections": [],
            "glycan_connections": [],
        }

    try:
        mmcif_dict = MMCIF2Dict(str(file_path))
    except Exception as exc:  # pragma: no cover - defensive for malformed mmCIF
        return {
            "available": False,
            "reason": "MMCIF2DICT_PARSE_FAILED",
            "error": str(exc),
            "connection_count": 0,
            "disulfide_count": 0,
            "glycan_link_count": 0,
            "connections": [],
            "disulfide_connections": [],
            "glycan_connections": [],
        }

    connection_types = _as_list(mmcif_dict.get("_struct_conn.conn_type_id"))
    connection_ids = _as_list(mmcif_dict.get("_struct_conn.id"))
    ptnr1_asym = _as_list(mmcif_dict.get("_struct_conn.ptnr1_label_asym_id"))
    ptnr1_comp = _as_list(mmcif_dict.get("_struct_conn.ptnr1_label_comp_id"))
    ptnr1_seq = _as_list(mmcif_dict.get("_struct_conn.ptnr1_label_seq_id"))
    ptnr1_atom = _as_list(mmcif_dict.get("_struct_conn.ptnr1_label_atom_id"))
    ptnr2_asym = _as_list(mmcif_dict.get("_struct_conn.ptnr2_label_asym_id"))
    ptnr2_comp = _as_list(mmcif_dict.get("_struct_conn.ptnr2_label_comp_id"))
    ptnr2_seq = _as_list(mmcif_dict.get("_struct_conn.ptnr2_label_seq_id"))
    ptnr2_atom = _as_list(mmcif_dict.get("_struct_conn.ptnr2_label_atom_id"))

    glycan_residue_names = {
        "NAG",
        "BMA",
        "MAN",
        "FUC",
        "GAL",
        "GLC",
        "SIA",
        "NDG",
        "BGC",
        "FCA",
    }

    records: list[dict[str, Any]] = []
    for index, conn_type in enumerate(connection_types):
        conn_type_norm = conn_type.strip().lower()
        p1_comp = ptnr1_comp[index].strip().upper() if index < len(ptnr1_comp) else ""
        p2_comp = ptnr2_comp[index].strip().upper() if index < len(ptnr2_comp) else ""

        is_disulfide = conn_type_norm == "disulf"
        is_glycan_link = conn_type_norm in {"covale", "modres"} and (
            p1_comp in glycan_residue_names or p2_comp in glycan_residue_names
        )

        record = {
            "id": connection_ids[index] if index < len(connection_ids) else f"conn_{index + 1}",
            "type": conn_type,
            "partner_1": {
                "chain_id": ptnr1_asym[index] if index < len(ptnr1_asym) else "",
                "residue_name": p1_comp,
                "sequence_id": ptnr1_seq[index] if index < len(ptnr1_seq) else "",
                "atom_id": ptnr1_atom[index] if index < len(ptnr1_atom) else "",
            },
            "partner_2": {
                "chain_id": ptnr2_asym[index] if index < len(ptnr2_asym) else "",
                "residue_name": p2_comp,
                "sequence_id": ptnr2_seq[index] if index < len(ptnr2_seq) else "",
                "atom_id": ptnr2_atom[index] if index < len(ptnr2_atom) else "",
            },
            "is_disulfide": is_disulfide,
            "is_glycan_link": is_glycan_link,
        }
        records.append(record)

    disulfides = [record for record in records if record["is_disulfide"]]
    glycans = [record for record in records if record["is_glycan_link"]]
    return {
        "available": True,
        "source": "_struct_conn",
        "connection_count": len(records),
        "disulfide_count": len(disulfides),
        "glycan_link_count": len(glycans),
        "connections": records,
        "disulfide_connections": disulfides,
        "glycan_connections": glycans,
    }


def summarize_structure(
    structure: Any,
    parser_name: str,
    *,
    file_path: Path | None = None,
    format_name: str | None = None,
    prediction_mode: str | None = None,
) -> StructureSummary:
    model_count = len(list(structure.get_models()))
    residue_counts: dict[str, int] = {}
    available_chains: list[str] = []
    warnings: list[str] = []
    warning_details: list[StructureValidationIssue] = []
    chain_residue_name_counts: dict[str, dict[str, int]] = {}
    chain_residue_class_counts: dict[str, dict[str, int]] = {}
    unsupported_residue_counts: dict[str, dict[str, int]] = {}
    chain_gap_details: dict[str, list[dict[str, int]]] = {}
    global_residue_class_counts: dict[str, int] = {
        "charged": 0,
        "polar": 0,
        "apolar": 0,
        "aromatic": 0,
        "other": 0,
    }

    for chain in structure.get_chains():
        chain_id = (chain.id or "").strip()
        if not chain_id:
            warnings.append("MISSING_CHAIN_ID")
            continue
        available_chains.append(chain_id)
        residue_count = 0
        residue_name_counts: dict[str, int] = {}
        unsupported_counts_for_chain: dict[str, int] = {}
        observed_residue_numbers: set[int] = set()
        residue_class_counts: dict[str, int] = {
            "charged": 0,
            "polar": 0,
            "apolar": 0,
            "aromatic": 0,
            "other": 0,
        }

        for residue in chain.get_residues():
            if residue.id[0] != " ":
                continue
            residue_count += 1
            observed_residue_numbers.add(int(residue.id[1]))
            residue_name = residue.get_resname().strip().upper()
            residue_name_counts[residue_name] = residue_name_counts.get(residue_name, 0) + 1
            residue_class = classify_residue(residue_name)
            residue_class_counts[residue_class] += 1
            global_residue_class_counts[residue_class] += 1
            if residue_class == "other":
                unsupported_counts_for_chain[residue_name] = (
                    unsupported_counts_for_chain.get(residue_name, 0) + 1
                )

        residue_counts[chain_id] = residue_count
        chain_residue_name_counts[chain_id] = residue_name_counts
        chain_residue_class_counts[chain_id] = residue_class_counts
        if unsupported_counts_for_chain:
            unsupported_residue_counts[chain_id] = unsupported_counts_for_chain

        if observed_residue_numbers:
            sorted_numbers = sorted(observed_residue_numbers)
            gaps_for_chain: list[dict[str, int]] = []
            for prev_number, next_number in zip(sorted_numbers, sorted_numbers[1:]):
                if next_number - prev_number <= 1:
                    continue
                gaps_for_chain.append(
                    {
                        "from_residue": prev_number,
                        "to_residue": next_number,
                        "missing_residue_count": next_number - prev_number - 1,
                    }
                )
            if gaps_for_chain:
                chain_gap_details[chain_id] = gaps_for_chain

    if model_count > 1:
        warnings.append("MULTI_MODEL_INPUT")
        warning_details.append(
            StructureValidationIssue(
                code="MULTI_MODEL_INPUT",
                message=(
                    "Input contains multiple models; the workflow will preserve "
                    "model-level metadata."
                ),
                details={"model_count": model_count},
            )
        )

    if unsupported_residue_counts:
        warnings.append("UNSUPPORTED_RESIDUE")
        warning_details.append(
            StructureValidationIssue(
                code="UNSUPPORTED_RESIDUE",
                message="Structure includes residues outside the canonical residue class map.",
                details={"unsupported_residue_counts": unsupported_residue_counts},
            )
        )

    if chain_gap_details:
        warnings.append("CHAIN_SEQUENCE_GAPS")
        warning_details.append(
            StructureValidationIssue(
                code="CHAIN_SEQUENCE_GAPS",
                message=(
                    "One or more chains include sequence index discontinuities "
                    "that may indicate missing residues."
                ),
                details={"chain_gap_details": chain_gap_details},
            )
        )

    pdb2gmx_preflight_issues: list[dict[str, Any]] = []
    if unsupported_residue_counts:
        pdb2gmx_preflight_issues.append(
            {
                "code": "NON_STANDARD_RESIDUES",
                "message": (
                    "Non-standard residues may require parameterization or "
                    "renaming before pdb2gmx."
                ),
                "details": {"unsupported_residue_counts": unsupported_residue_counts},
            }
        )
    if chain_gap_details:
        pdb2gmx_preflight_issues.append(
            {
                "code": "CHAIN_SEQUENCE_GAPS",
                "message": (
                    "Detected residue numbering gaps that may correspond to "
                    "unresolved segments."
                ),
                "details": {"chain_gap_details": chain_gap_details},
            }
        )

    if pdb2gmx_preflight_issues:
        warnings.append("PDB2GMX_PRECHECK_ISSUES")
        warning_details.append(
            StructureValidationIssue(
                code="PDB2GMX_PRECHECK_ISSUES",
                message="MD preflight checks found issues that may require cleanup before pdb2gmx.",
                details={"issues": pdb2gmx_preflight_issues},
            )
        )

    total_residues = sum(residue_counts.values())
    metadata: dict[str, Any] = {
        "total_residues": total_residues,
        "chain_residue_name_counts": chain_residue_name_counts,
        "chain_residue_class_counts": chain_residue_class_counts,
        "global_residue_class_counts": global_residue_class_counts,
        "unsupported_residue_counts": unsupported_residue_counts,
        "chain_gap_details": chain_gap_details,
        "md_preflight": {
            "ready_for_pdb2gmx": not pdb2gmx_preflight_issues,
            "issues": pdb2gmx_preflight_issues,
        },
    }

    if format_name == "mmcif" and file_path is not None:
        metadata["connectivity"] = _extract_mmcif_connectivity(file_path)

    if prediction_mode == "antibody_antigen":
        cdr_annotation = annotate_cdr_h3(structure)
        metadata["cdr_annotation"] = cdr_annotation
        record_cdr_annotation_telemetry(cdr_annotation)

        for warning_code in cdr_annotation.get("warnings", []):
            warning_code_text = str(warning_code).strip()
            if not warning_code_text:
                continue
            warnings.append(warning_code_text)
            warning_details.append(
                StructureValidationIssue(
                    code=warning_code_text,
                    message="CDR-H3 annotation emitted a typed bookkeeping warning.",
                    details={
                        "cdr_annotation_available": bool(cdr_annotation.get("available", False)),
                        "selected_heavy_chain": cdr_annotation.get("selected_heavy_chain"),
                        "scheme": cdr_annotation.get("scheme"),
                    },
                )
            )

    return StructureSummary(
        parser_name=parser_name,
        model_count=model_count,
        available_chains=sorted(set(available_chains)),
        residue_counts=residue_counts,
        warnings=sorted(set(warnings)),
        warning_details=warning_details,
        metadata=metadata,
    )
