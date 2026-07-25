from __future__ import annotations

from typing import Any

DNA_RESIDUE_NAMES = frozenset({"DA", "DC", "DG", "DI", "DT"})
RNA_RESIDUE_NAMES = frozenset({"A", "C", "G", "I", "U"})
PROTEIN_RESIDUE_NAMES = frozenset(
    {
        "ALA",
        "ARG",
        "ASN",
        "ASP",
        "CYS",
        "GLN",
        "GLU",
        "GLY",
        "HIS",
        "ILE",
        "LEU",
        "LYS",
        "MET",
        "PHE",
        "PRO",
        "SER",
        "THR",
        "TRP",
        "TYR",
        "VAL",
    }
)
MODIFIED_NUCLEOTIDE_TYPES = {"PSU": "rna"}


def is_canonical_nucleotide(residue_name: str) -> bool:
    normalized = residue_name.strip().upper()
    return normalized in DNA_RESIDUE_NAMES or normalized in RNA_RESIDUE_NAMES


def build_nucleic_acid_profile(structure: Any) -> dict[str, Any]:
    chain_types: dict[str, str] = {}
    canonical_nucleotide_counts: dict[str, dict[str, int]] = {}
    modified_nucleotides: list[dict[str, Any]] = []

    for chain in structure.get_chains():
        chain_id = str(chain.id or "").strip()
        if not chain_id:
            continue

        dna_count = 0
        rna_count = 0
        protein_count = 0
        nucleotide_counts: dict[str, int] = {}
        for residue in chain.get_residues():
            residue_name = residue.get_resname().strip().upper()
            if residue_name in DNA_RESIDUE_NAMES:
                dna_count += 1
                nucleotide_counts[residue_name] = nucleotide_counts.get(residue_name, 0) + 1
            elif residue_name in RNA_RESIDUE_NAMES:
                rna_count += 1
                nucleotide_counts[residue_name] = nucleotide_counts.get(residue_name, 0) + 1
            elif residue_name in PROTEIN_RESIDUE_NAMES:
                protein_count += 1
            elif residue_name in MODIFIED_NUCLEOTIDE_TYPES:
                polymer_type = MODIFIED_NUCLEOTIDE_TYPES[residue_name]
                if polymer_type == "dna":
                    dna_count += 1
                else:
                    rna_count += 1
                modified_nucleotides.append(
                    {
                        "chain_id": chain_id,
                        "residue_name": residue_name,
                        "sequence_id": int(residue.id[1]),
                        "polymer_type": polymer_type,
                    }
                )

        if dna_count and not rna_count and not protein_count:
            chain_types[chain_id] = "dna"
        elif rna_count and not dna_count and not protein_count:
            chain_types[chain_id] = "rna"
        elif dna_count or rna_count:
            chain_types[chain_id] = "mixed"
        elif protein_count:
            chain_types[chain_id] = "protein"
        else:
            chain_types[chain_id] = "unknown"

        if nucleotide_counts:
            canonical_nucleotide_counts[chain_id] = dict(sorted(nucleotide_counts.items()))

    nucleic_acid_chains = sorted(
        chain_id
        for chain_id, chain_type in chain_types.items()
        if chain_type in {"dna", "rna", "mixed"}
    )
    return {
        "available": bool(nucleic_acid_chains),
        "chain_types": dict(sorted(chain_types.items())),
        "nucleic_acid_chains": nucleic_acid_chains,
        "canonical_nucleotide_counts": dict(sorted(canonical_nucleotide_counts.items())),
        "modified_nucleotides": modified_nucleotides,
    }
