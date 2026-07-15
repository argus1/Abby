from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

CDR_REGION_NAMES: tuple[str, ...] = (
    "CDR-H1",
    "CDR-H2",
    "CDR-H3",
    "CDR-L1",
    "CDR-L2",
    "CDR-L3",
)

CDR_REGION_GLOSSARY: dict[str, str] = {
    "CDR-H1": "Heavy-chain complementarity-determining region 1.",
    "CDR-H2": "Heavy-chain complementarity-determining region 2.",
    "CDR-H3": "Heavy-chain complementarity-determining region 3.",
    "CDR-L1": "Light-chain complementarity-determining region 1.",
    "CDR-L2": "Light-chain complementarity-determining region 2.",
    "CDR-L3": "Light-chain complementarity-determining region 3.",
}

CDR_RESIDUE_KEY_FORMAT = "(chain_id, auth_seq_id/label_seq_id, insertion_code)"

CDR_CHAIN_ROLE_AMBIGUOUS = "CDR_CHAIN_ROLE_AMBIGUOUS"
CDR_BOUNDARY_AMBIGUOUS = "CDR_BOUNDARY_AMBIGUOUS"
CDR_MOTIF_FALLBACK_USED = "CDR_MOTIF_FALLBACK_USED"
CDR_NUMBERING_MISSING = "CDR_NUMBERING_MISSING"

CDR_WARNING_ERROR_CODES: tuple[str, ...] = (
    CDR_CHAIN_ROLE_AMBIGUOUS,
    CDR_BOUNDARY_AMBIGUOUS,
    CDR_MOTIF_FALLBACK_USED,
    CDR_NUMBERING_MISSING,
)

CDRNumberingScheme = Literal["imgt", "kabat", "chothia", "aho", "motif_fallback"]
CDRBoundarySource = Literal["numbered", "motif_fallback", "hybrid"]
CDRBoundaryConfidence = Literal["high", "medium", "low"]


@dataclass(frozen=True, slots=True)
class _ChainResidue:
    chain_id: str
    sequence_id: int
    insertion_code: str
    residue_name: str


@dataclass(frozen=True, slots=True)
class _CDRWindow:
    scheme: CDRNumberingScheme
    source: CDRBoundarySource
    confidence: CDRBoundaryConfidence
    start_index: int
    end_index: int


_ONE_LETTER_RESIDUE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}

_H3_MOTIF = re.compile(r"C([A-Z]{4,30}?)WG[A-Z]G")


def _chain_residues_from_structure(structure: Any) -> dict[str, list[_ChainResidue]]:
    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        return {}

    residues_by_chain: dict[str, list[_ChainResidue]] = {}
    for chain in models[0].get_chains():
        chain_id = str(getattr(chain, "id", "")).strip()
        if not chain_id:
            continue

        residues: list[_ChainResidue] = []
        for residue in chain.get_residues():
            residue_id = getattr(residue, "id", None)
            if not isinstance(residue_id, tuple) or len(residue_id) < 3:
                continue
            if residue_id[0] != " ":
                continue
            try:
                sequence_id = int(residue_id[1])
            except (TypeError, ValueError):
                continue

            insertion_code = str(residue_id[2] or "").strip()
            if insertion_code in {"?", "."}:
                insertion_code = ""

            residue_name = (
                residue.get_resname() if hasattr(residue, "get_resname") else "UNK"
            )
            residues.append(
                _ChainResidue(
                    chain_id=chain_id,
                    sequence_id=sequence_id,
                    insertion_code=insertion_code,
                    residue_name=str(residue_name).strip().upper(),
                )
            )

        residues_by_chain[chain_id] = sorted(
            residues,
            key=lambda item: (item.sequence_id, item.insertion_code),
        )

    return residues_by_chain


def _to_chain_sequence(residues: list[_ChainResidue]) -> str:
    return "".join(_ONE_LETTER_RESIDUE.get(residue.residue_name, "X") for residue in residues)


def _motif_matches(sequence: str) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    for match in _H3_MOTIF.finditer(sequence):
        start = int(match.start(1))
        end = int(match.end(1)) - 1
        if start <= end:
            matches.append((start, end))
    return matches


def _heavy_chain_score(
    chain_id: str,
    residues: list[_ChainResidue],
) -> tuple[int, list[tuple[int, int]]]:
    sequence = _to_chain_sequence(residues)
    motif_windows = _motif_matches(sequence)

    score = 0
    if len(sequence) >= 90:
        score += 2
    if "C" in sequence:
        score += 1
    if "W" in sequence:
        score += 1
    if motif_windows:
        score += 3

    normalized_chain_id = chain_id.strip().upper()
    if normalized_chain_id in {"H", "VH", "HEAVY"} or normalized_chain_id.startswith("H"):
        score += 1

    return score, motif_windows


def _numbering_h3_window(residues: list[_ChainResidue]) -> _CDRWindow | None:
    # Prefer Kabat-like H3 window when available, then IMGT-like fallback.
    kabat = [
        index for index, residue in enumerate(residues) if 95 <= residue.sequence_id <= 102
    ]
    if len(kabat) >= 4:
        return _CDRWindow(
            scheme="kabat",
            source="numbered",
            confidence="high",
            start_index=min(kabat),
            end_index=max(kabat),
        )

    imgt = [index for index, residue in enumerate(residues) if 105 <= residue.sequence_id <= 117]
    if len(imgt) >= 5:
        return _CDRWindow(
            scheme="imgt",
            source="numbered",
            confidence="high",
            start_index=min(imgt),
            end_index=max(imgt),
        )
    return None


def _motif_h3_window(
    residues: list[_ChainResidue],
    motif_windows: list[tuple[int, int]],
) -> _CDRWindow | None:
    if len(motif_windows) != 1:
        return None
    start, end = motif_windows[0]
    if start < 0 or end >= len(residues):
        return None

    loop_length = (end - start) + 1
    confidence: CDRBoundaryConfidence = "medium" if 6 <= loop_length <= 20 else "low"
    return _CDRWindow(
        scheme="motif_fallback",
        source="motif_fallback",
        confidence=confidence,
        start_index=start,
        end_index=end,
    )


def _residue_key_payload(residue: _ChainResidue) -> dict[str, str]:
    return {
        "chain_id": residue.chain_id,
        "sequence_id": str(residue.sequence_id),
        "insertion_code": residue.insertion_code,
    }


def annotate_cdr_h3(structure: Any) -> dict[str, Any]:
    """Annotate CDR-H3 boundaries using numbered windows first, motif fallback second."""

    residues_by_chain = _chain_residues_from_structure(structure)
    if not residues_by_chain:
        return {
            "available": False,
            "scheme": None,
            "boundary_source": None,
            "boundary_confidence": "low",
            "selected_heavy_chain": None,
            "chains": {},
            "warnings": [CDR_CHAIN_ROLE_AMBIGUOUS, CDR_BOUNDARY_AMBIGUOUS],
        }

    heavy_scores: dict[str, int] = {}
    motif_by_chain: dict[str, list[tuple[int, int]]] = {}
    for chain_id, residues in residues_by_chain.items():
        score, motif_windows = _heavy_chain_score(chain_id, residues)
        heavy_scores[chain_id] = score
        motif_by_chain[chain_id] = motif_windows

    highest_score = max(heavy_scores.values()) if heavy_scores else 0
    top_chains = sorted(
        [chain_id for chain_id, score in heavy_scores.items() if score == highest_score]
    )

    warnings: list[str] = []
    selected_heavy_chain = top_chains[0] if highest_score >= 2 and top_chains else None
    if selected_heavy_chain is None or len(top_chains) > 1:
        warnings.append(CDR_CHAIN_ROLE_AMBIGUOUS)

    annotation_window: _CDRWindow | None = None
    if selected_heavy_chain is not None:
        residues = residues_by_chain[selected_heavy_chain]
        annotation_window = _numbering_h3_window(residues)

        if annotation_window is None:
            warnings.append(CDR_NUMBERING_MISSING)
            motif_windows = motif_by_chain[selected_heavy_chain]
            if len(motif_windows) > 1:
                warnings.append(CDR_BOUNDARY_AMBIGUOUS)
            annotation_window = _motif_h3_window(residues, motif_windows)
            if annotation_window is not None:
                warnings.append(CDR_MOTIF_FALLBACK_USED)
    else:
        warnings.append(CDR_NUMBERING_MISSING)

    chains_payload: dict[str, dict[str, Any]] = {}
    for chain_id, residues in residues_by_chain.items():
        role = "heavy" if chain_id == selected_heavy_chain else "unknown"
        confidence: CDRBoundaryConfidence = "high" if role == "heavy" else "low"
        chain_regions: dict[str, Any] = {}

        if chain_id == selected_heavy_chain and annotation_window is not None:
            selected = residues[annotation_window.start_index : annotation_window.end_index + 1]
            chain_regions["CDR-H3"] = {
                "start_index": annotation_window.start_index,
                "end_index": annotation_window.end_index,
                "length": len(selected),
                "start_residue": _residue_key_payload(selected[0]),
                "end_residue": _residue_key_payload(selected[-1]),
                "residue_keys": [_residue_key_payload(residue) for residue in selected],
            }

        chains_payload[chain_id] = {
            "role": role,
            "confidence": confidence,
            "regions": chain_regions,
            "residue_count": len(residues),
        }

    available = annotation_window is not None
    if not available:
        warnings.append(CDR_BOUNDARY_AMBIGUOUS)

    deduped_warnings = sorted(set(warnings))

    return {
        "available": available,
        "scheme": annotation_window.scheme if annotation_window is not None else None,
        "boundary_source": annotation_window.source if annotation_window is not None else None,
        "boundary_confidence": (
            annotation_window.confidence if annotation_window is not None else "low"
        ),
        "selected_heavy_chain": selected_heavy_chain,
        "chains": chains_payload,
        "warnings": deduped_warnings,
    }


def is_valid_cdr_region_name(name: str) -> bool:
    return name in CDR_REGION_NAMES
