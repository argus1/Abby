from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from abby_api.services.cdr_quality_calibration import (
    CDRCalibrationSample,
    build_cdr_calibration_report,
)

_DEFAULT_ARTIFACT_ROOT = Path("data/validation_runs")
_DEFAULT_BINS = 10


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def _extract_sample(case: dict[str, Any]) -> CDRCalibrationSample | None:
    score_value = case.get("cdr_quality_baseline_score")
    if score_value is None:
        quality_baseline = case.get("quality_baseline")
        if isinstance(quality_baseline, dict):
            score_value = quality_baseline.get("score")

    observed_value = case.get("cdr_quality_baseline_observed_pass")
    if observed_value is None:
        observed_value = case.get("quality_baseline_observed_pass")

    parsed_observed = _parse_bool(observed_value)
    if parsed_observed is None:
        return None

    if score_value is None:
        return None

    try:
        score = float(score_value)
    except (TypeError, ValueError):
        return None

    return CDRCalibrationSample(score=score, observed_positive=parsed_observed)


def _load_validation_report(report_path: Path) -> dict[str, Any]:
    raw = report_path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Validation report at {report_path} is not a JSON object")
    return payload


def generate_cdr_calibration_artifacts(
    report_path: Path,
    *,
    n_bins: int = _DEFAULT_BINS,
    output_prefix: str = "cdr_quality_calibration",
) -> tuple[Path, Path]:
    payload = _load_validation_report(report_path)
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        cases = []

    samples = [
        sample
        for case in cases
        if isinstance(case, dict)
        for sample in [_extract_sample(case)]
        if sample is not None
    ]
    report = build_cdr_calibration_report(samples, n_bins=n_bins)

    report_dir = report_path.parent
    json_path = report_dir / f"{output_prefix}_report.json"
    csv_path = report_dir / f"{output_prefix}_bins.csv"

    report_payload = asdict(report)
    report_payload["source_validation_report"] = str(report_path)
    report_payload["extracted_sample_count"] = len(samples)
    json_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "index",
            "lower_bound",
            "upper_bound",
            "count",
            "mean_score",
            "observed_rate",
            "abs_calibration_gap",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for bucket in report.bins:
            writer.writerow(asdict(bucket))

    return json_path, csv_path


def run_for_artifact_root(
    artifact_root: Path,
    *,
    n_bins: int = _DEFAULT_BINS,
    output_prefix: str = "cdr_quality_calibration",
) -> list[tuple[Path, Path]]:
    report_paths = sorted(artifact_root.rglob("validation_report.json"))
    outputs: list[tuple[Path, Path]] = []
    for report_path in report_paths:
        outputs.append(
            generate_cdr_calibration_artifacts(
                report_path,
                n_bins=n_bins,
                output_prefix=output_prefix,
            )
        )
    return outputs


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build CDR quality calibration artifacts from validation_report.json files."
        )
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=_DEFAULT_ARTIFACT_ROOT,
        help="Root directory to search recursively for validation_report.json files.",
    )
    parser.add_argument(
        "--n-bins",
        type=int,
        default=_DEFAULT_BINS,
        help="Number of equal-width reliability bins.",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="cdr_quality_calibration",
        help="Output filename prefix used alongside each validation report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    outputs = run_for_artifact_root(
        args.artifact_root,
        n_bins=args.n_bins,
        output_prefix=args.output_prefix,
    )
    if not outputs:
        print(f"No validation_report.json files found under {args.artifact_root}")
        return 0

    for json_path, csv_path in outputs:
        print(f"Wrote calibration report: {json_path}")
        print(f"Wrote calibration bins CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
