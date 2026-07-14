from __future__ import annotations

import pytest

from abby_api.schemas.structures import ChainMapping, StructureSummary, StructureValidationResult
from abby_api.services.cdr_annotation import (
    CDR_REGION_GLOSSARY,
    CDR_REGION_NAMES,
    CDR_RESIDUE_KEY_FORMAT,
    CDR_WARNING_ERROR_CODES,
    is_valid_cdr_region_name,
)
from abby_api.services.cdr_numbering import ResidueKey
from abby_api.services.feature_extraction import build_descriptor_bundle


def test_cdr_contract_region_naming_and_glossary() -> None:
    assert set(CDR_REGION_NAMES) == {"CDR-H1", "CDR-H2", "CDR-H3", "CDR-L1", "CDR-L2", "CDR-L3"}
    assert set(CDR_REGION_GLOSSARY) == set(CDR_REGION_NAMES)
    assert is_valid_cdr_region_name("CDR-H3")
    assert not is_valid_cdr_region_name("H3")


def test_cdr_contract_warning_code_taxonomy() -> None:
    assert set(CDR_WARNING_ERROR_CODES) == {
        "CDR_CHAIN_ROLE_AMBIGUOUS",
        "CDR_BOUNDARY_AMBIGUOUS",
        "CDR_MOTIF_FALLBACK_USED",
        "CDR_NUMBERING_MISSING",
    }
    assert CDR_RESIDUE_KEY_FORMAT == "(chain_id, auth_seq_id/label_seq_id, insertion_code)"


def test_residue_key_stable_format() -> None:
    key = ResidueKey.from_biopython(chain_id="H", auth_seq_id=100, insertion_code="A")
    assert key.as_tuple() == ("H", "100", "A")

    key_from_label = ResidueKey.from_biopython(chain_id="L", label_seq_id=55, insertion_code="?")
    assert key_from_label.as_tuple() == ("L", "55", "")

    with pytest.raises(ValueError):
        ResidueKey.from_biopython(chain_id="H")


def test_antibody_bookkeeping_includes_typed_numbering_gap_note() -> None:
    summary = StructureSummary(
        parser_name="PDBParser",
        model_count=1,
        available_chains=["H", "L", "A"],
        residue_counts={"H": 1, "L": 1, "A": 1},
        metadata={"total_residues": 3},
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="pdb",
        chain_groups=ChainMapping(partner_1=["H"], partner_2=["A"]),
        partner_residue_counts={"partner_1": 1, "partner_2": 1},
    )

    bundle = build_descriptor_bundle(summary, validation, "antibody_antigen")
    assert "ANTIBODY_MODE_CDR_DETECTION_PENDING" in bundle.notes
    assert "CDR_NUMBERING_MISSING" in bundle.notes
