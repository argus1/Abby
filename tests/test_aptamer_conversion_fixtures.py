from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from abby_api.main import app
from abby_api.services.structure_parsing import BIOPYTHON_AVAILABLE, convert_pdb_to_mmcif

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-local-key"}
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "validation_dataset" / "aptamer"


@pytest.mark.skipif(
    not BIOPYTHON_AVAILABLE,
    reason="BioPython is required for PDB-to-mmCIF conversion",
)
def test_canonical_aptamer_pdb_conversion_preserves_chain_and_nucleotide_profile(
    tmp_path: Path,
) -> None:
    source_path = FIXTURE_ROOT / "dna_aptamer_target.pdb"
    converted_path = tmp_path / "dna_aptamer_target.converted.mmcif"

    convert_pdb_to_mmcif(source_path, converted_path)

    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                converted_path.name,
                converted_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text

    detail_response = client.get(
        f"/api/v1/structures/{upload_response.json()['structure_id']}",
        headers=HEADERS,
    )
    assert detail_response.status_code == 200, detail_response.text
    summary = detail_response.json()["summary"]
    profile = summary["metadata"]["nucleic_acid_profile"]

    assert summary["available_chains"] == ["D", "T"]
    assert summary["residue_counts"] == {"D": 3, "T": 2}
    assert profile["chain_types"] == {"D": "dna", "T": "protein"}
    assert profile["canonical_nucleotide_counts"] == {
        "D": {"DA": 1, "DC": 1, "DG": 1}
    }
    assert profile["modified_nucleotides"] == []
    assert profile["atom_naming_issues"] == []
    assert profile["residue_naming_issues"] == []
    assert profile["counterion_inventory"] == {
        "available": False,
        "total_ion_count": 0,
        "ion_counts": {},
        "nominal_charge_total": 0,
        "ions": [],
    }
    assert profile["ionization_preflight"] == {
        "status": "review_required",
        "counterions_present": False,
        "concentration_known": False,
        "neutralization_assessed": False,
        "reason_codes": [
            "ION_CONCENTRATION_UNKNOWN",
            "NEUTRALIZATION_NOT_ASSESSED",
        ],
    }
    assert summary["metadata"]["connectivity"]["connection_count"] == 0


def test_canonical_aptamer_mmcif_preserves_explicit_phosphodiester_connectivity() -> None:
    fixture_path = FIXTURE_ROOT / "dna_aptamer_target.mmcif"

    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text

    detail_response = client.get(
        f"/api/v1/structures/{upload_response.json()['structure_id']}",
        headers=HEADERS,
    )
    assert detail_response.status_code == 200, detail_response.text
    metadata = detail_response.json()["summary"]["metadata"]
    connectivity = metadata["connectivity"]

    assert metadata["nucleic_acid_profile"]["chain_types"] == {
        "D": "dna",
        "T": "protein",
    }
    assert connectivity["available"] is True
    assert connectivity["source"] == "_struct_conn"
    assert connectivity["connection_count"] == 2
    assert [record["id"] for record in connectivity["connections"]] == [
        "phosphodiester_1_2",
        "phosphodiester_2_3",
    ]
    assert connectivity["connections"][0]["partner_1"] == {
        "chain_id": "D",
        "residue_name": "DA",
        "sequence_id": "1",
        "atom_id": "O3'",
    }
    assert connectivity["connections"][0]["partner_2"] == {
        "chain_id": "D",
        "residue_name": "DC",
        "sequence_id": "2",
        "atom_id": "P",
    }


def test_canonical_aptamer_connectivity_persists_through_validation_and_prediction() -> None:
    fixture_path = FIXTURE_ROOT / "dna_aptamer_target.mmcif"
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "aptamer_target",
            "chains": {"partner_1": ["D"], "partner_2": ["T"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation = validate_response.json()
    assert validation["valid"] is True
    assert validation["inferred_roles"] == {
        "partner_1": "aptamer",
        "partner_2": "target",
    }

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "Canonical aptamer connectivity"},
    )
    assert project_response.status_code == 201, project_response.text

    prediction_response = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_response.json()["project_id"],
            "structure_id": structure_id,
            "mode": "aptamer_target",
        },
    )
    assert prediction_response.status_code == 202, prediction_response.text

    prediction_fetch = client.get(
        f"/api/v1/predictions/{prediction_response.json()['prediction_id']}",
        headers=HEADERS,
    )
    assert prediction_fetch.status_code == 200, prediction_fetch.text
    topology_handoff = prediction_fetch.json()["provenance"]["topology_handoff"]
    preserved = topology_handoff["preserved_connectivity"]
    assert preserved["source"] == "_struct_conn"
    assert preserved["connection_count"] == 2
    assert [record["id"] for record in preserved["connections"]] == [
        "phosphodiester_1_2",
        "phosphodiester_2_3",
    ]


def test_malformed_aptamer_reports_typed_atom_naming_warning() -> None:
    fixture_path = FIXTURE_ROOT / "rna_aptamer_malformed_naming.mmcif"
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "aptamer_target",
            "chains": {"partner_1": ["R"], "partner_2": ["T"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation = validate_response.json()
    assert validation["valid"] is True
    assert "APTAMER_ATOM_NAMING_INCOMPATIBLE" in validation["warnings"]
    issue = next(
        item
        for item in validation["warning_details"]
        if item["code"] == "APTAMER_ATOM_NAMING_INCOMPATIBLE"
    )
    assert issue["details"]["atom_naming_issues"] == [
        {
            "chain_id": "R",
            "residue_name": "U",
            "sequence_id": 1,
            "observed_atom_name": "O5*",
            "expected_atom_name": "O5'",
            "category": "legacy_star_prime_notation",
        }
    ]


def test_malformed_aptamer_reports_typed_residue_naming_warning() -> None:
    fixture_path = FIXTURE_ROOT / "rna_aptamer_malformed_naming.mmcif"
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "aptamer_target",
            "chains": {"partner_1": ["R"], "partner_2": ["T"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation = validate_response.json()
    assert validation["valid"] is True
    assert "APTAMER_RESIDUE_NAMING_INCOMPATIBLE" in validation["warnings"]
    assert "UNSUPPORTED_RESIDUE" not in validation["warnings"]
    issue = next(
        item
        for item in validation["warning_details"]
        if item["code"] == "APTAMER_RESIDUE_NAMING_INCOMPATIBLE"
    )
    assert issue["details"]["residue_naming_issues"] == [
        {
            "chain_id": "R",
            "observed_residue_name": "RA",
            "sequence_id": 2,
            "expected_residue_name": "A",
            "polymer_type": "rna",
            "category": "legacy_rna_prefix",
        }
    ]


def test_aptamer_validation_reports_typed_na_mg_counterion_inventory() -> None:
    fixture_path = FIXTURE_ROOT / "dna_aptamer_na_mg_counterions.mmcif"
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "aptamer_target",
            "chains": {"partner_1": ["D"], "partner_2": ["T"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation = validate_response.json()
    assert validation["valid"] is True
    assert "APTAMER_COUNTERIONS_PRESENT" in validation["warnings"]
    issue = next(
        item
        for item in validation["warning_details"]
        if item["code"] == "APTAMER_COUNTERIONS_PRESENT"
    )
    assert issue["details"]["counterion_inventory"] == {
        "available": True,
        "total_ion_count": 2,
        "ion_counts": {"MG": 1, "NA": 1},
        "nominal_charge_total": 3,
        "ions": [
            {
                "chain_id": "I",
                "residue_name": "MG",
                "sequence_id": 2,
                "nominal_charge": 2,
            },
            {
                "chain_id": "I",
                "residue_name": "NA",
                "sequence_id": 1,
                "nominal_charge": 1,
            },
        ],
    }


def test_aptamer_validation_requires_ionization_preflight_review() -> None:
    fixture_path = FIXTURE_ROOT / "dna_aptamer_na_mg_counterions.mmcif"
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "aptamer_target",
            "chains": {"partner_1": ["D"], "partner_2": ["T"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation = validate_response.json()
    assert validation["valid"] is True
    assert "APTAMER_IONIZATION_PRECHECK_REQUIRED" in validation["warnings"]
    issue = next(
        item
        for item in validation["warning_details"]
        if item["code"] == "APTAMER_IONIZATION_PRECHECK_REQUIRED"
    )
    assert issue["details"]["ionization_preflight"] == {
        "status": "review_required",
        "counterions_present": True,
        "concentration_known": False,
        "neutralization_assessed": False,
        "reason_codes": [
            "COUNTERION_ROLE_UNVERIFIED",
            "ION_CONCENTRATION_UNKNOWN",
            "NEUTRALIZATION_NOT_ASSESSED",
        ],
    }


def test_aptamer_prediction_persists_deterministic_sasa_fraction_provenance() -> None:
    fixture_path = FIXTURE_ROOT / "dna_aptamer_target.mmcif"
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "aptamer_target",
            "chains": {"partner_1": ["D"], "partner_2": ["T"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    assert validate_response.json()["valid"] is True

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "Aptamer SASA descriptor provenance"},
    )
    assert project_response.status_code == 201, project_response.text

    prediction_results = []
    for _ in range(2):
        prediction_response = client.post(
            "/api/v1/predictions",
            headers=HEADERS,
            json={
                "project_id": project_response.json()["project_id"],
                "structure_id": structure_id,
                "mode": "aptamer_target",
            },
        )
        assert prediction_response.status_code == 202, prediction_response.text
        prediction_fetch = client.get(
            f"/api/v1/predictions/{prediction_response.json()['prediction_id']}",
            headers=HEADERS,
        )
        assert prediction_fetch.status_code == 200, prediction_fetch.text
        prediction_results.append(prediction_fetch.json())

    first_summary = prediction_results[0]["feature_summary"]
    first_descriptors = first_summary["descriptors"]
    assert "aptamer_sasa_fraction" in first_descriptors
    assert first_descriptors["aptamer_sasa_fraction"] == round(
        first_descriptors["sasa_partner_1"] / first_descriptors["sasa_total"],
        4,
    )
    assert 0.0 < first_descriptors["aptamer_sasa_fraction"] <= 1.0
    assert first_summary["descriptor_version"] == "aptamer_features_v2"

    first_hash = prediction_results[0]["provenance"]["descriptor_hash"]
    second_hash = prediction_results[1]["provenance"]["descriptor_hash"]
    assert len(first_hash) == 64
    assert prediction_results[0]["feature_summary"]["descriptors"] == (
        prediction_results[1]["feature_summary"]["descriptors"]
    )
    assert first_hash == second_hash


def test_aptamer_prediction_persists_deterministic_counterion_contact_count() -> None:
    fixture_path = FIXTURE_ROOT / "dna_aptamer_na_mg_counterions.mmcif"
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                fixture_path.name,
                fixture_path.read_bytes(),
                "chemical/x-cif",
            )
        },
        data={"mode": "aptamer_target"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "aptamer_target",
            "chains": {"partner_1": ["D"], "partner_2": ["T"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    assert validate_response.json()["valid"] is True

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "Aptamer counterion contact provenance"},
    )
    assert project_response.status_code == 201, project_response.text

    prediction_results = []
    for _ in range(2):
        prediction_response = client.post(
            "/api/v1/predictions",
            headers=HEADERS,
            json={
                "project_id": project_response.json()["project_id"],
                "structure_id": structure_id,
                "mode": "aptamer_target",
            },
        )
        assert prediction_response.status_code == 202, prediction_response.text
        prediction_fetch = client.get(
            f"/api/v1/predictions/{prediction_response.json()['prediction_id']}",
            headers=HEADERS,
        )
        assert prediction_fetch.status_code == 200, prediction_fetch.text
        prediction_results.append(prediction_fetch.json())

    first_descriptors = prediction_results[0]["feature_summary"]["descriptors"]
    assert first_descriptors["aptamer_counterion_contact_count"] == 1.0
    assert prediction_results[0]["feature_summary"]["descriptor_version"] == (
        "aptamer_features_v2"
    )
    first_hash = prediction_results[0]["provenance"]["descriptor_hash"]
    second_hash = prediction_results[1]["provenance"]["descriptor_hash"]
    assert len(first_hash) == 64
    assert first_hash == second_hash
