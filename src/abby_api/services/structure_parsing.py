from __future__ import annotations

from pathlib import Path

from Bio.PDB import MMCIFParser, PDBParser, Structure

from abby_api.schemas.structures import StructureSummary
from abby_api.services.feature_extraction import classify_residue


def select_parser(format_name: str):
    if format_name == "mmcif":
        return MMCIFParser(QUIET=True), "MMCIFParser"
    return PDBParser(QUIET=True), "PDBParser"


def parse_structure_file(file_path: Path, format_name: str) -> tuple[Structure.Structure, str]:
    parser, parser_name = select_parser(format_name)
    structure = parser.get_structure(file_path.stem, str(file_path))
    return structure, parser_name


def summarize_structure(structure: Structure.Structure, parser_name: str) -> StructureSummary:
    model_count = len(list(structure.get_models()))
    residue_counts: dict[str, int] = {}
    available_chains: list[str] = []
    warnings: list[str] = []
    chain_residue_name_counts: dict[str, dict[str, int]] = {}
    chain_residue_class_counts: dict[str, dict[str, int]] = {}
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

        residue_counts[chain_id] = residue_count
        chain_residue_name_counts[chain_id] = residue_name_counts
        chain_residue_class_counts[chain_id] = residue_class_counts

    if model_count > 1:
        warnings.append("MULTI_MODEL_INPUT")

    total_residues = sum(residue_counts.values())
    return StructureSummary(
        parser_name=parser_name,
        model_count=model_count,
        available_chains=sorted(set(available_chains)),
        residue_counts=residue_counts,
        warnings=sorted(set(warnings)),
        metadata={
            "total_residues": total_residues,
            "chain_residue_name_counts": chain_residue_name_counts,
            "chain_residue_class_counts": chain_residue_class_counts,
            "global_residue_class_counts": global_residue_class_counts,
        },
    )