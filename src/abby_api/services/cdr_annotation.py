from __future__ import annotations

from typing import Literal

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


def is_valid_cdr_region_name(name: str) -> bool:
    return name in CDR_REGION_NAMES
