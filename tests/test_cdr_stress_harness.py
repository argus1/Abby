from __future__ import annotations

import pytest

from abby_api.services.cdr_stress_harness import (
    parse_cdr_mutation_spec,
    run_cdr_mutation_stress_batch,
)


def test_parse_cdr_point_mutation_spec() -> None:
    spec = parse_cdr_mutation_spec("H:95A:C>W")

    assert spec.chain_id == "H"
    assert spec.start_seq_id == 95
    assert spec.end_seq_id == 95
    assert spec.insertion_code == "A"
    assert spec.from_residue == "C"
    assert spec.to_residue == "W"
    assert spec.mode == "point_substitution"


def test_parse_cdr_range_mutation_rejects_descending_range() -> None:
    with pytest.raises(ValueError, match="CDR_MUTATION_RANGE_INVALID"):
        parse_cdr_mutation_spec("H:102-95:W")


def test_run_cdr_mutation_stress_batch_reports_success_failure_rollup() -> None:
    summary = run_cdr_mutation_stress_batch([
        "H:95A:C>W",
        "H:95-97:W",
        "H:102-95:W",
    ])

    assert summary.total_specs == 3
    assert summary.parsed_specs == 2
    assert summary.failed_specs == 1
    assert summary.results[0].status == "parsed"
    assert summary.results[1].status == "parsed"
    assert summary.results[2].status == "failed"
    assert "CDR_MUTATION_RANGE_INVALID" in summary.results[2].error
