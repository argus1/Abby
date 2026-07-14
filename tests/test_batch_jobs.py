from __future__ import annotations

import json
import time
from csv import DictReader
from io import StringIO
from uuid import UUID

from fastapi.testclient import TestClient

from abby_api.core.config import get_settings
from abby_api.main import app
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


def _upload_structure(filename: str) -> str:
    response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": (filename, PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "ppi_general"},
    )
    assert response.status_code == 201, response.text
    return response.json()["structure_id"]


def _validate_structure(structure_id: str) -> None:
    response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "ppi_general",
            "chains": {"partner_1": ["A"], "partner_2": ["B"]},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is True


def _create_project(name: str) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def _object_key_from_download_url(download_url: str) -> str:
    bucket = get_settings().object_storage_bucket.strip().strip("/")
    marker = f"/{bucket}/"
    assert marker in download_url, f"Expected bucket marker {marker} in {download_url}"
    return download_url.split(marker, 1)[1]


def _wait_for_job_terminal(job_id: str, timeout_seconds: float = 3.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/api/v1/batch-jobs/{job_id}", headers=HEADERS)
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(
        f"Batch job {job_id} did not reach a terminal state within {timeout_seconds}s"
    )


def test_batch_job_executes_predictions_and_produces_real_results_and_exports() -> None:
    project_id = _create_project("Batch execution success")
    structure_a = _upload_structure("batch_success_a.pdb")
    structure_b = _upload_structure("batch_success_b.pdb")
    _validate_structure(structure_a)
    _validate_structure(structure_b)

    create_response = client.post(
        "/api/v1/batch-jobs",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "mode": "ppi_general",
            "structure_ids": [structure_a, structure_b],
            "options": {
                "include_explainability": True,
                "return_all_models": True,
                "contact_distance_cutoff_angstrom": 6.0,
            },
        },
    )
    assert create_response.status_code == 202, create_response.text
    job_id = create_response.json()["job_id"]

    job = _wait_for_job_terminal(job_id)
    assert job["status"] == "completed"
    assert job["counts"]["completed"] == 2
    assert job["counts"]["failed"] == 0

    results_response = client.get(
        f"/api/v1/batch-jobs/{job_id}/results?page=1&page_size=10", headers=HEADERS
    )
    assert results_response.status_code == 200, results_response.text
    results = results_response.json()
    assert results["total"] == 2
    assert len(results["items"]) == 2
    assert {item["status"] for item in results["items"]} == {"completed"}
    assert {
        item["provenance"]["contact_distance_cutoff_angstrom"]
        for item in results["items"]
        if item.get("provenance")
    } == {6.0}

    csv_export_response = client.get(
        f"/api/v1/batch-jobs/{job_id}/export?format=csv", headers=HEADERS
    )
    json_export_response = client.get(
        f"/api/v1/batch-jobs/{job_id}/export?format=json", headers=HEADERS
    )
    assert csv_export_response.status_code == 200, csv_export_response.text
    assert json_export_response.status_code == 200, json_export_response.text

    object_store = ObjectStore()
    csv_key = _object_key_from_download_url(csv_export_response.json()["download_url"])
    json_key = _object_key_from_download_url(json_export_response.json()["download_url"])
    assert object_store.exists(csv_key)
    assert object_store.exists(json_key)

    json_payload_raw = object_store.get_bytes(json_key)
    csv_payload_raw = object_store.get_bytes(csv_key)
    assert json_payload_raw is not None
    assert csv_payload_raw is not None

    csv_rows = list(DictReader(StringIO(csv_payload_raw.decode("utf-8"))))
    assert len(csv_rows) == 2
    assert {row["structure_id"] for row in csv_rows} == {structure_a, structure_b}
    assert {row["status"] for row in csv_rows} == {"completed"}

    json_payload = json.loads(json_payload_raw.decode("utf-8"))
    assert json_payload["job_id"] == job_id
    assert len(json_payload["predictions"]) == 2
    assert {item["structure_id"] for item in json_payload["predictions"]} == {
        structure_a,
        structure_b,
    }
    assert json_payload["failures"] == []


def test_batch_job_tracks_partial_failures_without_losing_successful_results() -> None:
    project_id = _create_project("Batch partial failure")
    validated_structure = _upload_structure("batch_partial_ok.pdb")
    unvalidated_structure = _upload_structure("batch_partial_fail.pdb")
    _validate_structure(validated_structure)

    create_response = client.post(
        "/api/v1/batch-jobs",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "mode": "ppi_general",
            "structure_ids": [validated_structure, unvalidated_structure],
        },
    )
    assert create_response.status_code == 202, create_response.text
    job_id = create_response.json()["job_id"]

    job = _wait_for_job_terminal(job_id)
    assert job["status"] == "completed"
    assert job["counts"]["completed"] == 1
    assert job["counts"]["failed"] == 1

    results_response = client.get(
        f"/api/v1/batch-jobs/{job_id}/results?page=1&page_size=10", headers=HEADERS
    )
    assert results_response.status_code == 200, results_response.text
    results = results_response.json()
    assert results["total"] == 1
    assert len(results["items"]) == 1

    prediction_id = results["items"][0]["prediction_id"]
    prediction_response = client.get(f"/api/v1/predictions/{prediction_id}", headers=HEADERS)
    assert prediction_response.status_code == 200, prediction_response.text
    assert prediction_response.json()["status"] == "completed"

    csv_export_response = client.get(
        f"/api/v1/batch-jobs/{job_id}/export?format=csv", headers=HEADERS
    )
    json_export_response = client.get(
        f"/api/v1/batch-jobs/{job_id}/export?format=json", headers=HEADERS
    )
    assert csv_export_response.status_code == 200, csv_export_response.text
    assert json_export_response.status_code == 200, json_export_response.text

    object_store = ObjectStore()
    csv_key = _object_key_from_download_url(csv_export_response.json()["download_url"])
    json_key = _object_key_from_download_url(json_export_response.json()["download_url"])

    csv_payload_raw = object_store.get_bytes(csv_key)
    json_payload_raw = object_store.get_bytes(json_key)
    assert csv_payload_raw is not None
    assert json_payload_raw is not None

    csv_rows = list(DictReader(StringIO(csv_payload_raw.decode("utf-8"))))
    assert len(csv_rows) == 2
    assert {row["status"] for row in csv_rows} == {"completed", "failed"}
    failed_rows = [row for row in csv_rows if row["status"] == "failed"]
    assert len(failed_rows) == 1
    assert failed_rows[0]["structure_id"] == unvalidated_structure
    assert "validated successfully" in failed_rows[0]["error"]

    json_payload = json.loads(json_payload_raw.decode("utf-8"))
    assert len(json_payload["predictions"]) == 1
    assert json_payload["predictions"][0]["structure_id"] == validated_structure
    assert len(json_payload["failures"]) == 1
    assert json_payload["failures"][0]["structure_id"] == unvalidated_structure

    assert UUID(job_id)
