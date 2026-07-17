from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from abby_api.validation_harness import run_andd_validation_harness

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


def _build_test_workbook(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet3"
    headers = [
        "Source",
        "Update_Date",
        "PDB_ID",
        "PDB_ID_Changed",
        "Experimental_Method",
        "Structure_Title",
        "Complex_Structure",
        "Ab_or_Nano",
        "Source_Organism",
        "H_Chain Entity ID",
        "H_Chain Asym ID",
        "H_Chain Auth Asym ID",
        "H_Chain Database Name",
        "H_Chain Accession Code(s)",
        "H_Chain Sequence Cluster ID",
        "H_Chain Sequence Cluster Identity Threshold",
        "H_Chain Macromolecule Name",
        "L_Chain Entity ID",
        "L_Chain Asym ID",
        "L_Chain Auth Asym ID",
        "L_Chain Database Name",
        "L_Chain Accession Code(s)",
        "L_Chain Sequence Cluster ID",
        "L_Chain Sequence Cluster Identity Threshold",
        "L_Chain Macromolecule Name",
        "Ag_Entity ID",
        "Ag_Asym ID",
        "Ag_Auth Asym ID",
        "Ag_Database Name",
        "Ag_Accession Code(s)",
        "Ag_Name",
        "Ag_Seq",
        "Ag_Source Organism",
        "Ab/Nano_Mutation",
        "Ab/Nano H_Chain AA",
        "Ab/Nano L_Chain AA",
        "Ab/Nano_CDR H1",
        "Ab/Nano_CDR H2",
        "Ab/Nano_CDR H3",
        "Ab/Nano_CDR L1",
        "Ab/Nano_CDR L2",
        "Ab/Nano_CDR L3",
        "CDR Nomenclature",
        (
            "Affinity_Kd(M), (the near-physiological conditions, with controlled temperatures "
            "(20-25 °C or 37 °C) and buffered aqueous systems)"
        ),
        (
            "∆Gbinding(kJ/mol),(the near-equilibrium conditions at constant temperatures "
            "(20-25 °C) )"
        ),
        "Affinity_Method",
        "Reason_Code",
        "Predicted_or_Not",
        "Provenance",
    ]
    worksheet.append(headers)
    worksheet.append(
        [
            "ANDD",
            "2024-09-16",
            "TEST",
            "No",
            "SPR",
            "Test structure",
            True,
            "Antibody",
            "Mus musculus",
            1,
            "A",
            "A",
            "PIR",
            "TESTA",
            1,
            100,
            "HEAVY",
            2,
            "N/A",
            "N/A",
            "PIR",
            "TESTB",
            2,
            100,
            "N/A",
            3,
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "\\",
            "EVQL",
            "DVMT",
            "CDRH1",
            "CDRH2",
            "CDRH3",
            "CDRL1",
            "CDRL2",
            "CDRL3",
            "Chothia",
            1.0e-9,
            None,
            "SPR",
            "not_reported",
            "real",
            "validation|unit-test",
        ]
    )
    workbook.save(path)


def test_andd_validation_harness_runs_end_to_end_on_small_fixture(tmp_path) -> None:
    dataset_root = tmp_path / "ANDD_pdb"
    structures_dir = dataset_root / "All_structures"
    structures_dir.mkdir(parents=True)
    pdb_path = structures_dir / "TEST.pdb"
    pdb_path.write_text(PDB_FIXTURE)

    workbook_path = dataset_root / "Antibody and Nanobody Design Dataset (ANDD)_v2.xlsx"
    _build_test_workbook(workbook_path)

    output_dir = tmp_path / "validation_output"
    report = run_andd_validation_harness(
        dataset_root=dataset_root,
        workbook_path=workbook_path,
        output_dir=output_dir,
        pdb_ids=["TEST"],
        simulation_policy="skip",
    )

    assert report.total_structures == 1
    assert report.converted_structures == 1
    assert report.validated_structures == 1
    assert report.predicted_structures == 1
    assert report.matched_structures == 1
    assert report.failed_structures == 0
    assert len(report.cases) == 1

    case = report.cases[0]
    assert case.pdb_id == "TEST"
    assert case.reference_row_index == 2
    assert case.reference_source == "ANDD"
    assert case.predicted_log_k is not None
    assert case.experimental_log_k is not None
    assert case.prediction_status == "completed"
    assert case.simulation_status == "skipped"

    report_path = output_dir / "reports" / "validation_report.json"
    manifest_path = output_dir / "reports" / "validation_manifest.csv"
    cases_path = output_dir / "reports" / "validation_cases.csv"
    converted_path = output_dir / "converted_mmcif" / "TEST.mmcif"

    assert report_path.exists()
    assert manifest_path.exists()
    assert cases_path.exists()
    assert converted_path.exists()


def test_andd_validation_harness_optionally_writes_cdr_stress_report(tmp_path) -> None:
    dataset_root = tmp_path / "ANDD_pdb"
    structures_dir = dataset_root / "All_structures"
    structures_dir.mkdir(parents=True)
    pdb_path = structures_dir / "TEST.pdb"
    pdb_path.write_text(PDB_FIXTURE)

    workbook_path = dataset_root / "Antibody and Nanobody Design Dataset (ANDD)_v2.xlsx"
    _build_test_workbook(workbook_path)

    output_dir = tmp_path / "validation_output"
    run_andd_validation_harness(
        dataset_root=dataset_root,
        workbook_path=workbook_path,
        output_dir=output_dir,
        pdb_ids=["TEST"],
        simulation_policy="skip",
        cdr_stress_specs=["H:95A:C>W", "H:102-95:W"],
    )

    stress_report_path = output_dir / "reports" / "cdr_mutation_stress_report.json"
    assert stress_report_path.exists()

    payload = json.loads(stress_report_path.read_text(encoding="utf-8"))
    assert payload["total_specs"] == 2
    assert payload["parsed_specs"] == 1
    assert payload["failed_specs"] == 1
    assert payload["results"][0]["status"] == "parsed"
    assert payload["results"][1]["status"] == "failed"


def test_cdr_stress_report_includes_resilience_assertions(tmp_path) -> None:
    dataset_root = tmp_path / "ANDD_pdb"
    structures_dir = dataset_root / "All_structures"
    structures_dir.mkdir(parents=True)
    pdb_path = structures_dir / "TEST.pdb"
    pdb_path.write_text(PDB_FIXTURE)

    workbook_path = dataset_root / "Antibody and Nanobody Design Dataset (ANDD)_v2.xlsx"
    _build_test_workbook(workbook_path)

    output_dir = tmp_path / "validation_output"
    run_andd_validation_harness(
        dataset_root=dataset_root,
        workbook_path=workbook_path,
        output_dir=output_dir,
        pdb_ids=["TEST"],
        simulation_policy="skip",
        cdr_stress_specs=["H:95A:C>W", "H:95-97:W", "H:102-95:W"],
    )

    stress_report_path = output_dir / "reports" / "cdr_mutation_stress_report.json"
    payload = json.loads(stress_report_path.read_text(encoding="utf-8"))
    assertions = payload["resilience_assertions"]

    assert assertions["nonzero_parse_success"]["passed"] is True
    assert assertions["failure_rate_within_limit"]["passed"] is True
    assert assertions["failure_rate_within_limit"]["observed"] == 1 / 3


def test_cdr_stress_report_includes_structure_chain_coverage_assertion(tmp_path) -> None:
    dataset_root = tmp_path / "ANDD_pdb"
    structures_dir = dataset_root / "All_structures"
    structures_dir.mkdir(parents=True)
    pdb_path = structures_dir / "TEST.pdb"
    pdb_path.write_text(PDB_FIXTURE)

    workbook_path = dataset_root / "Antibody and Nanobody Design Dataset (ANDD)_v2.xlsx"
    _build_test_workbook(workbook_path)

    output_dir = tmp_path / "validation_output"
    run_andd_validation_harness(
        dataset_root=dataset_root,
        workbook_path=workbook_path,
        output_dir=output_dir,
        pdb_ids=["TEST"],
        simulation_policy="skip",
        cdr_stress_specs=["A:1:G>W", "B:1:A>Y"],
    )

    stress_report_path = output_dir / "reports" / "cdr_mutation_stress_report.json"
    payload = json.loads(stress_report_path.read_text(encoding="utf-8"))
    assertions = payload["resilience_assertions"]

    assert assertions["spec_chains_present_in_structures"]["passed"] is True
    assert assertions["spec_chains_present_in_structures"]["observed_missing_chains"] == []