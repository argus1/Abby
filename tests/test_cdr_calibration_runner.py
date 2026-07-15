from __future__ import annotations

import csv
import json
from pathlib import Path

from abby_api.cdr_calibration_runner import (
    generate_cdr_calibration_artifacts,
    run_for_artifact_root,
)


def _write_validation_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_generate_cdr_calibration_artifacts_from_case_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "run" / "reports" / "validation_report.json"
    _write_validation_report(
        report_path,
        {
            "cases": [
                {
                    "pdb_id": "1ABC",
                    "cdr_quality_baseline_score": 0.9,
                    "cdr_quality_baseline_observed_pass": True,
                },
                {
                    "pdb_id": "2DEF",
                    "cdr_quality_baseline_score": 0.2,
                    "cdr_quality_baseline_observed_pass": False,
                },
                {
                    "pdb_id": "3GHI",
                    "cdr_quality_baseline_score": None,
                    "cdr_quality_baseline_observed_pass": True,
                },
            ]
        },
    )

    json_path, csv_path = generate_cdr_calibration_artifacts(report_path, n_bins=5)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["n_samples"] == 2
    assert payload["ready"] is True
    assert payload["source_validation_report"] == str(report_path)

    with csv_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 5


def test_generate_cdr_calibration_artifacts_falls_back_to_quality_baseline_dict(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "run" / "reports" / "validation_report.json"
    _write_validation_report(
        report_path,
        {
            "cases": [
                {
                    "pdb_id": "4JKL",
                    "quality_baseline": {"score": 0.75},
                    "quality_baseline_observed_pass": "true",
                },
                {
                    "pdb_id": "5MNO",
                    "quality_baseline": {"score": 0.15},
                    "quality_baseline_observed_pass": "false",
                },
            ]
        },
    )

    json_path, _ = generate_cdr_calibration_artifacts(report_path, n_bins=4)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["n_samples"] == 2
    assert payload["ready"] is True


def test_run_for_artifact_root_processes_multiple_reports(tmp_path: Path) -> None:
    report_path_a = tmp_path / "run_a" / "reports" / "validation_report.json"
    report_path_b = tmp_path / "run_b" / "reports" / "validation_report.json"

    _write_validation_report(
        report_path_a,
        {
            "cases": [
                {
                    "cdr_quality_baseline_score": 0.8,
                    "cdr_quality_baseline_observed_pass": True,
                }
            ]
        },
    )
    _write_validation_report(
        report_path_b,
        {
            "cases": [
                {
                    "cdr_quality_baseline_score": 0.4,
                    "cdr_quality_baseline_observed_pass": False,
                }
            ]
        },
    )

    outputs = run_for_artifact_root(tmp_path, n_bins=3)

    assert len(outputs) == 2
    for json_path, csv_path in outputs:
        assert json_path.exists()
        assert csv_path.exists()
