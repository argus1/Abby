from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from math import sqrt
from typing import Any

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

# v2 adds residue-depth, burial, radius of gyration, and enrichment-hook bookkeeping.
DESCRIPTOR_VERSION = "summary_features_v2"


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


@dataclass(frozen=True)
class ContactObservation:
    total_contacts: int
    contact_bins: dict[str, int]
    interface_residue_counts: dict[str, int]
    notes: list[str]


@dataclass(frozen=True)
class SolventAccessibilityObservation:
    total_sasa: float
    partner_sasa: dict[str, float]
    class_sasa_fractions: dict[str, float]
    accessible_residue_count: int
    notes: list[str]


@dataclass(frozen=True)
class ResidueDepthObservation:
    partner_depth_means: dict[str, float]
    interface_depth_mean: float
    non_interface_depth_mean: float
    interface_burial_delta: float
    interface_residue_count: int
    notes: list[str]


@dataclass(frozen=True)
class RadiusOfGyrationObservation:
    radius_of_gyration_angstrom: float
    atom_count: int
    notes: list[str]


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


def _residue_name(residue: Any) -> str:
    value = residue.get_resname() if hasattr(residue, "get_resname") else getattr(residue, "resname", "UNK")
    return str(value).strip().upper()


def _residue_atom_coords(residue: Any) -> list[tuple[float, float, float]]:
    if hasattr(residue, "get_atoms"):
        coords: list[tuple[float, float, float]] = []
        for atom in residue.get_atoms():
            if hasattr(atom, "get_coord"):
                coord = atom.get_coord()
                coords.append((float(coord[0]), float(coord[1]), float(coord[2])))
            elif isinstance(atom, tuple) and len(atom) == 3:
                coords.append((float(atom[0]), float(atom[1]), float(atom[2])))
        return coords
    return []


def _iter_residues_by_chain(model: Any) -> dict[str, list[Any]]:
    residues_by_chain: dict[str, list[Any]] = {}
    for chain in model.get_chains():
        chain_id = str(getattr(chain, "id", "")).strip()
        if not chain_id:
            continue
        residues: list[Any] = []
        for residue in chain.get_residues():
            residue_id = getattr(residue, "id", None)
            if isinstance(residue_id, tuple) and residue_id and residue_id[0] != " ":
                continue
            residues.append(residue)
        residues_by_chain[chain_id] = residues
    return residues_by_chain


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _residue_centroid(residue: Any) -> tuple[float, float, float] | None:
    coords = _residue_atom_coords(residue)
    if not coords:
        return None
    return (
        sum(coord[0] for coord in coords) / len(coords),
        sum(coord[1] for coord in coords) / len(coords),
        sum(coord[2] for coord in coords) / len(coords),
    )


def _depths_from_geometry(model: Any) -> dict[int, float]:
    residue_depths: dict[int, float] = {}
    residues = [residue for chain in model.get_chains() for residue in chain.get_residues()]
    all_atoms = [coord for residue in residues for coord in _residue_atom_coords(residue)]
    if not all_atoms:
        return residue_depths

    center = (
        sum(coord[0] for coord in all_atoms) / len(all_atoms),
        sum(coord[1] for coord in all_atoms) / len(all_atoms),
        sum(coord[2] for coord in all_atoms) / len(all_atoms),
    )
    max_radius = 0.0
    for atom in all_atoms:
        radius = sqrt(
            ((atom[0] - center[0]) ** 2)
            + ((atom[1] - center[1]) ** 2)
            + ((atom[2] - center[2]) ** 2)
        )
        if radius > max_radius:
            max_radius = radius

    for residue in residues:
        centroid = _residue_centroid(residue)
        if centroid is None:
            continue
        radius = sqrt(
            ((centroid[0] - center[0]) ** 2)
            + ((centroid[1] - center[1]) ** 2)
            + ((centroid[2] - center[2]) ** 2)
        )
        residue_depths[id(residue)] = round(max(max_radius - radius, 0.0), 4)

    return residue_depths


def _antibody_chain_candidate_count(chains: list[str]) -> int:
    """Return a lightweight antibody-chain count for bookkeeping-only feature hooks.

    This heuristic intentionally looks only for single-letter `H`/`L` chain IDs and can
    produce false positives for non-antibody structures that use the same labels.
    This is acceptable for initial bookkeeping and should not be used for definitive
    antibody-chain identification.
    """
    return len([chain_id for chain_id in chains if len(chain_id) == 1 and chain_id.upper() in {"H", "L"}])


def _to_contact_letter(residue_class: str) -> str:
    if residue_class == "charged":
        return "C"
    if residue_class == "polar":
        return "P"
    if residue_class in {"apolar", "aromatic"}:
        return "A"
    return "P"


def calculate_inter_partner_contacts(
    structure: Any,
    validation: StructureValidationResult,
    distance_cutoff: float = 5.5,
) -> ContactObservation:
    if validation.chain_groups is None:
        return ContactObservation(
            total_contacts=0,
            contact_bins={"AA": 0, "PP": 0, "CC": 0, "AP": 0, "CP": 0, "AC": 0},
            interface_residue_counts={"partner_1": 0, "partner_2": 0},
            notes=["MISSING_CHAIN_GROUPS_FOR_CONTACTS"],
        )

    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        return ContactObservation(
            total_contacts=0,
            contact_bins={"AA": 0, "PP": 0, "CC": 0, "AP": 0, "CP": 0, "AC": 0},
            interface_residue_counts={"partner_1": 0, "partner_2": 0},
            notes=["NO_MODELS_AVAILABLE_FOR_CONTACTS"],
        )

    model = models[0]
    residues_by_chain = _iter_residues_by_chain(model)

    partner_1_residues = [
        residue
        for chain_id in validation.chain_groups.partner_1
        for residue in residues_by_chain.get(chain_id, [])
    ]
    partner_2_residues = [
        residue
        for chain_id in validation.chain_groups.partner_2
        for residue in residues_by_chain.get(chain_id, [])
    ]

    contact_bins: dict[str, int] = {"AA": 0, "PP": 0, "CC": 0, "AP": 0, "CP": 0, "AC": 0}
    interface_partner_1: set[tuple[Any, ...]] = set()
    interface_partner_2: set[tuple[Any, ...]] = set()

    d2_cutoff = float(distance_cutoff) ** 2

    for residue_1 in partner_1_residues:
        atoms_1 = _residue_atom_coords(residue_1)
        if not atoms_1:
            continue
        for residue_2 in partner_2_residues:
            atoms_2 = _residue_atom_coords(residue_2)
            if not atoms_2:
                continue

            has_contact = False
            for atom_1 in atoms_1:
                for atom_2 in atoms_2:
                    dx = atom_1[0] - atom_2[0]
                    dy = atom_1[1] - atom_2[1]
                    dz = atom_1[2] - atom_2[2]
                    if (dx * dx) + (dy * dy) + (dz * dz) <= d2_cutoff:
                        has_contact = True
                        break
                if has_contact:
                    break

            if not has_contact:
                continue

            class_1 = _to_contact_letter(classify_residue(_residue_name(residue_1)))
            class_2 = _to_contact_letter(classify_residue(_residue_name(residue_2)))
            contact_key = "".join(sorted((class_1, class_2)))
            if contact_key in contact_bins:
                contact_bins[contact_key] += 1

            residue_1_id = getattr(residue_1, "id", (id(residue_1),))
            residue_2_id = getattr(residue_2, "id", (id(residue_2),))
            interface_partner_1.add(tuple(residue_1_id) if isinstance(residue_1_id, tuple) else (residue_1_id,))
            interface_partner_2.add(tuple(residue_2_id) if isinstance(residue_2_id, tuple) else (residue_2_id,))

    total_contacts = sum(contact_bins.values())
    notes: list[str] = []
    if total_contacts == 0:
        notes.append("NO_INTER_PARTNER_CONTACTS")

    return ContactObservation(
        total_contacts=total_contacts,
        contact_bins=contact_bins,
        interface_residue_counts={
            "partner_1": len(interface_partner_1),
            "partner_2": len(interface_partner_2),
        },
        notes=notes,
    )


def calculate_solvent_accessibility(
    structure: Any,
    validation: StructureValidationResult,
) -> SolventAccessibilityObservation:
    empty_fractions = {
        "charged": 0.0,
        "polar": 0.0,
        "apolar": 0.0,
        "aromatic": 0.0,
        "other": 0.0,
    }
    if validation.chain_groups is None:
        return SolventAccessibilityObservation(
            total_sasa=0.0,
            partner_sasa={"partner_1": 0.0, "partner_2": 0.0},
            class_sasa_fractions=empty_fractions,
            accessible_residue_count=0,
            notes=["MISSING_CHAIN_GROUPS_FOR_SASA"],
        )

    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        return SolventAccessibilityObservation(
            total_sasa=0.0,
            partner_sasa={"partner_1": 0.0, "partner_2": 0.0},
            class_sasa_fractions=empty_fractions,
            accessible_residue_count=0,
            notes=["NO_MODELS_AVAILABLE_FOR_SASA"],
        )

    model = models[0]
    if not hasattr(model, "get_atoms"):
        return SolventAccessibilityObservation(
            total_sasa=0.0,
            partner_sasa={"partner_1": 0.0, "partner_2": 0.0},
            class_sasa_fractions=empty_fractions,
            accessible_residue_count=0,
            notes=["SASA_UNAVAILABLE_FOR_FALLBACK_PARSER"],
        )

    try:
        from Bio.PDB.SASA import ShrakeRupley
    except ModuleNotFoundError:
        return SolventAccessibilityObservation(
            total_sasa=0.0,
            partner_sasa={"partner_1": 0.0, "partner_2": 0.0},
            class_sasa_fractions=empty_fractions,
            accessible_residue_count=0,
            notes=["SASA_UNAVAILABLE_NO_BIOPYTHON"],
        )

    try:
        ShrakeRupley().compute(model, level="R")
    except Exception:
        return SolventAccessibilityObservation(
            total_sasa=0.0,
            partner_sasa={"partner_1": 0.0, "partner_2": 0.0},
            class_sasa_fractions=empty_fractions,
            accessible_residue_count=0,
            notes=["SASA_COMPUTE_FAILED"],
        )

    residues_by_chain = _iter_residues_by_chain(model)
    class_sasa = {"charged": 0.0, "polar": 0.0, "apolar": 0.0, "aromatic": 0.0, "other": 0.0}
    partner_sasa = {"partner_1": 0.0, "partner_2": 0.0}
    accessible_residue_count = 0

    def _accumulate(chain_ids: list[str], partner_name: str) -> None:
        nonlocal accessible_residue_count
        for chain_id in chain_ids:
            for residue in residues_by_chain.get(chain_id, []):
                sasa = float(getattr(residue, "sasa", 0.0) or 0.0)
                if sasa <= 0.0:
                    continue
                accessible_residue_count += 1
                partner_sasa[partner_name] += sasa
                residue_class = classify_residue(_residue_name(residue))
                class_sasa[residue_class] += sasa

    _accumulate(validation.chain_groups.partner_1, "partner_1")
    _accumulate(validation.chain_groups.partner_2, "partner_2")

    total_sasa = sum(class_sasa.values())
    denominator = max(total_sasa, 1e-12)
    class_sasa_fractions = {k: round(v / denominator, 4) for k, v in class_sasa.items()}

    return SolventAccessibilityObservation(
        total_sasa=round(total_sasa, 4),
        partner_sasa={
            "partner_1": round(partner_sasa["partner_1"], 4),
            "partner_2": round(partner_sasa["partner_2"], 4),
        },
        class_sasa_fractions=class_sasa_fractions,
        accessible_residue_count=accessible_residue_count,
        notes=[],
    )


def calculate_residue_depth(
    structure: Any,
    validation: StructureValidationResult,
    distance_cutoff: float = 5.5,
) -> ResidueDepthObservation:
    if validation.chain_groups is None:
        return ResidueDepthObservation(
            partner_depth_means={"partner_1": 0.0, "partner_2": 0.0},
            interface_depth_mean=0.0,
            non_interface_depth_mean=0.0,
            interface_burial_delta=0.0,
            interface_residue_count=0,
            notes=["MISSING_CHAIN_GROUPS_FOR_RESIDUE_DEPTH"],
        )

    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        return ResidueDepthObservation(
            partner_depth_means={"partner_1": 0.0, "partner_2": 0.0},
            interface_depth_mean=0.0,
            non_interface_depth_mean=0.0,
            interface_burial_delta=0.0,
            interface_residue_count=0,
            notes=["NO_MODELS_AVAILABLE_FOR_RESIDUE_DEPTH"],
        )

    model = models[0]
    residues_by_chain = _iter_residues_by_chain(model)
    partner_1_residues = [
        residue
        for chain_id in validation.chain_groups.partner_1
        for residue in residues_by_chain.get(chain_id, [])
    ]
    partner_2_residues = [
        residue
        for chain_id in validation.chain_groups.partner_2
        for residue in residues_by_chain.get(chain_id, [])
    ]
    selected_residues = [*partner_1_residues, *partner_2_residues]

    notes: list[str] = []
    residue_depths: dict[int, float] = {}

    try:
        from Bio.PDB.ResidueDepth import ResidueDepth

        depth_model = ResidueDepth(model)
        depth_payload = getattr(depth_model, "property_dict", {})
        if isinstance(depth_payload, dict):
            for residue, value in depth_payload.items():
                if isinstance(value, (tuple, list)):
                    depth_value = float(value[0]) if value else 0.0
                else:
                    depth_value = float(value)
                residue_depths[id(residue)] = round(depth_value, 4)
            notes.append("RESIDUE_DEPTH_FROM_BIOPYTHON")
    except Exception:
        residue_depths = {}

    if not residue_depths:
        residue_depths = _depths_from_geometry(model)
        notes.append("RESIDUE_DEPTH_FROM_GEOMETRY_PROXY")

    interface_residue_ids: set[int] = set()
    d2_cutoff = float(distance_cutoff) ** 2
    for residue_1 in partner_1_residues:
        atoms_1 = _residue_atom_coords(residue_1)
        if not atoms_1:
            continue
        for residue_2 in partner_2_residues:
            atoms_2 = _residue_atom_coords(residue_2)
            if not atoms_2:
                continue
            has_contact = False
            for atom_1 in atoms_1:
                for atom_2 in atoms_2:
                    dx = atom_1[0] - atom_2[0]
                    dy = atom_1[1] - atom_2[1]
                    dz = atom_1[2] - atom_2[2]
                    if (dx * dx) + (dy * dy) + (dz * dz) <= d2_cutoff:
                        has_contact = True
                        break
                if has_contact:
                    break
            if has_contact:
                interface_residue_ids.add(id(residue_1))
                interface_residue_ids.add(id(residue_2))

    partner_1_depths = [
        residue_depths[id(residue)]
        for residue in partner_1_residues
        if id(residue) in residue_depths
    ]
    partner_2_depths = [
        residue_depths[id(residue)]
        for residue in partner_2_residues
        if id(residue) in residue_depths
    ]
    interface_depths = [
        residue_depths[residue_id]
        for residue_id in interface_residue_ids
        if residue_id in residue_depths
    ]
    non_interface_depths = [
        residue_depths[id(residue)]
        for residue in selected_residues
        if id(residue) in residue_depths and id(residue) not in interface_residue_ids
    ]

    interface_depth_mean = _mean(interface_depths)
    non_interface_depth_mean = _mean(non_interface_depths)
    if not interface_depths:
        notes.append("NO_INTERFACE_RESIDUE_DEPTHS")

    return ResidueDepthObservation(
        partner_depth_means={
            "partner_1": round(_mean(partner_1_depths), 4),
            "partner_2": round(_mean(partner_2_depths), 4),
        },
        interface_depth_mean=round(interface_depth_mean, 4),
        non_interface_depth_mean=round(non_interface_depth_mean, 4),
        interface_burial_delta=round(interface_depth_mean - non_interface_depth_mean, 4),
        interface_residue_count=len(interface_depths),
        notes=notes,
    )


def calculate_radius_of_gyration(
    structure: Any,
    validation: StructureValidationResult,
) -> RadiusOfGyrationObservation:
    if validation.chain_groups is None:
        return RadiusOfGyrationObservation(
            radius_of_gyration_angstrom=0.0,
            atom_count=0,
            notes=["MISSING_CHAIN_GROUPS_FOR_RADIUS_OF_GYRATION"],
        )

    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        return RadiusOfGyrationObservation(
            radius_of_gyration_angstrom=0.0,
            atom_count=0,
            notes=["NO_MODELS_AVAILABLE_FOR_RADIUS_OF_GYRATION"],
        )

    model = models[0]
    residues_by_chain = _iter_residues_by_chain(model)
    selected_chains = [*validation.chain_groups.partner_1, *validation.chain_groups.partner_2]
    atom_coords = [
        coord
        for chain_id in selected_chains
        for residue in residues_by_chain.get(chain_id, [])
        for coord in _residue_atom_coords(residue)
    ]
    if not atom_coords:
        return RadiusOfGyrationObservation(
            radius_of_gyration_angstrom=0.0,
            atom_count=0,
            notes=["NO_ATOMS_FOR_RADIUS_OF_GYRATION"],
        )

    center = (
        sum(coord[0] for coord in atom_coords) / len(atom_coords),
        sum(coord[1] for coord in atom_coords) / len(atom_coords),
        sum(coord[2] for coord in atom_coords) / len(atom_coords),
    )
    mean_squared_distance = sum(
        ((coord[0] - center[0]) ** 2)
        + ((coord[1] - center[1]) ** 2)
        + ((coord[2] - center[2]) ** 2)
        for coord in atom_coords
    ) / len(atom_coords)

    return RadiusOfGyrationObservation(
        radius_of_gyration_angstrom=round(sqrt(mean_squared_distance), 4),
        atom_count=len(atom_coords),
        notes=[],
    )


def build_descriptor_bundle(
    summary: StructureSummary,
    validation: StructureValidationResult,
    mode: PredictionMode,
    contact_observation: ContactObservation | None = None,
    solvent_accessibility: SolventAccessibilityObservation | None = None,
    residue_depth_observation: ResidueDepthObservation | None = None,
    radius_of_gyration_observation: RadiusOfGyrationObservation | None = None,
    contact_distance_cutoff: float = 5.5,
    trajectory_summary: Any | None = None,
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

    fallback_paired_apolar = min(partner_1_class_counts["apolar"], partner_2_class_counts["apolar"])
    fallback_paired_charged = min(partner_1_class_counts["charged"], partner_2_class_counts["charged"])
    fallback_paired_polar = min(partner_1_class_counts["polar"], partner_2_class_counts["polar"])
    fallback_contact_proxy = round(
        min(smaller_partner * 1.5, fallback_paired_apolar + fallback_paired_charged + fallback_paired_polar + 1),
        4,
    )

    if contact_observation is None:
        interface_contact_proxy = fallback_contact_proxy
        paired_apolar = float(fallback_paired_apolar)
        paired_charged = float(fallback_paired_charged)
        paired_polar = float(fallback_paired_polar)
        interface_residue_count = float(min(partner_residues.values()))
        contact_bins = {"AA": 0.0, "PP": 0.0, "CC": 0.0, "AP": 0.0, "CP": 0.0, "AC": 0.0}
        contact_notes: list[str] = ["CONTACTS_FROM_SUMMARY_PROXY"]
    else:
        interface_contact_proxy = float(contact_observation.total_contacts)
        paired_apolar = float(contact_observation.contact_bins.get("AA", 0))
        paired_charged = float(contact_observation.contact_bins.get("CC", 0))
        paired_polar = float(contact_observation.contact_bins.get("PP", 0))
        interface_residue_count = float(
            contact_observation.interface_residue_counts.get("partner_1", 0)
            + contact_observation.interface_residue_counts.get("partner_2", 0)
        )
        contact_bins = {
            key: float(value)
            for key, value in contact_observation.contact_bins.items()
        }
        contact_notes = list(contact_observation.notes)

    if solvent_accessibility is None:
        sasa_total = 0.0
        sasa_partner_1 = 0.0
        sasa_partner_2 = 0.0
        sasa_apolar_fraction = 0.0
        sasa_charged_fraction = 0.0
        sasa_polar_fraction = 0.0
        sasa_aromatic_fraction = 0.0
        accessible_residue_count = 0.0
        sasa_notes = ["SASA_NOT_COMPUTED"]
    else:
        sasa_total = float(solvent_accessibility.total_sasa)
        sasa_partner_1 = float(solvent_accessibility.partner_sasa.get("partner_1", 0.0))
        sasa_partner_2 = float(solvent_accessibility.partner_sasa.get("partner_2", 0.0))
        sasa_apolar_fraction = float(solvent_accessibility.class_sasa_fractions.get("apolar", 0.0))
        sasa_charged_fraction = float(solvent_accessibility.class_sasa_fractions.get("charged", 0.0))
        sasa_polar_fraction = float(solvent_accessibility.class_sasa_fractions.get("polar", 0.0))
        sasa_aromatic_fraction = float(solvent_accessibility.class_sasa_fractions.get("aromatic", 0.0))
        accessible_residue_count = float(solvent_accessibility.accessible_residue_count)
        sasa_notes = list(solvent_accessibility.notes)
        if sasa_total > 0.0:
            residue_class_fractions = dict(solvent_accessibility.class_sasa_fractions)

    if residue_depth_observation is None:
        residue_depth_partner_1_mean = 0.0
        residue_depth_partner_2_mean = 0.0
        residue_depth_interface_mean = 0.0
        residue_depth_non_interface_mean = 0.0
        interface_burial_delta = 0.0
        residue_depth_interface_count = 0.0
        residue_depth_notes = ["RESIDUE_DEPTH_NOT_COMPUTED"]
    else:
        residue_depth_partner_1_mean = float(
            residue_depth_observation.partner_depth_means.get("partner_1", 0.0)
        )
        residue_depth_partner_2_mean = float(
            residue_depth_observation.partner_depth_means.get("partner_2", 0.0)
        )
        residue_depth_interface_mean = float(residue_depth_observation.interface_depth_mean)
        residue_depth_non_interface_mean = float(residue_depth_observation.non_interface_depth_mean)
        interface_burial_delta = float(residue_depth_observation.interface_burial_delta)
        residue_depth_interface_count = float(residue_depth_observation.interface_residue_count)
        residue_depth_notes = list(residue_depth_observation.notes)

    if radius_of_gyration_observation is None:
        radius_of_gyration = 0.0
        radius_of_gyration_atom_count = 0.0
        radius_of_gyration_notes = ["RADIUS_OF_GYRATION_NOT_COMPUTED"]
    else:
        radius_of_gyration = float(radius_of_gyration_observation.radius_of_gyration_angstrom)
        radius_of_gyration_atom_count = float(radius_of_gyration_observation.atom_count)
        radius_of_gyration_notes = list(radius_of_gyration_observation.notes)

    antibody_candidate_count = float(
        _antibody_chain_candidate_count([*partner_1_chains, *partner_2_chains])
    )
    cdr_bookkeeping_ready_flag = (
        1.0 if mode == "antibody_antigen" and antibody_candidate_count > 0 else 0.0
    )
    electrostatics_hook_ready = 1.0 if validation.chain_groups is not None else 0.0
    surface_pka_hook_ready = 1.0 if validation.chain_groups is not None else 0.0

    descriptors = {
        "total_residues": float(total_residues),
        "contact_distance_cutoff_angstrom": round(float(contact_distance_cutoff), 3),
        "partner_1_residue_fraction": round(partner_residues["partner_1"] / total_residues, 4),
        "partner_2_residue_fraction": round(partner_residues["partner_2"] / total_residues, 4),
        "partner_size_ratio": round(smaller_partner / max(larger_partner, 1), 4),
        "interface_contact_proxy": interface_contact_proxy,
        "interface_density_proxy": round(interface_contact_proxy / total_residues, 4),
        "interface_residue_count": interface_residue_count,
        "paired_apolar_proxy": float(paired_apolar),
        "paired_charged_proxy": float(paired_charged),
        "paired_polar_proxy": float(paired_polar),
        "contact_bin_cc": contact_bins["CC"],
        "contact_bin_cp": contact_bins["CP"],
        "contact_bin_ac": contact_bins["AC"],
        "contact_bin_pp": contact_bins["PP"],
        "contact_bin_ap": contact_bins["AP"],
        "contact_bin_aa": contact_bins["AA"],
        "sasa_total": sasa_total,
        "sasa_partner_1": sasa_partner_1,
        "sasa_partner_2": sasa_partner_2,
        "sasa_partner_ratio": round(min(sasa_partner_1, sasa_partner_2) / max(max(sasa_partner_1, sasa_partner_2), 1.0), 4),
        "sasa_apolar_fraction": sasa_apolar_fraction,
        "sasa_charged_fraction": sasa_charged_fraction,
        "sasa_polar_fraction": sasa_polar_fraction,
        "sasa_aromatic_fraction": sasa_aromatic_fraction,
        "accessible_residue_count": accessible_residue_count,
        "residue_depth_partner_1_mean": residue_depth_partner_1_mean,
        "residue_depth_partner_2_mean": residue_depth_partner_2_mean,
        "residue_depth_interface_mean": residue_depth_interface_mean,
        "residue_depth_non_interface_mean": residue_depth_non_interface_mean,
        "interface_burial_delta": interface_burial_delta,
        "residue_depth_interface_count": residue_depth_interface_count,
        "radius_of_gyration_angstrom": radius_of_gyration,
        "radius_of_gyration_atom_count": radius_of_gyration_atom_count,
        "antibody_chain_candidate_count": antibody_candidate_count,
        "cdr_bookkeeping_ready_flag": cdr_bookkeeping_ready_flag,
        "electrostatics_hook_ready_flag": electrostatics_hook_ready,
        "surface_pka_hook_ready_flag": surface_pka_hook_ready,
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
    notes.extend(contact_notes)
    notes.extend(sasa_notes)
    notes.extend(residue_depth_notes)
    notes.extend(radius_of_gyration_notes)
    if mode == "antibody_antigen" and cdr_bookkeeping_ready_flag > 0.0:
        notes.append("ANTIBODY_MODE_CDR_DETECTION_PENDING")
    if electrostatics_hook_ready > 0.0 and surface_pka_hook_ready > 0.0:
        notes.append("ELECTROSTATICS_SURFACE_PKA_HOOKS_ENABLED")
    notes.append(f"CONTACT_DISTANCE_CUTOFF_{round(float(contact_distance_cutoff), 3)}A")

    # Phase 5B: thread trajectory-derived summaries into descriptor generation.
    if trajectory_summary is not None:
        from abby_api.services.trajectory import enrich_descriptors_from_trajectory
        descriptors, trajectory_notes = enrich_descriptors_from_trajectory(descriptors, trajectory_summary)
        notes.extend(trajectory_notes)

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