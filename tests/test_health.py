from __future__ import annotations

from typing import Any, Sequence

import pytest
from fastapi.testclient import TestClient

from abby_api.main import app
from abby_api.services.cdr_telemetry import reset_cdr_annotation_telemetry
from abby_api.services.structure_parsing import (
    _SimpleModel,
    _SimpleStructure,
    summarize_structure,
)

client = TestClient(app)


def _residue(sequence_id: int, residue_name: str, insertion_code: str = " "):
    return type(
        "Residue",
        (),
        {
            "id": (" ", sequence_id, insertion_code),
            "get_resname": lambda self: residue_name,
        },
    )()


def _chain(chain_id: str, residues: Sequence[Any]):
    return type(
        "Chain",
        (),
        {
            "id": chain_id,
            "get_residues": lambda self: iter(residues),
        },
    )()


def _structure(chains: Sequence[Any]):
    return _SimpleStructure(id="test", _models=[_SimpleModel(id=0, _chains=list(chains))])


def test_health_endpoint() -> None:
    reset_cdr_annotation_telemetry()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "dependencies" in body
    assert "capabilities" in body
    dependency_names = {item["name"] for item in body["dependencies"]}
    assert {"BioPython", "Gemmi", "MDAnalysis", "freesasa", "Gromacs-CIF"}.issubset(
        dependency_names
    )
    cdr_capabilities = body["capabilities"]["cdr_annotation"]
    assert cdr_capabilities["backend_available"] is True
    assert cdr_capabilities["numbering_support_available"] is True
    assert cdr_capabilities["motif_fallback_available"] is True
    assert cdr_capabilities["typed_validation_issues_available"] is True
    assert "typed validation issues" in cdr_capabilities["detail"]
    telemetry = cdr_capabilities["telemetry"]
    assert telemetry["total_antibody_summaries"] == 0
    assert telemetry["numbering_based_percent"] == 0.0
    assert telemetry["motif_fallback_percent"] == 0.0
    assert telemetry["ambiguous_or_failed_percent"] == 0.0


def test_health_endpoint_reports_cdr_telemetry_percentages() -> None:
    reset_cdr_annotation_telemetry()

    numbered_structure = _structure(
        [
            _chain(
                "H",
                [
                    _residue(31, "CYS"),
                    *[_residue(sequence_id, "ALA") for sequence_id in range(32, 36)],
                    _residue(50, "TRP"),
                    *[_residue(sequence_id, "ALA") for sequence_id in range(51, 66)],
                    *[_residue(sequence_id, "ALA") for sequence_id in range(95, 103)],
                ],
            )
        ]
    )
    summarize_structure(numbered_structure, "PDBParser", prediction_mode="antibody_antigen")

    motif_residues = [
        _residue(1, "CYS"),
        _residue(2, "ALA"),
        _residue(3, "ALA"),
        _residue(4, "ALA"),
        _residue(5, "ALA"),
        _residue(6, "TRP"),
        _residue(7, "GLY"),
        _residue(8, "ALA"),
        _residue(9, "GLY"),
    ]
    motif_structure = _structure([_chain("H", motif_residues)])
    summarize_structure(motif_structure, "PDBParser", prediction_mode="antibody_antigen")

    failed_structure = _structure([])
    summarize_structure(failed_structure, "PDBParser", prediction_mode="antibody_antigen")

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    telemetry = response.json()["capabilities"]["cdr_annotation"]["telemetry"]

    assert telemetry["total_antibody_summaries"] == 3
    assert telemetry["numbering_based_count"] == 1
    assert telemetry["motif_fallback_count"] == 1
    assert telemetry["ambiguous_or_failed_count"] == 1
    assert telemetry["numbering_based_percent"] == pytest.approx(33.33, abs=0.01)
    assert telemetry["motif_fallback_percent"] == pytest.approx(33.33, abs=0.01)
    assert telemetry["ambiguous_or_failed_percent"] == pytest.approx(33.33, abs=0.01)
