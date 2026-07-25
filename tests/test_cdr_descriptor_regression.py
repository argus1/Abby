from __future__ import annotations

from abby_api.schemas.structures import ChainMapping, StructureSummary, StructureValidationResult
from abby_api.services.feature_extraction import build_descriptor_bundle


def _antibody_descriptor_inputs() -> tuple[StructureSummary, StructureValidationResult]:
    summary = StructureSummary(
        parser_name="MMCIFParser",
        model_count=1,
        available_chains=["H", "L", "A"],
        residue_counts={"H": 120, "L": 110, "A": 80},
        metadata={
            "total_residues": 310,
            "cdr_annotation": {
                "available": True,
                "warnings": [],
                "chains": {
                    "H": {
                        "role": "heavy",
                        "completeness_score": 1.0,
                        "regions": {
                            "CDR-H1": {"length": 5},
                            "CDR-H2": {"length": 16},
                            "CDR-H3": {"length": 8},
                        },
                    },
                    "L": {
                        "role": "light_kappa",
                        "completeness_score": 1.0,
                        "regions": {
                            "CDR-L1": {"length": 11},
                            "CDR-L2": {"length": 7},
                            "CDR-L3": {"length": 9},
                        },
                    },
                },
            },
        },
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="mmcif",
        chain_groups=ChainMapping(partner_1=["H", "L"], partner_2=["A"]),
        partner_residue_counts={"partner_1": 230, "partner_2": 80},
    )
    return summary, validation


def test_cdr_descriptor_bundle_matches_provenance_regression_hash() -> None:
    summary, validation = _antibody_descriptor_inputs()

    bundle = build_descriptor_bundle(summary, validation, "antibody_antigen")

    assert bundle.descriptor_version == "summary_features_v3"
    assert bundle.descriptor_hash == (
        "345bc3f1fa67f4b41abcc2d7b7f9c39f3582753ff8a6fe1859fbc358b1bd0bfc"
    )


def test_cdr_descriptor_bundle_preserves_legacy_and_region_fields() -> None:
    summary, validation = _antibody_descriptor_inputs()

    descriptors = build_descriptor_bundle(
        summary,
        validation,
        "antibody_antigen",
    ).descriptors

    assert {
        "total_residues",
        "partner_size_ratio",
        "interface_contact_proxy",
        "sasa_total",
        "global_apolar_fraction",
    }.issubset(descriptors)
    assert {
        "cdr_h1_length": 5.0,
        "cdr_h2_length": 16.0,
        "cdr_h3_length": 8.0,
        "cdr_l1_length": 11.0,
        "cdr_l2_length": 7.0,
        "cdr_l3_length": 9.0,
        "cdr_region_count_total": 6.0,
        "cdr_region_residue_count_total": 56.0,
    }.items() <= descriptors.items()


def test_cdr_descriptor_extension_is_neutral_for_non_antibody_mode() -> None:
    summary = StructureSummary(
        parser_name="MMCIFParser",
        model_count=1,
        available_chains=["A", "B"],
        residue_counts={"A": 40, "B": 20},
        metadata={"total_residues": 60},
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="mmcif",
        chain_groups=ChainMapping(partner_1=["A"], partner_2=["B"]),
        partner_residue_counts={"partner_1": 40, "partner_2": 20},
    )

    bundle = build_descriptor_bundle(summary, validation, "ppi_general")

    assert bundle.descriptors["cdr_bookkeeping_ready_flag"] == 0.0
    assert all(
        value == 0.0
        for name, value in bundle.descriptors.items()
        if name.startswith("cdr_")
    )
    assert "CDR_DESCRIPTOR_FEATURES_ENABLED" not in bundle.notes
