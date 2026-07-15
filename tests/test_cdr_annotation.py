from __future__ import annotations

import pytest

from abby_api.schemas.structures import ChainMapping, StructureSummary, StructureValidationResult
from abby_api.services.cdr_annotation import (
    CDR_BOUNDARY_AMBIGUOUS,
    CDR_MOTIF_FALLBACK_USED,
    CDR_NUMBERING_MISSING,
    CDR_REGION_GLOSSARY,
    CDR_REGION_NAMES,
    CDR_RESIDUE_KEY_FORMAT,
    CDR_WARNING_ERROR_CODES,
    annotate_cdr_h3,
    is_valid_cdr_region_name,
)
from abby_api.services.cdr_numbering import ResidueKey
from abby_api.services.feature_extraction import build_descriptor_bundle


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


class _MultiModelStructure:
    def __init__(self, model_chains: list[list[_Chain]]) -> None:
        self._models = [_Model(chains) for chains in model_chains]

    def get_models(self):
        return iter(self._models)


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
    "X": "ALA",
}


def _chain_from_sequence(chain_id: str, start_seq_id: int, sequence: str) -> _Chain:
    residues = [
        _Residue(start_seq_id + index, _ONE_TO_THREE.get(code, "ALA"))
        for index, code in enumerate(sequence)
    ]
    return _Chain(chain_id, residues)


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
    assert "CDR_H3_ANNOTATED" not in bundle.notes
    assert "ANTIBODY_MODE_CDR_DETECTION_PENDING" not in bundle.notes
    assert "CDR_NUMBERING_MISSING" in bundle.notes


def test_cdr_h3_numbering_annotation_selects_heavy_chain_without_h_name() -> None:
    heavy_sequence = "AAAA" + "C" + "AAAAAAAA" + "W" + "AAAAAAAAAAAAAAAAAAAA"
    structure = _Structure(
        [
            _chain_from_sequence("X", 90, heavy_sequence),
            _chain_from_sequence("B", 1, "AAAAAAAAAAAAAAAA"),
        ]
    )

    annotation = annotate_cdr_h3(structure)

    assert annotation["available"] is True
    assert annotation["selected_heavy_chain"] == "X"
    assert annotation["scheme"] == "kabat"
    assert annotation["boundary_source"] == "numbered"
    assert annotation["boundary_confidence"] == "high"
    assert annotation["chains"]["X"]["regions"]["CDR-H3"]["length"] >= 4
    assert annotation["quality_baseline"]["available"] is True
    assert annotation["quality_baseline"]["predicted_confidence_class"] == "medium"
    assert annotation["quality_baseline"]["model_contract"]["contract_version"] == (
        "cdr_boundary_quality_contract_v1"
    )
    assert annotation["quality_baseline"]["model_contract"]["feature_schema_version"] == (
        "cdr_boundary_quality_features_v1"
    )


def test_cdr_h3_motif_fallback_annotation_records_typed_warning() -> None:
    structure = _Structure([_chain_from_sequence("Z", 1, "AAAAACAAAAAWGQGAAAAA")])

    annotation = annotate_cdr_h3(structure)

    assert annotation["available"] is True
    assert annotation["scheme"] == "motif_fallback"
    assert annotation["boundary_source"] == "motif_fallback"
    assert CDR_NUMBERING_MISSING in annotation["warnings"]
    assert CDR_MOTIF_FALLBACK_USED in annotation["warnings"]
    assert annotation["quality_baseline"]["drift_flag"] is True
    assert "FALLBACK_BOUNDARY_SOURCE" in annotation["quality_baseline"]["drift_reason_codes"]


def test_cdr_h3_ambiguous_motif_returns_boundary_ambiguity_warning() -> None:
    structure = _Structure([_chain_from_sequence("Q", 1, "ACAAAAAWGQGAAACGGGGGWGAG")])

    annotation = annotate_cdr_h3(structure)

    assert annotation["available"] is False
    assert CDR_BOUNDARY_AMBIGUOUS in annotation["warnings"]
    assert annotation["quality_baseline"]["predicted_confidence_class"] == "low"
    assert "ANNOTATION_UNAVAILABLE" in annotation["quality_baseline"]["drift_reason_codes"]


def test_cdr_h3_annotation_is_deterministic() -> None:
    structure = _Structure([_chain_from_sequence("X", 1, "AAAAACAAAAAWGQGAAAAA")])

    first = annotate_cdr_h3(structure)
    second = annotate_cdr_h3(structure)

    assert first == second


def test_cdr_bookkeeping_ready_flag_requires_actual_annotation() -> None:
    summary = StructureSummary(
        parser_name="MMCIFParser",
        model_count=1,
        available_chains=["X", "A"],
        residue_counts={"X": 20, "A": 8},
        metadata={
            "total_residues": 28,
            "cdr_annotation": {
                "available": True,
                "scheme": "motif_fallback",
                "boundary_source": "motif_fallback",
                "boundary_confidence": "medium",
                "selected_heavy_chain": "X",
                "chains": {"X": {"role": "heavy", "regions": {"CDR-H3": {}}}},
                "warnings": ["CDR_MOTIF_FALLBACK_USED", "CDR_NUMBERING_MISSING"],
            },
        },
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="mmcif",
        chain_groups=ChainMapping(partner_1=["X"], partner_2=["A"]),
        partner_residue_counts={"partner_1": 20, "partner_2": 8},
    )

    bundle = build_descriptor_bundle(summary, validation, "antibody_antigen")

    assert bundle.descriptors["cdr_bookkeeping_ready_flag"] == 1.0
    assert "CDR_H3_ANNOTATED" in bundle.notes
    assert "CDR_H3_ANNOTATED_MOTIF_FALLBACK" in bundle.notes


def test_cdr_annotation_assigns_light_kappa_role() -> None:
    heavy = _chain_from_sequence("H", 90, "AAAA" + "C" + "AAAAAAAA" + "W" + "AAAAAAAAAAAA")
    light = _chain_from_sequence("K1", 1, "ACDEFGHIKLMNPQRSTVAY" * 5)
    structure = _Structure([heavy, light])

    annotation = annotate_cdr_h3(structure)

    assert annotation["chains"]["K1"]["role"] == "light_kappa"
    assert annotation["chains"]["K1"]["confidence"] == "high"


def test_cdr_annotation_assigns_light_unknown_fallback_role() -> None:
    heavy = _chain_from_sequence("H", 90, "AAAA" + "C" + "AAAAAAAA" + "W" + "AAAAAAAAAAAA")
    light = _chain_from_sequence("L2", 1, "ACDEFGHIKLMNPQRSTVAY" * 5)
    structure = _Structure([heavy, light])

    annotation = annotate_cdr_h3(structure)

    assert annotation["chains"]["L2"]["role"] == "light_unknown"
    assert annotation["chains"]["L2"]["confidence"] == "high"


def test_cdr_annotation_assigns_light_lambda_role() -> None:
    heavy = _chain_from_sequence("H", 90, "AAAA" + "C" + "AAAAAAAA" + "W" + "AAAAAAAAAAAA")
    light = _chain_from_sequence("LAM_A", 1, "ACDEFGHIKLMNPQRSTVAY" * 5)
    structure = _Structure([heavy, light])

    annotation = annotate_cdr_h3(structure)

    assert annotation["chains"]["LAM_A"]["role"] == "light_lambda"
    assert annotation["chains"]["LAM_A"]["confidence"] == "high"


def test_full_numbered_cdr_regions_extracted_for_heavy_and_light() -> None:
    heavy_sequence = ("A" * 9) + "C" + ("A" * 130)
    light_sequence = ("A" * 23) + "C" + ("A" * 20) + "F" + ("A" * 81)
    structure = _Structure(
        [
            _chain_from_sequence("H", 1, heavy_sequence),
            _chain_from_sequence("L", 1, light_sequence),
        ]
    )

    annotation = annotate_cdr_h3(structure)

    heavy_regions = set(annotation["chains"]["H"]["regions"].keys())
    light_regions = set(annotation["chains"]["L"]["regions"].keys())

    assert {"CDR-H1", "CDR-H2", "CDR-H3"}.issubset(heavy_regions)
    assert {"CDR-L1", "CDR-L2", "CDR-L3"}.issubset(light_regions)
    assert annotation["chains"]["H"]["completeness_score"] == 1.0
    assert annotation["chains"]["L"]["completeness_score"] == 1.0
    assert annotation["quality_baseline"]["predicted_confidence_class"] == "high"
    assert annotation["quality_baseline"]["drift_flag"] is False
    assert annotation["quality_baseline"]["model_contract"]["model_id"] == (
        "cdr_boundary_quality_heuristic"
    )


def test_cdr_region_payload_keeps_insertion_code_ordering() -> None:
    heavy_residues = [_Residue(i, "ALA") for i in range(1, 111)]
    heavy_residues.extend([
        _Residue(31, "ALA", "A"),
        _Residue(31, "ALA", "B"),
    ])
    structure = _Structure([_Chain("H", heavy_residues)])

    annotation = annotate_cdr_h3(structure)
    h1_region = annotation["chains"]["H"]["regions"]["CDR-H1"]
    insertion_codes = [item["insertion_code"] for item in h1_region["residue_keys"]]

    assert "A" in insertion_codes
    assert "B" in insertion_codes
    assert insertion_codes.index("") < insertion_codes.index("A") < insertion_codes.index("B")


def test_discontinuous_numbering_yields_partial_heavy_completeness() -> None:
    heavy_residues = [_Residue(i, "ALA") for i in range(1, 41)]
    heavy_residues[9] = _Residue(10, "CYS")
    heavy_residues[19] = _Residue(20, "TRP")
    heavy_residues.extend([_Residue(i, "ALA") for i in range(95, 103)])
    structure = _Structure([_Chain("H", heavy_residues)])

    annotation = annotate_cdr_h3(structure)
    heavy = annotation["chains"]["H"]

    assert annotation["available"] is True
    assert heavy["regions"].get("CDR-H1") is not None
    assert heavy["regions"].get("CDR-H2") is None
    assert heavy["regions"].get("CDR-H3") is not None
    assert heavy["completeness_score"] == round(2 / 3, 4)
    assert CDR_BOUNDARY_AMBIGUOUS in annotation["warnings"]


def test_multi_model_annotation_uses_first_model_deterministically() -> None:
    first_model_heavy = _chain_from_sequence(
        "H",
        95,
        "CWAAAAAA",
    )
    second_model_heavy = _chain_from_sequence(
        "H",
        95,
        "AAAAAAAC",
    )
    structure = _MultiModelStructure([[first_model_heavy], [second_model_heavy]])

    annotation = annotate_cdr_h3(structure)

    assert annotation["available"] is True
    assert annotation["selected_heavy_chain"] == "H"
    assert "CDR-H3" in annotation["chains"]["H"]["regions"]
