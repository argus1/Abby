from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from abby_api.schemas.common import CDRAnnotationProvenance

AIRR_SCHEMA_RELEASE = "2.0.0"
AIRR_SCHEMA_OBJECT = "Rearrangement"
AIRR_SCHEMA_SOURCE = (
    "https://raw.githubusercontent.com/airr-community/airr-standards/"
    "v2.0.0/specs/airr-schema.yaml"
)
AIRR_COORDINATE_SYSTEM = "1-based closed nucleotide query coordinates"

AIRRLocus = Literal["IGH", "IGI", "IGK", "IGL"]
_AIRR_LOCI = {"IGH", "IGI", "IGK", "IGL"}
_AIRR_REARRANGEMENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "sequence_id",
    "sequence",
    "rev_comp",
    "productive",
    "v_call",
    "d_call",
    "j_call",
    "sequence_alignment",
    "germline_alignment",
    "junction",
    "junction_aa",
    "v_cigar",
    "d_cigar",
    "j_cigar",
)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _normalize_sequences(
    chain_amino_acid_sequences: Mapping[str, str] | None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for chain_id, sequence in (chain_amino_acid_sequences or {}).items():
        normalized_chain_id = str(chain_id).strip()
        normalized_sequence = str(sequence).strip().upper()
        if not normalized_chain_id:
            raise ValueError("AIRR export chain sequence keys must be non-empty.")
        if not normalized_sequence:
            raise ValueError(
                f"AIRR export amino-acid sequence for chain {normalized_chain_id!r} is empty."
            )
        normalized[normalized_chain_id] = normalized_sequence
    return normalized


def _normalize_loci(chain_loci: Mapping[str, str] | None) -> dict[str, AIRRLocus]:
    normalized: dict[str, AIRRLocus] = {}
    for chain_id, locus in (chain_loci or {}).items():
        normalized_chain_id = str(chain_id).strip()
        normalized_locus = str(locus).strip().upper()
        if not normalized_chain_id:
            raise ValueError("AIRR export locus keys must be non-empty.")
        if normalized_locus not in _AIRR_LOCI:
            raise ValueError(
                f"Unsupported AIRR locus {normalized_locus!r} for chain "
                f"{normalized_chain_id!r}."
            )
        normalized[normalized_chain_id] = normalized_locus  # type: ignore[assignment]
    return normalized


def _region_number(region_name: str, chain_role: str) -> int | None:
    expected_prefix = "CDR-H" if chain_role == "heavy" else "CDR-L"
    if not region_name.startswith(expected_prefix):
        return None
    try:
        number = int(region_name[-1])
    except ValueError:
        return None
    return number if number in {1, 2, 3} else None


def _structural_region_payload(
    region_name: str,
    region_payload: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        start_index = int(region_payload["start_index"])
        end_index = int(region_payload["end_index"])
        length = int(region_payload["length"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"CDR region {region_name} has invalid index metadata.") from exc

    if start_index < 0 or end_index < start_index or length != (end_index - start_index) + 1:
        raise ValueError(f"CDR region {region_name} has inconsistent index metadata.")

    return {
        "start_index_1based": start_index + 1,
        "end_index_1based": end_index + 1,
        "length_amino_acids": length,
        "start_residue": region_payload.get("start_residue"),
        "end_residue": region_payload.get("end_residue"),
        "residue_keys": list(region_payload.get("residue_keys", [])),
    }


def _record_for_chain(
    *,
    structure_id: str,
    chain_id: str,
    chain_payload: Mapping[str, Any],
    annotation: CDRAnnotationProvenance,
    amino_acid_sequence: str | None,
    locus: AIRRLocus | None,
) -> dict[str, Any]:
    role = str(chain_payload.get("role", "unknown"))
    regions = chain_payload.get("regions", {})
    if not isinstance(regions, Mapping):
        raise ValueError(f"CDR regions for chain {chain_id!r} must be a mapping.")

    record: dict[str, Any] = {
        "sequence_id": f"{structure_id}:{chain_id}",
    }
    if amino_acid_sequence is not None:
        record["sequence_aa"] = amino_acid_sequence
    if locus is not None:
        record["locus"] = locus

    parameters_hash = (
        annotation.annotation_toolchain.parameters_hash
        if annotation.annotation_toolchain is not None
        else None
    )
    if parameters_hash:
        record["data_processing_id"] = f"abby-compdetrae-{parameters_hash[:12]}"

    structural_regions: dict[str, dict[str, Any]] = {}
    conversion_warnings: list[str] = []
    for region_name in sorted(str(item) for item in regions):
        region_payload = regions[region_name]
        if not isinstance(region_payload, Mapping):
            raise ValueError(f"CDR region {region_name} for chain {chain_id!r} is invalid.")
        number = _region_number(region_name, role)
        if number is None:
            continue

        structural_region = _structural_region_payload(region_name, region_payload)
        structural_regions[region_name] = structural_region
        if amino_acid_sequence is not None:
            start_index = int(structural_region["start_index_1based"]) - 1
            end_index = int(structural_region["end_index_1based"])
            if end_index > len(amino_acid_sequence):
                raise ValueError(
                    f"CDR region {region_name} exceeds amino-acid sequence length "
                    f"for chain {chain_id!r}."
                )
            record[f"cdr{number}_aa"] = amino_acid_sequence[start_index:end_index]

        if any(
            bool(residue_key.get("insertion_code"))
            for residue_key in structural_region["residue_keys"]
            if isinstance(residue_key, Mapping)
        ):
            conversion_warnings.append("AIRR_INSERTION_CODES_PRESERVED_IN_ABBY_EXTENSION")

    missing_required_fields = [
        field_name
        for field_name in _AIRR_REARRANGEMENT_REQUIRED_FIELDS
        if field_name not in record
    ]
    if amino_acid_sequence is None:
        conversion_warnings.append("AIRR_AMINO_ACID_SEQUENCE_NOT_PROVIDED")
    if locus is None:
        conversion_warnings.append("AIRR_LOCUS_EVIDENCE_NOT_PROVIDED")
    conversion_warnings.append("AIRR_NUCLEOTIDE_COORDINATES_NOT_EMITTED")
    if annotation.boundary_source in {"motif_fallback", "hybrid"}:
        conversion_warnings.append("AIRR_STRUCTURAL_MOTIF_BOUNDARY_RECORDED")

    record["x_abby_structural_annotation"] = {
        "source_authority": "abby_structure_annotation",
        "chain_id": chain_id,
        "chain_role": role,
        "numbering_scheme": annotation.numbering_scheme or annotation.scheme,
        "boundary_source": annotation.boundary_source,
        "boundary_confidence": annotation.boundary_confidence,
        "boundary_evidence": list(annotation.boundary_evidence),
        "annotation_toolchain": (
            annotation.annotation_toolchain.model_dump(mode="json")
            if annotation.annotation_toolchain is not None
            else None
        ),
        "interop_profile": annotation.interop_profile,
        "regions": structural_regions,
        "missing_airr_required_fields": missing_required_fields,
        "conversion_warnings": sorted(set(conversion_warnings)),
    }
    return record


def build_airr_cdr_export(
    cdr_annotation: CDRAnnotationProvenance | Mapping[str, Any],
    *,
    structure_id: str,
    chain_amino_acid_sequences: Mapping[str, str] | None = None,
    chain_loci: Mapping[str, str] | None = None,
    schema_release: str = AIRR_SCHEMA_RELEASE,
) -> dict[str, Any]:
    """Build an optional AIRR DataFile-like structural CDR export.

    The pinned AIRR Rearrangement schema requires nucleotide rearrangement and
    germline-alignment fields that structural annotation cannot truthfully infer.
    The export therefore declares partial compliance and records every absent
    required field instead of fabricating repertoire evidence.
    """

    if schema_release != AIRR_SCHEMA_RELEASE:
        raise ValueError(
            f"Unsupported AIRR schema release {schema_release!r}; "
            f"only {AIRR_SCHEMA_RELEASE!r} is pinned."
        )
    normalized_structure_id = str(structure_id).strip()
    if not normalized_structure_id:
        raise ValueError("AIRR export requires a non-empty structure_id.")

    annotation = CDRAnnotationProvenance.model_validate(cdr_annotation)
    if not annotation.available:
        raise ValueError("AIRR export requires cdr_annotation.available=true.")

    sequences = _normalize_sequences(chain_amino_acid_sequences)
    loci = _normalize_loci(chain_loci)
    records: list[dict[str, Any]] = []
    for chain_id in sorted(annotation.chains):
        chain_payload = annotation.chains[chain_id]
        role = str(chain_payload.get("role", "unknown"))
        if role != "heavy" and not role.startswith("light"):
            continue
        records.append(
            _record_for_chain(
                structure_id=normalized_structure_id,
                chain_id=chain_id,
                chain_payload=chain_payload,
                annotation=annotation,
                amino_acid_sequence=sequences.get(chain_id),
                locus=loci.get(chain_id),
            )
        )

    if not records:
        raise ValueError("AIRR export found no annotated heavy or light chains.")

    payload: dict[str, Any] = {
        "Info": {
            "title": "Abby CompDetRAE AIRR structural CDR export",
            "version": AIRR_SCHEMA_RELEASE,
            "description": (
                "Partial AIRR Rearrangement exchange profile generated from "
                "structure-authoritative Abby CDR annotations."
            ),
        },
        "Rearrangement": records,
        "abby_interop": {
            "schema_release": AIRR_SCHEMA_RELEASE,
            "schema_source": AIRR_SCHEMA_SOURCE,
            "schema_object": AIRR_SCHEMA_OBJECT,
            "coordinate_system": AIRR_COORDINATE_SYSTEM,
            "compliance": "partial",
            "authoritative_source": "abby_structure_annotation",
            "default_prediction_flow_enabled": False,
        },
    }
    payload["abby_interop"]["export_hash"] = hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return payload


def serialize_cdr_annotation_to_airr(
    cdr_annotation: CDRAnnotationProvenance | Mapping[str, Any],
    *,
    structure_id: str,
    chain_amino_acid_sequences: Mapping[str, str] | None = None,
    chain_loci: Mapping[str, str] | None = None,
    schema_release: str = AIRR_SCHEMA_RELEASE,
) -> str:
    """Serialize an Abby CDR annotation to deterministic AIRR v2.0.0 JSON."""

    payload = build_airr_cdr_export(
        cdr_annotation,
        structure_id=structure_id,
        chain_amino_acid_sequences=chain_amino_acid_sequences,
        chain_loci=chain_loci,
        schema_release=schema_release,
    )
    return _canonical_json(payload)
