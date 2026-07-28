#!/usr/bin/env python3
"""
Analyze ANDD validation report for systemic affinity prediction failures.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict


def analyze_report(report_path: Path) -> None:
    """Mine validation report for patterns and systemic issues."""

    with open(report_path) as f:
        report = json.load(f)

    cases = report.get("cases", [])
    metrics = report.get("metrics", {})

    print("\n" + "=" * 80)
    print("ANDD VALIDATION DATASET ANALYSIS")
    print("=" * 80)

    # Summary stats
    print(f"\nDataset Summary:")
    print(f"  Total structures: {report.get('total_structures', 0)}")
    print(f"  Converted: {report.get('converted_structures', 0)}")
    print(f"  Validated: {report.get('validated_structures', 0)}")
    print(f"  Predicted: {report.get('predicted_structures', 0)}")
    print(f"  Failed: {report.get('failed_structures', 0)}")
    print(f"  Matched (ref data available): {report.get('matched_structures', 0)}")
    
    # Affinity metrics
    print(f"\nAffinity Prediction Metrics:")
    paired = metrics.get("paired_cases", 0)
    print(f"  Paired cases (predicted vs experimental): {paired}")
    if paired > 0:
        mae_dg = metrics.get("mae_delta_g_kcal_mol")
        rmse_dg = metrics.get("rmse_delta_g_kcal_mol")
        pearson_dg = metrics.get("pearson_delta_g_kcal_mol")
        print(f"  ΔG (kcal/mol) MAE: {mae_dg:.3f}" if mae_dg is not None else "  ΔG (kcal/mol) MAE: N/A")
        print(f"  ΔG (kcal/mol) RMSE: {rmse_dg:.3f}" if rmse_dg is not None else "  ΔG (kcal/mol) RMSE: N/A")
        print(f"  ΔG (kcal/mol) Pearson: {pearson_dg:.4f}" if pearson_dg is not None else "  ΔG (kcal/mol) Pearson: N/A")
        
        mae_logk = metrics.get("mae_log_k")
        rmse_logk = metrics.get("rmse_log_k")
        pearson_logk = metrics.get("pearson_log_k")
        print(f"  log(K) MAE: {mae_logk:.3f}" if mae_logk is not None else "  log(K) MAE: N/A")
        print(f"  log(K) RMSE: {rmse_logk:.3f}" if rmse_logk is not None else "  log(K) RMSE: N/A")
        print(f"  log(K) Pearson: {pearson_logk:.4f}" if pearson_logk is not None else "  log(K) Pearson: N/A")
    
    # Validation failure analysis
    print(f"\nValidation Status Breakdown:")
    validation_status_counts = defaultdict(int)
    for case in cases:
        status = case.get("validation_status", "unknown")
        validation_status_counts[status] += 1
    
    for status, count in sorted(validation_status_counts.items()):
        print(f"  {status}: {count}")
    
    # Error pattern analysis
    print(f"\nValidation Errors (patterns):")
    error_counts = defaultdict(int)
    cases_with_errors = 0
    for case in cases:
        errors = case.get("validation_errors", [])
        if errors:
            cases_with_errors += 1
            for error in errors:
                error_counts[error] += 1
    
    if error_counts:
        print(f"  Cases with validation errors: {cases_with_errors}/{len(cases)}")
        for error, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            pct = (count / cases_with_errors * 100) if cases_with_errors else 0
            print(f"    {error}: {count} ({pct:.1f}%)")
    else:
        print(f"  No validation errors detected.")
    
    # Warnings pattern analysis
    print(f"\nValidation Warnings (patterns):")
    warning_counts = defaultdict(int)
    cases_with_warnings = 0
    for case in cases:
        warnings = case.get("validation_warnings", [])
        if warnings:
            cases_with_warnings += 1
            for warn in warnings:
                warning_counts[warn] += 1
    
    if warning_counts:
        print(f"  Cases with warnings: {cases_with_warnings}/{len(cases)}")
        for warn, count in sorted(warning_counts.items(), key=lambda x: -x[1]):
            pct = (count / len(cases) * 100)
            print(f"    {warn}: {count} ({pct:.1f}%)")
    
    # Prediction quality
    print(f"\nPrediction Status:")
    pred_status_counts = defaultdict(int)
    for case in cases:
        status = case.get("prediction_status", "unknown")
        pred_status_counts[status] += 1
    
    for status, count in sorted(pred_status_counts.items()):
        print(f"  {status}: {count}")
    
    # Reference data availability
    print(f"\nReference Data Availability:")
    has_ref = sum(1 for c in cases if c.get("experimental_kd_m") is not None or c.get("experimental_delta_g_kj_mol") is not None)
    print(f"  Cases with affinity labels: {has_ref}/{len(cases)}")
    
    # Top failing cases (if validation/prediction failed)
    print(f"\nTop Failed Cases (validation_status='failed' or prediction_status='failed'):")
    failed = [c for c in cases if c.get("validation_status") == "failed" or c.get("prediction_status") == "failed"]
    for case in failed[:10]:
        pdb_id = case.get("pdb_id", "unknown")
        val_err = case.get("validation_errors", [])
        val_err_str = ", ".join(val_err[:2]) if val_err else "none"
        pred_status = case.get("prediction_status", "unknown")
        error = case.get("error")
        print(f"  {pdb_id}: prediction={pred_status}, validation_errors=[{val_err_str}]")
        if error:
            print(f"    error: {error[:80]}")
    
    # Simulation readiness
    print(f"\nMD Simulation Readiness:")
    md_ready = sum(1 for c in cases if c.get("md_handoff_ready"))
    print(f"  MD-ready structures: {md_ready}/{len(cases)}")
    gromacs_available = sum(1 for c in cases if c.get("gromacs_cif_available"))
    print(f"  GROMACS CIF available: {gromacs_available}/{len(cases)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        report_path = Path("data/validation_runs/andd_full_20260726/reports/validation_report.json")
    else:
        report_path = Path(sys.argv[1])
    
    if not report_path.exists():
        print(f"Report not found: {report_path}")
        print("(Full ANDD run may still be in progress)")
        sys.exit(1)
    
    analyze_report(report_path)
