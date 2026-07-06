from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps

from abby_api.schemas.common import DescriptorContribution, Explainability, PredictionMode
from abby_api.schemas.predictions import FeatureSummary
from abby_api.schemas.structures import StructureSummary, StructureValidationResult

RESIDUE_CLASS_MAP = {
    "ARG": "charged",
    "LYS": "charged",
    "ASP": "charged",
    "GLU": "charged",
    "HIS": "charged",
    "SER": "polar",
    "THR": "polar",
    "ASN": "polar",
    "GLN": "polar",
    "CYS": "polar",
    "TYR": "polar",
    "GLY": "apolar",
    "ALA": "apolar",
    "VAL": "apolar",
    "LEU": "apolar",
    "ILE": "apolar",
    "MET": "apolar",
    "PRO": "apolar",
    "PHE": "aromatic",
    "TRP": "aromatic",
}

DESCRIPTOR_VERSION = "summary_features_v1"


def classify_residue(residue_name: str) -> str:
    return RESIDUE_CLASS_MAP.get(residue_name.upper(), "other")


@dataclass(frozen=True)
class DescriptorBundle:
    descriptor_version: str
    descriptors: dict[str, float]
    partner_residues: dict[str, int]
    residue_class_fractions: dict[str, float]
    notes: list[str]
    descriptor_hash: str


def _partner_chain_class_counts(
    summary: StructureSummary,
    chains: list[str],
) -> dict[str, int]:
    counts = {"charged": 0, "polar": 0, "apolar": 0, "aromatic": 0, "other": 0}
    by_chain = summary.metadata.get("chain_residue_class_counts", {})
    for chain_id in chains:
        chain_counts = by_chain.get(chain_id, {})
        for residue_class in counts:
            counts[residue_class] += int(chain_counts.get(residue_class, 0))
    return counts


def _fractions(counts: dict[str, int], total: int) -> dict[str, float]:
    denominator = max(total, 1)
    return {key: round(value / denominator, 4) for key, value in counts.items()}


def _build_descriptor_hash(payload: dict[str, object]) -> str:
    serialized = dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def build_descriptor_bundle(
    summary: StructureSummary,
    validation: StructureValidationResult,
    mode: PredictionMode,
) -> DescriptorBundle:
    partner_1_chains = validation.chain_groups.partner_1 if validation.chain_groups else []
    partner_2_chains = validation.chain_groups.partner_2 if validation.chain_groups else []

    partner_residues = {
        "partner_1": int(validation.partner_residue_counts.get("partner_1", 0)),
        "partner_2": int(validation.partner_residue_counts.get("partner_2", 0)),
    }
    total_residues = max(int(summary.metadata.get("total_residues", 0)), 1)
    smaller_partner = min(partner_residues.values())
    larger_partner = max(partner_residues.values())

    partner_1_class_counts = _partner_chain_class_counts(summary, partner_1_chains)
    partner_2_class_counts = _partner_chain_class_counts(summary, partner_2_chains)
    global_counts = {
        key: int(value)
        for key, value in summary.metadata.get("global_residue_class_counts", {}).items()
    }
    residue_class_fractions = _fractions(global_counts, total_residues)

    paired_apolar = min(partner_1_class_counts["apolar"], partner_2_class_counts["apolar"])
    paired_charged = min(partner_1_class_counts["charged"], partner_2_class_counts["charged"])
    paired_polar = min(partner_1_class_counts["polar"], partner_2_class_counts["polar"])
    interface_contact_proxy = round(
        min(smaller_partner * 1.5, paired_apolar + paired_charged + paired_polar + 1),
        4,
    )

    descriptors = {
        "total_residues": float(total_residues),
        "partner_1_residue_fraction": round(partner_residues["partner_1"] / total_residues, 4),
        "partner_2_residue_fraction": round(partner_residues["partner_2"] / total_residues, 4),
        "partner_size_ratio": round(smaller_partner / max(larger_partner, 1), 4),
        "interface_contact_proxy": interface_contact_proxy,
        "interface_density_proxy": round(interface_contact_proxy / total_residues, 4),
        "paired_apolar_proxy": float(paired_apolar),
        "paired_charged_proxy": float(paired_charged),
        "paired_polar_proxy": float(paired_polar),
        "global_apolar_fraction": residue_class_fractions.get("apolar", 0.0),
        "global_charged_fraction": residue_class_fractions.get("charged", 0.0),
        "global_polar_fraction": residue_class_fractions.get("polar", 0.0),
        "global_aromatic_fraction": residue_class_fractions.get("aromatic", 0.0),
        "multi_model_flag": 1.0 if summary.model_count > 1 else 0.0,
        "antibody_mode_flag": 1.0 if mode == "antibody_antigen" else 0.0,
    }
    notes = list(summary.warnings)
    if validation.warnings:
        notes.extend(validation.warnings)
    notes = sorted(set(notes))

    hash_payload = {
        "descriptor_version": DESCRIPTOR_VERSION,
        "descriptors": descriptors,
        "partner_residues": partner_residues,
        "residue_class_fractions": residue_class_fractions,
        "notes": notes,
    }
    return DescriptorBundle(
        descriptor_version=DESCRIPTOR_VERSION,
        descriptors=descriptors,
        partner_residues=partner_residues,
        residue_class_fractions=residue_class_fractions,
        notes=notes,
        descriptor_hash=_build_descriptor_hash(hash_payload),
    )


def make_feature_summary(bundle: DescriptorBundle) -> FeatureSummary:
    return FeatureSummary(
        descriptor_version=bundle.descriptor_version,
        source="parsed_structure_summary",
        descriptors=bundle.descriptors,
        partner_residues=bundle.partner_residues,
        residue_class_fractions=bundle.residue_class_fractions,
        notes=bundle.notes,
    )


def make_explainability_summary(bundle: DescriptorBundle) -> Explainability:
    ranked = sorted(
        bundle.descriptors.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:5]
    return Explainability(
        top_descriptors=[
            DescriptorContribution(name=name, contribution=round(value, 4))
            for name, value in ranked
        ]
    )