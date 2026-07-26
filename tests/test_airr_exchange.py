from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from abby_api.main import app
from abby_api.services.airr_exchange import serialize_cdr_annotation_to_airr
from abby_api.storage.object_store import ObjectStore

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-local-key"}

PDB_ANTIBODY_MOTIF_FIXTURE = """\
ATOM      1  N   CYS H   1      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  N   ALA H   2      12.560  13.102   9.262  1.00 20.00           N
ATOM      3  N   ALA H   3      13.030  11.670   9.634  1.00 20.00           N
ATOM      4  N   ALA H   4      12.284  10.719   9.434  1.00 20.00           N
ATOM      5  N   ALA H   5      14.300  11.500  10.100  1.00 20.00           N
ATOM      6  N   ALA H   6      14.900  10.170  10.420  1.00 20.00           N
ATOM      7  N   TRP H   7      16.350  10.200  10.900  1.00 20.00           N
ATOM      8  N   GLY H   8      17.020   9.180  10.810  1.00 20.00           N
ATOM      9  N   ALA H   9      18.200  10.700  11.400  1.00 20.00           N
ATOM     10  N   GLY H  10      19.100  10.900  12.500  1.00 20.00           N
ATOM     11  N   ALA A   1      19.900  12.100  12.900  1.00 20.00           N
TER
END
"""


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


def test_prediction_airr_export_endpoint_persists_signed_json_artifact() -> None:
    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "AIRR transport"},
    )
    assert project_response.status_code == 201, project_response.text

    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "airr_export_antibody.pdb",
                PDB_ANTIBODY_MOTIF_FIXTURE,
                "chemical/x-pdb",
            )
        },
        data={"mode": "antibody_antigen"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validation_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "antibody_antigen",
            "chains": {"partner_1": ["H"], "partner_2": ["A"]},
        },
    )
    assert validation_response.status_code == 200, validation_response.text
    assert validation_response.json()["valid"] is True

    prediction_response = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_response.json()["project_id"],
            "structure_id": structure_id,
            "mode": "antibody_antigen",
        },
    )
    assert prediction_response.status_code == 202, prediction_response.text
    prediction_id = prediction_response.json()["prediction_id"]

    before_export = client.get(
        f"/api/v1/predictions/{prediction_id}", headers=HEADERS
    )
    assert before_export.status_code == 200
    assert (
        before_export.json()["provenance"]["artifacts"].get("airr_cdr_export")
        is None
    )

    export_response = client.post(
        f"/api/v1/predictions/{prediction_id}/cdr:export-airr",
        headers=HEADERS,
        json={},
    )

    assert export_response.status_code == 201, export_response.text
    exported = export_response.json()
    assert exported["prediction_id"] == prediction_id
    assert exported["status"] == "exported"
    assert exported["schema_release"] == "2.0.0"
    assert exported["compliance"] == "partial"
    assert exported["record_count"] == 1
    assert len(exported["export_hash"]) == 64
    assert exported["artifact"]["artifact_type"] == "airr_cdr_export"
    assert exported["artifact"]["format"] == "json"
    assert exported["artifact"]["artifact_url"]

    artifact_key = exported["artifact"]["artifact_key"]
    payload_bytes = ObjectStore().get_bytes(artifact_key)
    assert payload_bytes is not None
    payload = json.loads(payload_bytes.decode("utf-8"))
    assert payload["abby_interop"]["export_hash"] == exported["export_hash"]
    assert payload["Rearrangement"][0]["sequence_id"] == f"{structure_id}:H"

    repeated_response = client.post(
        f"/api/v1/predictions/{prediction_id}/cdr:export-airr",
        headers=HEADERS,
        json={},
    )
    assert repeated_response.status_code == 201
    repeated = repeated_response.json()
    assert repeated["export_hash"] == exported["export_hash"]
    assert repeated["artifact"]["artifact_key"] == artifact_key
    assert ObjectStore().get_bytes(artifact_key) == payload_bytes

    after_export = client.get(
        f"/api/v1/predictions/{prediction_id}", headers=HEADERS
    )
    assert after_export.status_code == 200
    registered = after_export.json()["provenance"]["artifacts"]["airr_cdr_export"]
    assert registered["artifact_key"] == artifact_key


def test_prediction_airr_export_endpoint_rejects_unknown_prediction() -> None:
    response = client.post(
        f"/api/v1/predictions/{uuid4()}/cdr:export-airr",
        headers=HEADERS,
        json={},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Prediction not found."


def test_prediction_airr_export_endpoint_validates_locus_values() -> None:
    response = client.post(
        f"/api/v1/predictions/{uuid4()}/cdr:export-airr",
        headers=HEADERS,
        json={"chain_loci": {"H": "TRA"}},
    )

    assert response.status_code == 422
