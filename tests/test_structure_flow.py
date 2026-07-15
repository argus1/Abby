from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from abby_api.main import app
from abby_api.repositories.memory import get_feature_summary_artifact
from abby_api.services.structure_parsing import BIOPYTHON_AVAILABLE, convert_pdb_to_mmcif
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

PDB_GAP_FIXTURE = """\
ATOM      1  N   GLY A   1      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  CA  GLY A   1      12.560  13.102   9.262  1.00 20.00           C
ATOM      3  C   GLY A   1      13.030  11.670   9.634  1.00 20.00           C
ATOM      4  O   GLY A   1      12.284  10.719   9.434  1.00 20.00           O
ATOM      5  N   ALA A   3      14.300  11.500  10.100  1.00 20.00           N
ATOM      6  CA  ALA A   3      14.900  10.170  10.420  1.00 20.00           C
ATOM      7  C   ALA A   3      16.350  10.200  10.900  1.00 20.00           C
ATOM      8  O   ALA A   3      17.020   9.180  10.810  1.00 20.00           O
ATOM      9  N   SER B   1      18.200  10.700  11.400  1.00 20.00           N
ATOM     10  CA  SER B   1      19.100  10.900  12.500  1.00 20.00           C
TER
END
"""

MMCIF_CONNECTIVITY_FIXTURE = """\
data_connectivity
#
loop_
_struct_conn.id
_struct_conn.conn_type_id
_struct_conn.ptnr1_label_asym_id
_struct_conn.ptnr1_label_comp_id
_struct_conn.ptnr1_label_seq_id
_struct_conn.ptnr1_label_atom_id
_struct_conn.ptnr2_label_asym_id
_struct_conn.ptnr2_label_comp_id
_struct_conn.ptnr2_label_seq_id
_struct_conn.ptnr2_label_atom_id
disulf1 disulf A CYS 6 SG A CYS 127 SG
glyco1 covale A ASN 10 ND2 C NAG 301 C1
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.pdbx_formal_charge
_atom_site.auth_seq_id
_atom_site.auth_comp_id
_atom_site.auth_asym_id
_atom_site.auth_atom_id
_atom_site.pdbx_PDB_model_num
ATOM 1 S SG . CYS A 1 6 ? 11.104 13.207 9.111 1.00 20.00 ? 6 CYS A SG 1
ATOM 2 S SG . CYS A 1 127 ? 14.300 11.500 10.100 1.00 20.00 ? 127 CYS A SG 1
ATOM 3 N ND2 . ASN A 1 10 ? 15.100 10.170 10.420 1.00 20.00 ? 10 ASN A ND2 1
HETATM 4 C C1 . NAG C 2 301 ? 16.350 10.200 10.900 1.00 20.00 ? 301 NAG C C1 1
ATOM 5 N N . ALA B 3 1 ? 12.560 13.102 9.262 1.00 20.00 ? 1 ALA B N 1
#
"""

PDB_ANTIBODY_CHAIN_REMAP_FIXTURE = """\
ATOM      1  N   CYS B  95      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  CA  CYS B  95      12.560  13.102   9.262  1.00 20.00           C
ATOM      3  C   CYS B  95      13.030  11.670   9.634  1.00 20.00           C
ATOM      4  O   CYS B  95      12.284  10.719   9.434  1.00 20.00           O
ATOM      5  N   TRP B 102      14.300  11.500  10.100  1.00 20.00           N
ATOM      6  CA  TRP B 102      14.900  10.170  10.420  1.00 20.00           C
ATOM      7  C   TRP B 102      16.350  10.200  10.900  1.00 20.00           C
ATOM      8  O   TRP B 102      17.020   9.180  10.810  1.00 20.00           O
ATOM      9  N   CYS A  24      18.200  10.700  11.400  1.00 20.00           N
ATOM     10  CA  CYS A  24      19.100  10.900  12.500  1.00 20.00           C
ATOM     11  C   CYS A  24      19.900  12.100  12.900  1.00 20.00           C
ATOM     12  O   CYS A  24      20.800  12.200  13.700  1.00 20.00           O
ATOM     13  N   PHE A  89      21.100  13.100  13.500  1.00 20.00           N
ATOM     14  CA  PHE A  89      22.200  13.300  14.300  1.00 20.00           C
ATOM     15  C   PHE A  89      23.100  14.400  13.700  1.00 20.00           C
ATOM     16  O   PHE A  89      24.200  14.200  13.200  1.00 20.00           O
TER
END
"""

PDB_ANTIBODY_MULTI_MODEL_REMAP_GAP_FIXTURE = """\
MODEL        1
ATOM      1  N   CYS B  95      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  CA  CYS B  95      12.560  13.102   9.262  1.00 20.00           C
ATOM      3  N   TRP B 102      14.300  11.500  10.100  1.00 20.00           N
ATOM      4  CA  TRP B 102      14.900  10.170  10.420  1.00 20.00           C
ATOM      5  N   CYS A  24      18.200  10.700  11.400  1.00 20.00           N
ATOM      6  CA  CYS A  24      19.100  10.900  12.500  1.00 20.00           C
ATOM      7  N   PHE A  89      21.100  13.100  13.500  1.00 20.00           N
ATOM      8  CA  PHE A  89      22.200  13.300  14.300  1.00 20.00           C
TER
ENDMDL
MODEL        2
ATOM      9  N   ALA B  10      31.104  23.207  19.111  1.00 20.00           N
ATOM     10  CA  ALA B  10      32.560  23.102  19.262  1.00 20.00           C
ATOM     11  N   ALA A  11      33.300  21.500  20.100  1.00 20.00           N
ATOM     12  CA  ALA A  11      33.900  20.170  20.420  1.00 20.00           C
TER
ENDMDL
END
"""

PDB_ANTIBODY_MOTIF_FALLBACK_FIXTURE = """\
ATOM      1  N   CYS H   1      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  CA  CYS H   1      12.560  13.102   9.262  1.00 20.00           C
ATOM      3  N   ALA H   2      13.030  11.670   9.634  1.00 20.00           N
ATOM      4  CA  ALA H   2      12.284  10.719   9.434  1.00 20.00           C
ATOM      5  N   ALA H   3      14.300  11.500  10.100  1.00 20.00           N
ATOM      6  CA  ALA H   3      14.900  10.170  10.420  1.00 20.00           C
ATOM      7  N   ALA H   4      16.350  10.200  10.900  1.00 20.00           N
ATOM      8  CA  ALA H   4      17.020   9.180  10.810  1.00 20.00           C
ATOM      9  N   ALA H   5      18.200  10.700  11.400  1.00 20.00           N
ATOM     10  CA  ALA H   5      19.100  10.900  12.500  1.00 20.00           C
ATOM     11  N   ALA H   6      19.900  12.100  12.900  1.00 20.00           N
ATOM     12  CA  ALA H   6      20.800  12.200  13.700  1.00 20.00           C
ATOM     13  N   TRP H   7      21.100  13.100  13.500  1.00 20.00           N
ATOM     14  CA  TRP H   7      22.200  13.300  14.300  1.00 20.00           C
ATOM     15  N   GLY H   8      23.100  14.400  13.700  1.00 20.00           N
ATOM     16  CA  GLY H   8      24.200  14.200  13.200  1.00 20.00           C
ATOM     17  N   ALA H   9      25.100  15.100  12.900  1.00 20.00           N
ATOM     18  CA  ALA H   9      26.200  15.300  12.100  1.00 20.00           C
ATOM     19  N   GLY H  10      27.100  16.400  11.700  1.00 20.00           N
ATOM     20  CA  GLY H  10      28.200  16.200  11.200  1.00 20.00           C
ATOM     21  N   ALA A   1      29.100  17.100  10.900  1.00 20.00           N
ATOM     22  CA  ALA A   1      30.200  17.300  10.100  1.00 20.00           C
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
    assert sorted(
        error_details_by_code["UNKNOWN_CHAIN_SELECTION"]["details"]["missing_chains"]
    ) == ["Z"]


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
    assert (
        warning_details_by_code["UNSUPPORTED_RESIDUE"]["details"]["unsupported_residue_counts"][
            "A"
        ]["MSE"]
        == 1
    )


@pytest.mark.skipif(not BIOPYTHON_AVAILABLE, reason="BioPython is required for mmCIF parsing")
def test_mmcif_upload_preserves_struct_conn_connectivity_metadata() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_connectivity.mmcif", MMCIF_CONNECTIVITY_FIXTURE, "chemical/x-cif")},
        data={"mode": "ppi_general"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    detail_response = client.get(f"/api/v1/structures/{structure_id}", headers=HEADERS)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()

    connectivity = detail["summary"]["metadata"]["connectivity"]
    assert connectivity["available"] is True
    assert connectivity["source"] == "_struct_conn"
    assert connectivity["connection_count"] == 2
    assert connectivity["disulfide_count"] == 1
    assert connectivity["glycan_link_count"] == 1

    connection_by_id = {entry["id"]: entry for entry in connectivity["connections"]}
    assert connection_by_id["disulf1"]["is_disulfide"] is True
    assert connection_by_id["disulf1"]["partner_1"]["residue_name"] == "CYS"
    assert connection_by_id["glyco1"]["is_glycan_link"] is True
    assert connection_by_id["glyco1"]["partner_2"]["residue_name"] == "NAG"


@pytest.mark.skipif(not BIOPYTHON_AVAILABLE, reason="BioPython is required for mmCIF parsing")
def test_mmcif_connectivity_metadata_persists_through_validation_flow() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "test_connectivity_validation.mmcif",
                MMCIF_CONNECTIVITY_FIXTURE,
                "chemical/x-cif",
            )
        },
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
            "chains": {"partner_1": ["A"], "partner_2": ["B", "C"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    assert validate_response.json()["valid"] is True

    detail_response = client.get(f"/api/v1/structures/{structure_id}", headers=HEADERS)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()

    connectivity = detail["summary"]["metadata"]["connectivity"]
    assert connectivity["available"] is True
    assert connectivity["connection_count"] == 2
    assert len(connectivity["disulfide_connections"]) == connectivity["disulfide_count"] == 1
    assert len(connectivity["glycan_connections"]) == connectivity["glycan_link_count"] == 1

    glycan_connection = connectivity["glycan_connections"][0]
    assert glycan_connection["partner_1"]["residue_name"] == "ASN"
    assert glycan_connection["partner_2"]["residue_name"] == "NAG"


def test_structure_summary_reports_chain_sequence_gaps_and_md_preflight_issues() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex_gap.pdb", PDB_GAP_FIXTURE, "chemical/x-pdb")},
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
    validation = validate_response.json()
    assert validation["valid"] is True
    assert "CHAIN_SEQUENCE_GAPS" in validation["warnings"]
    assert "PDB2GMX_PRECHECK_ISSUES" in validation["warnings"]

    warning_by_code = {item["code"]: item for item in validation["warning_details"]}
    chain_gap_details = warning_by_code["CHAIN_SEQUENCE_GAPS"]["details"]["chain_gap_details"]
    assert chain_gap_details["A"][0]["from_residue"] == 1
    assert chain_gap_details["A"][0]["to_residue"] == 3
    assert chain_gap_details["A"][0]["missing_residue_count"] == 1

    precheck_issues = warning_by_code["PDB2GMX_PRECHECK_ISSUES"]["details"]["issues"]
    assert any(issue["code"] == "CHAIN_SEQUENCE_GAPS" for issue in precheck_issues)

    detail_response = client.get(f"/api/v1/structures/{structure_id}", headers=HEADERS)
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()

    md_preflight = detail_payload["summary"]["metadata"]["md_preflight"]
    assert md_preflight["ready_for_pdb2gmx"] is False
    assert any(issue["code"] == "CHAIN_SEQUENCE_GAPS" for issue in md_preflight["issues"])


def test_validation_returns_md_handoff_chain_canonicalization_plan() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex_md_handoff.pdb", PDB_FIXTURE, "chemical/x-pdb")},
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
            "chains": {"partner_1": ["B"], "partner_2": ["A"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    payload = validate_response.json()

    assert payload["valid"] is True
    assert "MD_CHAIN_CANONICALIZATION_SUGGESTED" in payload["warnings"]
    assert payload["md_handoff"]["renaming_required"] is True
    assert payload["md_handoff"]["ready_for_md_handoff"] is True
    assert payload["md_handoff"]["canonical_chain_map"]["B"] == "A"
    assert payload["md_handoff"]["canonical_chain_map"]["A"] == "B"
    assert payload["md_handoff"]["canonical_partner_1"] == ["A"]
    assert payload["md_handoff"]["canonical_partner_2"] == ["B"]

    warning_by_code = {item["code"]: item for item in payload["warning_details"]}
    handoff_details = warning_by_code["MD_CHAIN_CANONICALIZATION_SUGGESTED"]["details"][
        "md_handoff"
    ]
    assert handoff_details["renaming_required"] is True
    assert any(
        issue["code"] == "CHAIN_CANONICALIZATION_REQUIRED" for issue in handoff_details["issues"]
    )


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
    assert prediction["feature_summary"]["descriptors"]["residue_depth_partner_1_mean"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["residue_depth_partner_2_mean"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["residue_depth_interface_mean"] >= 0.0
    assert prediction["feature_summary"]["descriptors"]["radius_of_gyration_angstrom"] > 0.0
    assert prediction["feature_summary"]["descriptors"]["radius_of_gyration_atom_count"] > 0.0
    assert prediction["feature_summary"]["descriptors"]["electrostatics_hook_ready_flag"] > 0.0
    assert prediction["feature_summary"]["descriptors"]["surface_pka_hook_ready_flag"] > 0.0
    assert prediction["feature_summary"]["partner_residues"]["partner_1"] == 1
    assert prediction["provenance"]["descriptor_hash"]
    assert prediction["provenance"]["contact_distance_cutoff_angstrom"] == 5.5
    assert prediction["provenance"]["topology_handoff"]["normalized_chain_map"]
    assert prediction["provenance"]["simulation"]["imported"] is False
    assert prediction["provenance"]["artifacts"]["feature_summary"]["artifact_key"]
    assert prediction["provenance"]["artifacts"]["normalized_structure"]["artifact_key"]

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
    assert (
        low_payload["provenance"]["descriptor_hash"]
        != high_payload["provenance"]["descriptor_hash"]
    )
    assert low_payload["provenance"]["contact_distance_cutoff_angstrom"] == 0.5
    assert high_payload["provenance"]["contact_distance_cutoff_angstrom"] == 8.0


@pytest.mark.skipif(
    not BIOPYTHON_AVAILABLE, reason="BioPython is required for PDB->mmCIF conversion"
)
def test_pdb_to_mmcif_conversion_regression_preserves_chain_and_residue_counts(tmp_path) -> None:
    source_path = tmp_path / "source.pdb"
    converted_path = tmp_path / "converted.mmcif"
    source_path.write_text(PDB_FIXTURE)

    converted = convert_pdb_to_mmcif(source_path, converted_path)
    assert converted.exists()

    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "converted_regression.mmcif",
                converted.read_text(),
                "chemical/x-cif",
            )
        },
        data={"mode": "ppi_general"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    detail_response = client.get(f"/api/v1/structures/{structure_id}", headers=HEADERS)
    assert detail_response.status_code == 200, detail_response.text
    summary = detail_response.json()["summary"]
    assert summary["available_chains"] == ["A", "B"]
    assert summary["residue_counts"]["A"] == 1
    assert summary["residue_counts"]["B"] == 1
    assert summary["metadata"]["total_residues"] == 2


def test_prediction_supports_external_simulation_summary_import() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test_complex_import_sim.pdb", PDB_FIXTURE, "chemical/x-pdb")},
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
        "/api/v1/projects", headers=HEADERS, json={"name": "Simulation import"}
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    prediction_response = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "ppi_general",
        },
    )
    assert prediction_response.status_code == 202, prediction_response.text
    prediction_id = prediction_response.json()["prediction_id"]

    import_response = client.post(
        f"/api/v1/predictions/{prediction_id}/simulation-summary:import",
        headers=HEADERS,
        json={
            "force_field": "amber99sb-ildn",
            "water_model": "tip3p",
            "ionization": "0.15M NaCl",
            "minimization_protocol": "steepest-descent-5000",
            "seed": 42,
            "engine": "gromacs_external",
            "engine_version": "2026.1-cif",
            "topology_reference_url": "s3://external-bucket/topol.tpr",
            "topology_reference_format": "tpr",
            "trajectory_summary": {"frame_count": 5000, "radius_gyration_mean": 17.8},
            "notes": ["imported from external gromacs-cif run"],
        },
    )
    assert import_response.status_code == 200, import_response.text
    import_payload = import_response.json()
    assert import_payload["status"] == "imported"
    assert import_payload["simulation"]["imported"] is True
    assert import_payload["simulation"]["force_field"] == "amber99sb-ildn"
    assert import_payload["provenance"]["artifacts"]["trajectory_summary"]["artifact_key"]
    assert (
        import_payload["provenance"]["artifacts"]["topology_reference"]["external_url"]
        == "s3://external-bucket/topol.tpr"
    )

    prediction_fetch = client.get(f"/api/v1/predictions/{prediction_id}", headers=HEADERS)
    assert prediction_fetch.status_code == 200, prediction_fetch.text
    prediction_payload = prediction_fetch.json()
    assert prediction_payload["provenance"]["simulation"]["imported"] is True
    trajectory_key = prediction_payload["provenance"]["artifacts"]["trajectory_summary"][
        "artifact_key"
    ]
    assert trajectory_key
    assert ObjectStore().exists(trajectory_key)


def test_prediction_cdr_annotation_stays_on_source_chain_ids_after_md_remap() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "test_antibody_chain_remap.pdb",
                PDB_ANTIBODY_CHAIN_REMAP_FIXTURE,
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
            "chains": {"partner_1": ["B"], "partner_2": ["A"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation_payload = validate_response.json()
    assert validation_payload["md_handoff"]["canonical_chain_map"]["B"] == "A"
    assert validation_payload["md_handoff"]["canonical_chain_map"]["A"] == "B"

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "CDR remap interaction"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    prediction_response = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "antibody_antigen",
        },
    )
    assert prediction_response.status_code == 202, prediction_response.text
    prediction_id = prediction_response.json()["prediction_id"]

    prediction_fetch = client.get(f"/api/v1/predictions/{prediction_id}", headers=HEADERS)
    assert prediction_fetch.status_code == 200, prediction_fetch.text
    prediction_payload = prediction_fetch.json()
    cdr_provenance = prediction_payload["provenance"]["cdr_annotation"]

    assert cdr_provenance["selected_heavy_chain"] == "B"
    assert "B" in cdr_provenance["chains"]
    assert cdr_provenance["chains"]["B"]["role"] == "heavy"
    assert "CDR-H3" in cdr_provenance["chains"]["B"]["regions"]
    assert cdr_provenance["quality_baseline"]["available"] is True
    assert cdr_provenance["quality_baseline"]["predicted_confidence_class"] in {
        "medium",
        "high",
    }


def test_antibody_prediction_response_exposes_cdr_descriptor_fields() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "test_antibody_cdr_descriptors.pdb",
                PDB_ANTIBODY_CHAIN_REMAP_FIXTURE,
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
            "chains": {"partner_1": ["B"], "partner_2": ["A"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "CDR descriptor visibility"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    prediction_response = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "antibody_antigen",
            "options": {"include_explainability": True, "return_all_models": False},
        },
    )
    assert prediction_response.status_code == 202, prediction_response.text
    prediction_id = prediction_response.json()["prediction_id"]

    prediction_fetch = client.get(f"/api/v1/predictions/{prediction_id}", headers=HEADERS)
    assert prediction_fetch.status_code == 200, prediction_fetch.text
    prediction_payload = prediction_fetch.json()
    descriptors = prediction_payload["feature_summary"]["descriptors"]
    explainability_names = [
        item["name"] for item in prediction_payload["explainability"]["top_descriptors"]
    ]

    assert prediction_payload["feature_summary"]["descriptor_version"] == "summary_features_v3"
    assert "cdr_h3_length" in descriptors
    assert "cdr_region_count_total" in descriptors
    assert "cdr_heavy_completeness_mean" in descriptors
    assert any(name.startswith("cdr_") for name in explainability_names)


def test_antibody_multi_model_chain_remap_and_gap_combined_stress_case() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "test_antibody_multi_model_remap_gap.pdb",
                PDB_ANTIBODY_MULTI_MODEL_REMAP_GAP_FIXTURE,
                "chemical/x-pdb",
            )
        },
        data={"mode": "antibody_antigen"},
    )
    assert upload_response.status_code == 201, upload_response.text
    structure_id = upload_response.json()["structure_id"]

    detail_response = client.get(f"/api/v1/structures/{structure_id}", headers=HEADERS)
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()

    assert "MULTI_MODEL_INPUT" in detail_payload["summary"]["warnings"]
    assert "CHAIN_SEQUENCE_GAPS" in detail_payload["summary"]["warnings"]
    assert "PDB2GMX_PRECHECK_ISSUES" in detail_payload["summary"]["warnings"]

    validate_response = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "antibody_antigen",
            "chains": {"partner_1": ["B"], "partner_2": ["A"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    validation_payload = validate_response.json()

    assert validation_payload["valid"] is True
    assert validation_payload["md_handoff"]["canonical_chain_map"]["B"] == "A"
    assert validation_payload["md_handoff"]["canonical_chain_map"]["A"] == "B"
    assert "MD_CHAIN_CANONICALIZATION_SUGGESTED" in validation_payload["warnings"]
    assert "CHAIN_SEQUENCE_GAPS" in validation_payload["warnings"]
    assert "MULTI_MODEL_INPUT" in validation_payload["warnings"]

    project_response = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "CDR combined interaction stress"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["project_id"]

    prediction_response = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "antibody_antigen",
        },
    )
    assert prediction_response.status_code == 202, prediction_response.text
    prediction_id = prediction_response.json()["prediction_id"]

    prediction_fetch = client.get(f"/api/v1/predictions/{prediction_id}", headers=HEADERS)
    assert prediction_fetch.status_code == 200, prediction_fetch.text
    prediction_payload = prediction_fetch.json()

    cdr_provenance = prediction_payload["provenance"]["cdr_annotation"]
    assert cdr_provenance["available"] is True
    assert cdr_provenance["selected_heavy_chain"] == "B"
    assert cdr_provenance["boundary_source"] == "numbered"
    assert "B" in cdr_provenance["chains"]
    assert cdr_provenance["chains"]["B"]["role"] == "heavy"
    assert "CDR-H3" in cdr_provenance["chains"]["B"]["regions"]
    assert cdr_provenance["quality_baseline"]["predicted_confidence_class"] in {
        "medium",
        "high",
    }


def test_validation_surfaces_dedicated_cdr_motif_fallback_issue() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "test_antibody_motif_fallback.pdb",
                PDB_ANTIBODY_MOTIF_FALLBACK_FIXTURE,
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
            "chains": {"partner_1": ["H"], "partner_2": ["A"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    payload = validate_response.json()

    warning_details_by_code = {item["code"]: item for item in payload["warning_details"]}
    assert "CDR_MOTIF_FALLBACK_USED" in warning_details_by_code
    assert "CDR_NUMBERING_MISSING" in warning_details_by_code
    assert "CDR_BASELINE_DRIFT_FLAGGED" in warning_details_by_code
    fallback_issue = warning_details_by_code["CDR_MOTIF_FALLBACK_USED"]
    assert fallback_issue["details"]["cdr_annotation_available"] is True
    assert fallback_issue["details"]["selected_heavy_chain"] == "H"
    assert fallback_issue["details"]["boundary_source"] == "motif_fallback"

    drift_issue = warning_details_by_code["CDR_BASELINE_DRIFT_FLAGGED"]
    assert drift_issue["details"]["quality_baseline"]["drift_flag"] is True
    assert "FALLBACK_BOUNDARY_SOURCE" in drift_issue["details"]["drift_reason_codes"]
    assert "CDR_BASELINE_DRIFT_FLAGGED" in payload["warnings"]


def test_validation_surfaces_dedicated_cdr_boundary_ambiguity_issue() -> None:
    upload_response = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={
            "file": (
                "test_antibody_multi_model_remap_gap_validation.pdb",
                PDB_ANTIBODY_MULTI_MODEL_REMAP_GAP_FIXTURE,
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
            "chains": {"partner_1": ["B"], "partner_2": ["A"]},
        },
    )
    assert validate_response.status_code == 200, validate_response.text
    payload = validate_response.json()

    warning_details_by_code = {item["code"]: item for item in payload["warning_details"]}
    assert "CDR_BOUNDARY_AMBIGUOUS" in warning_details_by_code
    boundary_issue = warning_details_by_code["CDR_BOUNDARY_AMBIGUOUS"]
    assert boundary_issue["details"]["cdr_annotation_available"] is True
    assert boundary_issue["details"]["selected_heavy_chain"] == "B"
    assert boundary_issue["details"]["chains"]["A"]["completeness_score"] < 1.0
