from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from Bio.PDB import MMCIFParser, PDBParser, Structure

    BIOPYTHON_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without BioPython
    MMCIFParser = None  # type: ignore[assignment]
    PDBParser = None  # type: ignore[assignment]
    Structure = None  # type: ignore[assignment]
    BIOPYTHON_AVAILABLE = False

from abby_api.schemas.structures import StructureSummary, StructureValidationIssue
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

            chain_id = (line[21:22].strip() or "")
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


def summarize_structure(structure: Any, parser_name: str) -> StructureSummary:
    model_count = len(list(structure.get_models()))
    residue_counts: dict[str, int] = {}
    available_chains: list[str] = []
    warnings: list[str] = []
    warning_details: list[StructureValidationIssue] = []
    chain_residue_name_counts: dict[str, dict[str, int]] = {}
    chain_residue_class_counts: dict[str, dict[str, int]] = {}
    unsupported_residue_counts: dict[str, dict[str, int]] = {}
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

    if model_count > 1:
        warnings.append("MULTI_MODEL_INPUT")
        warning_details.append(
            StructureValidationIssue(
                code="MULTI_MODEL_INPUT",
                message="Input contains multiple models; the workflow will preserve model-level metadata.",
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

    total_residues = sum(residue_counts.values())
    return StructureSummary(
        parser_name=parser_name,
        model_count=model_count,
        available_chains=sorted(set(available_chains)),
        residue_counts=residue_counts,
        warnings=sorted(set(warnings)),
        warning_details=warning_details,
        metadata={
            "total_residues": total_residues,
            "chain_residue_name_counts": chain_residue_name_counts,
            "chain_residue_class_counts": chain_residue_class_counts,
            "global_residue_class_counts": global_residue_class_counts,
            "unsupported_residue_counts": unsupported_residue_counts,
        },
    )