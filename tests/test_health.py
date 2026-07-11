from __future__ import annotations

from fastapi.testclient import TestClient

from abby_api.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "dependencies" in body
    dependency_names = {item["name"] for item in body["dependencies"]}
    assert {"BioPython", "Gemmi", "MDAnalysis", "freesasa", "Gromacs-CIF"}.issubset(dependency_names)
