from __future__ import annotations

import pytest

from abby_api.services.cdr_quality_calibration import (
    CDRCalibrationSample,
    build_cdr_calibration_report,
)


def test_calibration_report_empty_samples() -> None:
    report = build_cdr_calibration_report([])

    assert report.ready is False
    assert report.n_samples == 0
    assert report.auc_roc is None
    assert "CALIBRATION_NO_SAMPLES" in report.notes


def test_calibration_report_basic_metrics() -> None:
    samples = [
        CDRCalibrationSample(score=0.95, observed_positive=True),
        CDRCalibrationSample(score=0.85, observed_positive=True),
        CDRCalibrationSample(score=0.20, observed_positive=False),
        CDRCalibrationSample(score=0.10, observed_positive=False),
    ]
    report = build_cdr_calibration_report(samples, n_bins=5)

    assert report.ready is True
    assert report.n_samples == 4
    assert report.n_bins == 5
    assert 0.0 <= report.ece <= 1.0
    assert 0.0 <= report.mce <= 1.0
    assert 0.0 <= report.brier_score <= 1.0
    assert report.auc_roc is not None
    assert 0.0 <= float(report.auc_roc) <= 1.0
    assert sum(bucket.count for bucket in report.bins) == report.n_samples


def test_calibration_report_auc_single_class_is_undefined() -> None:
    samples = [
        CDRCalibrationSample(score=0.9, observed_positive=True),
        CDRCalibrationSample(score=0.6, observed_positive=True),
    ]
    report = build_cdr_calibration_report(samples)

    assert report.auc_roc is None
    assert "CALIBRATION_AUC_UNDEFINED_SINGLE_CLASS" in report.notes


def test_calibration_report_score_clamping_note() -> None:
    samples = [
        CDRCalibrationSample(score=-0.2, observed_positive=False),
        CDRCalibrationSample(score=1.4, observed_positive=True),
    ]
    report = build_cdr_calibration_report(samples, n_bins=4)

    assert report.ready is True
    assert "CALIBRATION_SCORE_CLAMPED_2" in report.notes


def test_calibration_report_invalid_bin_count() -> None:
    with pytest.raises(ValueError):
        build_cdr_calibration_report([], n_bins=0)
