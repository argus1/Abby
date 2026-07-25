from __future__ import annotations

from pathlib import Path

from abby_api.services.cdr_annotation import CDR_BOUNDARY_AMBIGUOUS
from abby_api.services.structure_parsing import (
    parse_structure_file,
    summarize_structure,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "validation_dataset"
    / "ANDD_pdb"
    / "CompDetRAE_edge_cases"
)


def test_insertion_code_fixture_preserves_ordered_cdr_residue_keys() -> None:
    fixture_path = FIXTURE_ROOT / "numbering_insertion_codes.mmcif"

    structure, parser_name = parse_structure_file(fixture_path, "mmcif")
    summary = summarize_structure(
        structure,
        parser_name,
        file_path=fixture_path,
        format_name="mmcif",
        prediction_mode="antibody_antigen",
    )

    h1_region = summary.metadata["cdr_annotation"]["chains"]["H"]["regions"]["CDR-H1"]
    residue_keys = h1_region["residue_keys"]
    position_31_codes = [
        key["insertion_code"] for key in residue_keys if key["sequence_id"] == "31"
    ]

    assert position_31_codes == ["", "A", "B"]


def test_discontinuous_numbering_fixture_reports_partial_cdr_map() -> None:
    fixture_path = FIXTURE_ROOT / "numbering_discontinuity_nonstandard_chain.mmcif"

    structure, parser_name = parse_structure_file(fixture_path, "mmcif")
    summary = summarize_structure(
        structure,
        parser_name,
        file_path=fixture_path,
        format_name="mmcif",
        prediction_mode="antibody_antigen",
    )

    annotation = summary.metadata["cdr_annotation"]
    heavy_chain = annotation["chains"]["X"]

    assert annotation["selected_heavy_chain"] == "X"
    assert set(heavy_chain["regions"]) == {"CDR-H1", "CDR-H3"}
    assert heavy_chain["completeness_score"] == round(2 / 3, 4)
    assert CDR_BOUNDARY_AMBIGUOUS in annotation["warnings"]
    assert "CHAIN_SEQUENCE_GAPS" in summary.warnings