from __future__ import annotations

from abby_api.schemas.structures import ChainMapping, StructureSummary, StructureValidationResult
from abby_api.services.feature_extraction import (
    build_descriptor_bundle,
    make_explainability_summary,
)


def test_enrichment_hook_flags_disabled_without_chain_groups() -> None:
    summary = StructureSummary(
        parser_name="PDBParser",
        model_count=1,
        available_chains=[],
        residue_counts={},
        metadata={"total_residues": 0},
    )
    validation = StructureValidationResult(
        valid=False,
        normalized_format="pdb",
        chain_groups=None,
    )

    bundle = build_descriptor_bundle(summary, validation, "ppi_general")
    assert bundle.descriptors["electrostatics_hook_ready_flag"] == 0.0
    assert bundle.descriptors["surface_pka_hook_ready_flag"] == 0.0
    assert "ELECTROSTATICS_SURFACE_PKA_HOOKS_ENABLED" not in bundle.notes


def test_enrichment_hook_flags_enabled_with_chain_groups() -> None:
    summary = StructureSummary(
        parser_name="PDBParser",
        model_count=1,
        available_chains=["A", "B"],
        residue_counts={"A": 1, "B": 1},
        metadata={"total_residues": 2},
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="pdb",
        chain_groups=ChainMapping(partner_1=["A"], partner_2=["B"]),
        partner_residue_counts={"partner_1": 1, "partner_2": 1},
    )

    bundle = build_descriptor_bundle(summary, validation, "ppi_general")
    assert bundle.descriptors["electrostatics_hook_ready_flag"] == 1.0
    assert bundle.descriptors["surface_pka_hook_ready_flag"] == 1.0
    assert "ELECTROSTATICS_SURFACE_PKA_HOOKS_ENABLED" in bundle.notes


def test_cdr_descriptor_features_are_emitted_for_antibody_mode() -> None:
    summary = StructureSummary(
        parser_name="PDBParser",
        model_count=1,
        available_chains=["H", "L", "A"],
        residue_counts={"H": 10, "L": 8, "A": 7},
        metadata={
            "total_residues": 25,
            "cdr_annotation": {
                "available": True,
                "warnings": [],
                "chains": {
                    "H": {
                        "role": "heavy",
                        "completeness_score": 1.0,
                        "regions": {
                            "CDR-H1": {"length": 5},
                            "CDR-H2": {"length": 6},
                            "CDR-H3": {"length": 8},
                        },
                    },
                    "L": {
                        "role": "light_unknown",
                        "completeness_score": 0.6667,
                        "regions": {
                            "CDR-L1": {"length": 5},
                            "CDR-L3": {"length": 6},
                        },
                    },
                },
            },
        },
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="pdb",
        chain_groups=ChainMapping(partner_1=["H", "L"], partner_2=["A"]),
        partner_residue_counts={"partner_1": 18, "partner_2": 7},
    )

    bundle = build_descriptor_bundle(summary, validation, "antibody_antigen")

    assert bundle.descriptor_version == "summary_features_v3"
    assert bundle.descriptors["cdr_region_count_total"] == 5.0
    assert bundle.descriptors["cdr_region_residue_count_total"] == 30.0
    assert bundle.descriptors["cdr_h1_length"] == 5.0
    assert bundle.descriptors["cdr_h2_length"] == 6.0
    assert bundle.descriptors["cdr_h3_length"] == 8.0
    assert bundle.descriptors["cdr_l1_length"] == 5.0
    assert bundle.descriptors["cdr_l2_length"] == 0.0
    assert bundle.descriptors["cdr_l3_length"] == 6.0
    assert bundle.descriptors["cdr_partner_1_region_residue_count"] == 30.0
    assert bundle.descriptors["cdr_partner_2_region_residue_count"] == 0.0
    assert bundle.descriptors["cdr_interface_overlap_proxy"] == 0.0
    assert bundle.descriptors["cdr_heavy_completeness_mean"] == 1.0
    assert bundle.descriptors["cdr_light_completeness_mean"] == 0.6667
    assert "CDR_DESCRIPTOR_FEATURES_ENABLED" in bundle.notes
    # Backward compatibility: existing descriptors still present.
    assert "interface_contact_proxy" in bundle.descriptors
    assert "sasa_total" in bundle.descriptors


def test_cdr_explainability_includes_cdr_descriptors_when_available() -> None:
    summary = StructureSummary(
        parser_name="PDBParser",
        model_count=1,
        available_chains=["H", "L", "A"],
        residue_counts={"H": 10, "L": 8, "A": 7},
        metadata={
            "total_residues": 25,
            "cdr_annotation": {
                "available": True,
                "warnings": [],
                "chains": {
                    "H": {
                        "role": "heavy",
                        "completeness_score": 1.0,
                        "regions": {
                            "CDR-H1": {"length": 5},
                            "CDR-H2": {"length": 6},
                            "CDR-H3": {"length": 12},
                        },
                    },
                    "L": {
                        "role": "light_unknown",
                        "completeness_score": 1.0,
                        "regions": {
                            "CDR-L1": {"length": 5},
                            "CDR-L2": {"length": 5},
                            "CDR-L3": {"length": 6},
                        },
                    },
                },
            },
        },
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="pdb",
        chain_groups=ChainMapping(partner_1=["H", "L"], partner_2=["A"]),
        partner_residue_counts={"partner_1": 18, "partner_2": 7},
    )

    bundle = build_descriptor_bundle(summary, validation, "antibody_antigen")
    explainability = make_explainability_summary(bundle)

    descriptor_names = [item.name for item in explainability.top_descriptors]
    assert any(name.startswith("cdr_") for name in descriptor_names)


def test_cdr_descriptor_hash_is_deterministic_for_same_inputs() -> None:
    summary = StructureSummary(
        parser_name="PDBParser",
        model_count=1,
        available_chains=["H", "L", "A"],
        residue_counts={"H": 10, "L": 8, "A": 7},
        metadata={
            "total_residues": 25,
            "cdr_annotation": {
                "available": True,
                "warnings": [],
                "chains": {
                    "H": {
                        "role": "heavy",
                        "completeness_score": 1.0,
                        "regions": {
                            "CDR-H1": {"length": 5},
                            "CDR-H2": {"length": 6},
                            "CDR-H3": {"length": 8},
                        },
                    },
                },
            },
        },
    )
    validation = StructureValidationResult(
        valid=True,
        normalized_format="pdb",
        chain_groups=ChainMapping(partner_1=["H"], partner_2=["A"]),
        partner_residue_counts={"partner_1": 10, "partner_2": 7},
    )

    first = build_descriptor_bundle(summary, validation, "antibody_antigen")
    second = build_descriptor_bundle(summary, validation, "antibody_antigen")

    assert first.descriptor_version == "summary_features_v3"
    assert first.descriptors == second.descriptors
    assert first.notes == second.notes
    assert first.descriptor_hash == second.descriptor_hash
