from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from abby_api.services.airr_exchange import serialize_cdr_annotation_to_airr


def _numbered_heavy_annotation() -> dict[str, object]:
    residue_keys = [
        {"chain_id": "H", "sequence_id": str(sequence_id), "insertion_code": ""}
        for sequence_id in range(95, 103)
    ]
    return {
        "available": True,
        "antibody_format": "vhh_single_domain",
        "scheme": "kabat",
        "numbering_scheme": "kabat",
        "boundary_source": "numbered",
        "boundary_confidence": "high",
        "boundary_evidence": ["numbering_interval_match"],
        "annotation_toolchain": {
            "engine_name": "CompDetRAE",
            "engine_version": "0.1.0",
            "parameters_hash": "a" * 64,
            "reference_data_version": None,
        },
        "interop_profile": "abby_structural_v1_1",
        "selected_heavy_chain": "H",
        "chains": {
            "H": {
                "role": "heavy",
                "confidence": "high",
                "scheme": "kabat",
                "completeness_score": 1.0,
                "residue_count": 130,
                "regions": {
                    "CDR-H3": {
                        "start_index": 94,
                        "end_index": 101,
                        "length": 8,
                        "start_residue": residue_keys[0],
                        "end_residue": residue_keys[-1],
                        "residue_keys": residue_keys,
                    }
                },
            }
        },
        "region_applicability": {
            "CDR-H1": "applicable",
            "CDR-H2": "applicable",
            "CDR-H3": "applicable",
            "CDR-L1": "not_applicable",
            "CDR-L2": "not_applicable",
            "CDR-L3": "not_applicable",
        },
        "warnings": [],
    }


def test_serializer_emits_pinned_airr_datafile_with_structural_extension() -> None:
    sequence = "A" * 94 + "CARDRSTY" + "A" * 28

    serialized = serialize_cdr_annotation_to_airr(
        _numbered_heavy_annotation(),
        structure_id="structure-123",
        chain_amino_acid_sequences={"H": sequence},
        chain_loci={"H": "IGH"},
    )
    payload = json.loads(serialized)

    assert payload["Info"]["title"] == "Abby CompDetRAE AIRR structural CDR export"
    assert payload["Info"]["version"] == "2.0.0"
    assert payload["abby_interop"]["schema_release"] == "2.0.0"
    assert payload["abby_interop"]["schema_object"] == "Rearrangement"
    assert payload["abby_interop"]["compliance"] == "partial"

    record = payload["Rearrangement"][0]
    assert record["sequence_id"] == "structure-123:H"
    assert record["sequence_aa"] == sequence
    assert record["locus"] == "IGH"
    assert record["cdr3_aa"] == "CARDRSTY"
    assert "cdr3_start" not in record
    assert "cdr3_end" not in record
    assert record["data_processing_id"] == "abby-compdetrae-aaaaaaaaaaaa"
    assert record["x_abby_structural_annotation"]["source_authority"] == (
        "abby_structure_annotation"
    )
    assert record["x_abby_structural_annotation"]["regions"]["CDR-H3"][
        "start_index_1based"
    ] == 95
    assert record["x_abby_structural_annotation"]["regions"]["CDR-H3"][
        "end_index_1based"
    ] == 102
    assert "sequence" in record["x_abby_structural_annotation"]["missing_airr_required_fields"]


def test_airr_serialization_and_export_hash_are_deterministic() -> None:
    kwargs = {
        "structure_id": "structure-123",
        "chain_amino_acid_sequences": {"H": "A" * 130},
        "chain_loci": {"H": "IGH"},
    }

    first = serialize_cdr_annotation_to_airr(_numbered_heavy_annotation(), **kwargs)
    second = serialize_cdr_annotation_to_airr(_numbered_heavy_annotation(), **kwargs)

    assert first == second
    first_payload = json.loads(first)
    export_hash = first_payload["abby_interop"].pop("export_hash")
    canonical_payload = json.dumps(first_payload, sort_keys=True, separators=(",", ":"))
    assert export_hash == hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def test_airr_serializer_rejects_unpinned_schema_release() -> None:
    with pytest.raises(ValueError, match="only '2.0.0' is pinned"):
        serialize_cdr_annotation_to_airr(
            _numbered_heavy_annotation(),
            structure_id="structure-123",
            schema_release="1.6.1",
        )


def test_airr_serializer_rejects_unavailable_annotation() -> None:
    unavailable = _numbered_heavy_annotation()
    unavailable["available"] = False

    with pytest.raises(ValueError, match="cdr_annotation.available=true"):
        serialize_cdr_annotation_to_airr(
            unavailable,
            structure_id="structure-123",
        )


def test_airr_serializer_does_not_infer_sequence_or_locus_from_chain_role() -> None:
    payload = json.loads(
        serialize_cdr_annotation_to_airr(
            _numbered_heavy_annotation(),
            structure_id="structure-123",
        )
    )

    record = payload["Rearrangement"][0]
    extension = record["x_abby_structural_annotation"]
    assert "sequence" not in record
    assert "sequence_aa" not in record
    assert "locus" not in record
    assert "cdr3_aa" not in record
    assert "AIRR_AMINO_ACID_SEQUENCE_NOT_PROVIDED" in extension["conversion_warnings"]
    assert "AIRR_LOCUS_EVIDENCE_NOT_PROVIDED" in extension["conversion_warnings"]
    assert "AIRR_NUCLEOTIDE_COORDINATES_NOT_EMITTED" in extension["conversion_warnings"]


def test_airr_serializer_preserves_insertion_codes_and_hybrid_boundary_provenance() -> None:
    annotation = _numbered_heavy_annotation()
    annotation["boundary_source"] = "hybrid"
    annotation["boundary_confidence"] = "medium"
    annotation["boundary_evidence"] = [
        "numbering_interval_match",
        "conserved_anchor_match",
        "insertion_code_normalized",
    ]
    chains = annotation["chains"]
    assert isinstance(chains, dict)
    residue_keys = chains["H"]["regions"]["CDR-H3"]["residue_keys"]
    residue_keys[1]["insertion_code"] = "A"

    payload = json.loads(
        serialize_cdr_annotation_to_airr(
            annotation,
            structure_id="structure-123",
        )
    )
    extension = payload["Rearrangement"][0]["x_abby_structural_annotation"]

    assert extension["boundary_source"] == "hybrid"
    assert extension["regions"]["CDR-H3"]["residue_keys"][1]["insertion_code"] == "A"
    assert "AIRR_INSERTION_CODES_PRESERVED_IN_ABBY_EXTENSION" in (
        extension["conversion_warnings"]
    )
    assert "AIRR_STRUCTURAL_MOTIF_BOUNDARY_RECORDED" in extension["conversion_warnings"]


def test_airr_serializer_emits_sorted_heavy_and_light_chain_records() -> None:
    annotation = _numbered_heavy_annotation()
    annotation["antibody_format"] = "paired_antibody"
    chains = annotation["chains"]
    assert isinstance(chains, dict)
    light_region = deepcopy(chains["H"]["regions"]["CDR-H3"])
    light_region["start_index"] = 23
    light_region["end_index"] = 30
    light_region["start_residue"]["chain_id"] = "K"
    light_region["end_residue"]["chain_id"] = "K"
    for residue_key in light_region["residue_keys"]:
        residue_key["chain_id"] = "K"
    chains["K"] = {
        "role": "light_kappa",
        "confidence": "high",
        "scheme": "kabat",
        "completeness_score": 1.0,
        "residue_count": 110,
        "regions": {"CDR-L1": light_region},
    }

    payload = json.loads(
        serialize_cdr_annotation_to_airr(
            annotation,
            structure_id="structure-123",
            chain_amino_acid_sequences={"H": "A" * 130, "K": "A" * 23 + "KAPPAONE" + "A" * 79},
            chain_loci={"H": "IGH", "K": "IGK"},
        )
    )

    records = payload["Rearrangement"]
    assert [record["sequence_id"] for record in records] == [
        "structure-123:H",
        "structure-123:K",
    ]
    assert records[0]["locus"] == "IGH"
    assert records[1]["locus"] == "IGK"
    assert records[1]["cdr1_aa"] == "KAPPAONE"
