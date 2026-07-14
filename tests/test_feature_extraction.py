from __future__ import annotations

from abby_api.schemas.structures import ChainMapping, StructureSummary, StructureValidationResult
from abby_api.services.feature_extraction import build_descriptor_bundle


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
