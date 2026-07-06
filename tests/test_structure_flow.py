from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from abby_api.main import app
from abby_api.repositories.memory import get_feature_summary_artifact
from abby_api.storage.object_store import ObjectStore

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-local-key"}

PDB_FIXTURE = """\
ATOM      1  N   GLY A   1      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  CA  GLY A   1      12.560  13.102   9.262  1.00 20.00           C
ATOM      3  C   GLY A   1      13.030  11.670   9.634  1.00 20.00           C
ATOM      4  O   GLY A   1      12.284  10.719   9.434  1.00 20.00           O
ATOM      5  N   ALA B   1      14.300  11.500  10.100  1.00 20.00           N
ATOM      6  CA  ALA B   1      14.900  10.170  10.420  1.00 20.00           C
ATOM      7  C   ALA B   1      16.350  10.200  10.900  1.00 20.00           C
ATOM      8  O   ALA B   1      17.020   9.180  10.810  1.00 20.00           O
TER
END
"""

PDB_UNSUPPORTED_RESIDUE_FIXTURE = """\
ATOM      1  N   MSE A   1      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  CA  MSE A   1      12.560  13.102   9.262  1.00 20.00           C
ATOM      3  C   MSE A   1      13.030  11.670   9.634  1.00 20.00           C
ATOM      4  O   MSE A   1      12.284  10.719   9.434  1.00 20.00           O
ATOM      5  N   ALA B   1      14.300  11.500  10.100  1.00 20.00           N
ATOM      6  CA  ALA B   1      14.900  10.170  10.420  1.00 20.00           C
ATOM      7  C   ALA B   1      16.350  10.200  10.900  1.00 20.00           C
ATOM      8  O   ALA B   1      17.020   9.180  10.810  1.00 20.00           O
TER
END
"""


def test_structure_upload_validate_and_fetch() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex.pdb", PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "ppi_general"},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    assert uploaded["format"] == "pdb"

    structure_id = uploaded["structure_id"]
    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "ppi_general",
            "chains": {"partner_1": ["A"], "partner_2": ["B"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation = validate_response.json()
    assert validation["valid"] is True
    assert validation["available_chains"] == ["A", "B"]
    assert validation["partner_residue_counts"]["partner_1"] == 1
    assert validation["partner_residue_counts"]["partner_2"] == 1
    assert validation["warning_details"] == []
    assert validation["error_details"] == []

    detail_response = client.get(f"/api/v1/structures/{structure_id}", headers=HEADERS)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["summary"]["parser_name"] == "PDBParser"
    assert detail["summary"]["metadata"]["global_residue_class_counts"]["apolar"] == 2
    assert detail["summary"]["metadata"]["chain_residue_class_counts"]["A"]["apolar"] == 1
    assert detail["summary"]["warning_details"] == []
    assert detail["validation"]["valid"] is True


def test_structure_validation_reports_typed_error_details() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex_validation_errors.pdb", PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "ppi_general"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "ppi_general",
            "chains": {"partner_1": ["A", "Z"], "partner_2": ["A"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    payload = validate_response.json()
    assert payload["valid"] is False
    assert set(payload["errors"]) == {"CHAIN_GROUP_OVERLAP", "UNKNOWN_CHAIN_SELECTION"}

    error_details_by_code = {entry["code"]: entry for entry in payload["error_details"]}
    assert sorted(error_details_by_code["CHAIN_GROUP_OVERLAP"]["details"]["overlap"]) == ["A"]
    assert sorted(error_details_by_code["UNKNOWN_CHAIN_SELECTION"]["details"]["missing_chains"]) == ["Z"]


def test_structure_validation_propagates_unsupported_residue_warning() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "test_complex_unsupported_residue.pdb",
                PDB_UNSUPPORTED_RESIDUE_FIXTURE,
                "chemical/x-pdb",
            )
        },
        data={"mode": "antibody_antigen"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "antibody_antigen",
            "chains": {"partner_1": ["A"], "partner_2": ["B"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    payload = validate_response.json()
    assert payload["valid"] is True
    assert "UNSUPPORTED_RESIDUE" in payload["warnings"]

    warning_details_by_code = {entry["code"]: entry for entry in payload["warning_details"]}
    assert warning_details_by_code["UNSUPPORTED_RESIDUE"]["details"]["unsupported_residue_counts"]["A"]["MSE"] == 1


def test_prediction_requires_validation_before_success() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex_unvalidated.pdb", PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "ppi_general"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "Prediction validation test"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    before_validation = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "ppi_general",
            "options": {"include_explainability": True, "return_all_models": True},
        },
    )
    assert before_validation.status_code == 400, before_validation.text

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "ppi_general",
            "chains": {"partner_1": ["A"], "partner_2": ["B"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text

    after_validation = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "ppi_general",
            "options": {"include_explainability": True, "return_all_models": True},
        },
    )
    assert after_validation.status_code == 202, after_validation.text
    queued = after_validation.json()
    assert queued["status"] == "queued"

    prediction_response = client.get(
        f"/api/v1/predictions/{queued['prediction_id']}",
        headers=HEADERS,
    )
    assert prediction_response.status_code == 200, prediction_response.text
    prediction = prediction_response.json()
    assert prediction["status"] == "completed"
    assert prediction["consensus"]["log_k"] is not None
    assert prediction["best_model"]["model_id"] == "mixed_baseline_v1"
    assert len(prediction["all_models"]) == 3
    assert prediction["feature_summary"]["source"] == "parsed_structure_summary"
    assert prediction["feature_summary"]["artifact_key"]
    assert prediction["feature_summary"]["artifact_url"]
    assert prediction["feature_summary"]["descriptors"]["interface_contact_proxy"] >= 1.0
    assert prediction["feature_summary"]["descriptors"]["interface_residue_count"] >= 2.0
    assert prediction["feature_summary"]["descriptors"]["contact_bin_cc"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["contact_bin_cp"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["contact_bin_ac"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["contact_bin_pp"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["contact_bin_ap"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["contact_bin_aa"] >= 0.0
    contact_sum = (
        prediction["feature_summary"]["descriptors"]["contact_bin_cc"]
        + prediction["feature_summary"]["descriptors"]["contact_bin_cp"]
        + prediction["feature_summary"]["descriptors"]["contact_bin_ac"]
        + prediction["feature_summary"]["descriptors"]["contact_bin_pp"]
        + prediction["feature_summary"]["descriptors"]["contact_bin_ap"]
        + prediction["feature_summary"]["descriptors"]["contact_bin_aa"]
    )
    assert contact_sum == prediction["feature_summary"]["descriptors"]["interface_contact_proxy"]
    assert prediction["feature_summary"]["descriptors"]["sasa_total"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["sasa_partner_1"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["sasa_partner_2"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["sasa_partner_ratio"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["sasa_partner_ratio"] <= 1.0
    assert prediction["feature_summary"]["descriptors"]["sasa_apolar_fraction"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["sasa_charged_fraction"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["sasa_polar_fraction"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["sasa_aromatic_fraction"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["accessible_residue_count"] >= 0.0
    assert prediction["feature_summary"]["partner_residues"]["partner_1"] == 1
    assert prediction["provenance"]["descriptor_hash"]
    assert prediction["provenance"]["contact_distance_cutoff_angstrom"] == 5.5

    record = get_feature_summary_artifact(UUID(queued["prediction_id"]))
    assert record is not None
    assert record.descriptor_hash == prediction["provenance"]["descriptor_hash"]
    assert record.artifact_key == prediction["feature_summary"]["artifact_key"]
    assert ObjectStore().exists(record.artifact_key)


def test_feature_bundle_is_deterministic_for_same_structure() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex_repeatable.pdb", PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "antibody_antigen"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "antibody_antigen",
            "chains": {"partner_1": ["A"], "partner_2": ["B"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "Deterministic features test"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    queued_prediction_ids: list[str] = []
    for _ in range(2):
        prediction_response = client.post(
            "/api/v1/predictions",
            headers=HEADERS,
            json={
                "project_id": project_id,
                "structure_id": structure_id,
                "mode": "antibody_antigen",
                "options": {"include_explainability": True, "return_all_models": True},
            },
        )
        assert prediction_response.status_code == 202, prediction_response.text
        queued_prediction_ids.append(prediction_response.json()["prediction_id"])

    fetched_predictions = []
    for prediction_id in queued_prediction_ids:
        fetched = client.get(f"/api/v1/predictions/{prediction_id}", headers=HEADERS)
        assert fetched.status_code == 200, fetched.text
        fetched_predictions.append(fetched.json())

    first, second = fetched_predictions
    assert first["feature_summary"]["descriptors"] == second["feature_summary"]["descriptors"]
    assert first["provenance"]["descriptor_hash"] == second["provenance"]["descriptor_hash"]
    assert first["explainability"]["top_descriptors"] == second["explainability"]["top_descriptors"]


def test_prediction_contact_cutoff_is_configurable() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex_cutoff.pdb", PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "ppi_general"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "ppi_general",
            "chains": {"partner_1": ["A"], "partner_2": ["B"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "Contact cutoff test"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    response_low = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "ppi_general",
            "options": {
                "include_explainability": True,
                "return_all_models": True,
                "contact_distance_cutoff_angstrom": 0.5,
            },
        },
    )
    assert response_low.status_code == 202, response_low.text

    response_high = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "ppi_general",
            "options": {
                "include_explainability": True,
                "return_all_models": True,
                "contact_distance_cutoff_angstrom": 8.0,
            },
        },
    )
    assert response_high.status_code == 202, response_high.text

    low_pred = client.get(
        f"/api/v1/predictions/{response_low.json()['prediction_id']}",
        headers=HEADERS,
    )
    high_pred = client.get(
        f"/api/v1/predictions/{response_high.json()['prediction_id']}",
        headers=HEADERS,
    )
    assert low_pred.status_code == 200, low_pred.text
    assert high_pred.status_code == 200, high_pred.text

    low_payload = low_pred.json()
    high_payload = high_pred.json()
    low_descriptors = low_payload["feature_summary"]["descriptors"]
    high_descriptors = high_payload["feature_summary"]["descriptors"]

    assert low_descriptors["contact_distance_cutoff_angstrom"] == 0.5
    assert high_descriptors["contact_distance_cutoff_angstrom"] == 8.0
    assert low_descriptors["interface_contact_proxy"] <= high_descriptors["interface_contact_proxy"]
    assert low_payload["provenance"]["descriptor_hash"] != high_payload["provenance"]["descriptor_hash"]
    assert low_payload["provenance"]["contact_distance_cutoff_angstrom"] == 0.5
    assert high_payload["provenance"]["contact_distance_cutoff_angstrom"] == 8.0
