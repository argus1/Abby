from __future__ import annotations

import pytest

from abby_api.services.cdr_stress_harness import (
    parse_cdr_mutation_spec,
    run_cdr_mutation_annotation_probe,
    run_cdr_mutation_stress_batch,
)


class _Residue:
    def __init__(self, sequence_id: int, residue_name: str, insertion_code: str = " ") -> None:
        self.id = (" ", sequence_id, insertion_code)
        self._residue_name = residue_name

    def get_resname(self) -> str:
        return self._residue_name


class _Chain:
    def __init__(self, chain_id: str, residues: list[_Residue]) -> None:
        self.id = chain_id
        self._residues = residues

    def get_residues(self):
        return iter(self._residues)


class _Model:
    def __init__(self, chains: list[_Chain]) -> None:
        self._chains = chains

    def get_chains(self):
        return iter(self._chains)


class _Structure:
    def __init__(self, chains: list[_Chain]) -> None:
        self._chains = chains

    def get_models(self):
        return iter([_Model(self._chains)])


_ONE_TO_THREE = {
    "A": "ALA",
    "C": "CYS",
    "D": "ASP",
    "E": "GLU",
    "F": "PHE",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "K": "LYS",
    "L": "LEU",
    "M": "MET",
    "N": "ASN",
    "P": "PRO",
    "Q": "GLN",
    "R": "ARG",
    "S": "SER",
    "T": "THR",
    "V": "VAL",
    "W": "TRP",
    "Y": "TYR",
}


def _chain_from_sequence(chain_id: str, start_seq_id: int, sequence: str) -> _Chain:
    residues = [
        _Residue(start_seq_id + index, _ONE_TO_THREE[code])
        for index, code in enumerate(sequence)
    ]
    return _Chain(chain_id, residues)


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


def test_mutation_probe_keeps_h3_annotation_typed_and_deterministic() -> None:
    heavy_sequence = "AAAA" + "C" + "AAAAAAAA" + "W" + "AAAAAAAAAAAAAAAAAAAA"
    structure = _Structure([_chain_from_sequence("H", 90, heavy_sequence)])

    result = run_cdr_mutation_annotation_probe(
        structure,
        mutation_specs=["H:95:A>W"],
    )

    assert result["status"] == "completed"
    assert result["applied_mutation_count"] == 1
    assert result["deterministic"] is True
    assert result["annotation"]["available"] is True
    assert result["annotation"]["boundary_confidence"] in {"high", "medium", "low"}


def test_mutation_probe_handles_malformed_spec_without_crashing() -> None:
    heavy_sequence = "AAAA" + "C" + "AAAAAAAA" + "W" + "AAAAAAAAAAAAAAAAAAAA"
    structure = _Structure([_chain_from_sequence("H", 90, heavy_sequence)])

    result = run_cdr_mutation_annotation_probe(
        structure,
        mutation_specs=["H95:C>W", "H:95:A>W"],
    )

    assert result["status"] == "completed"
    assert result["applied_mutation_count"] == 1
    assert result["failed_mutation_count"] == 1
    issue_codes = [issue["code"] for issue in result["issues"]]
    assert "CDR_MUTATION_SPEC_INVALID_FORMAT" in issue_codes
    assert result["annotation"]["available"] is True


def test_mutation_probe_applies_local_range_perturbation_resiliently() -> None:
    heavy_sequence = "AAAA" + "C" + "AAAAAAAA" + "W" + "AAAAAAAAAAAAAAAAAAAA"
    structure = _Structure([_chain_from_sequence("H", 90, heavy_sequence)])

    result = run_cdr_mutation_annotation_probe(
        structure,
        mutation_specs=["H:95-97:W"],
    )

    assert result["status"] == "completed"
    assert result["applied_mutation_count"] == 1
    assert result["failed_mutation_count"] == 0
    assert result["deterministic"] is True
    assert result["annotation"]["available"] is True
