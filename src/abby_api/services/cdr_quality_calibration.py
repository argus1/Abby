from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CDRCalibrationSample:
    score: float
    observed_positive: bool


@dataclass(frozen=True)
class CDRCalibrationBin:
    index: int
    lower_bound: float
    upper_bound: float
    count: int
    mean_score: float
    observed_rate: float
    abs_calibration_gap: float


@dataclass(frozen=True)
class CDRCalibrationReport:
    ready: bool
    method: str
    n_samples: int
    n_bins: int
    ece: float
    mce: float
    brier_score: float
    auc_roc: float | None
    bins: list[CDRCalibrationBin]
    notes: list[str]


def build_cdr_calibration_report(
    samples: Iterable[CDRCalibrationSample],
    *,
    n_bins: int = 10,
) -> CDRCalibrationReport:
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")

    sample_list = list(samples)
    if not sample_list:
        return CDRCalibrationReport(
            ready=False,
            method="equal_width_binning",
            n_samples=0,
            n_bins=n_bins,
            ece=0.0,
            mce=0.0,
            brier_score=0.0,
            auc_roc=None,
            bins=[],
            notes=["CALIBRATION_NO_SAMPLES"],
        )

    notes: list[str] = []
    clamped_scores: list[float] = []
    labels: list[int] = []
    clamp_count = 0
    for sample in sample_list:
        raw_score = float(sample.score)
        clamped = min(max(raw_score, 0.0), 1.0)
        if clamped != raw_score:
            clamp_count += 1
        clamped_scores.append(clamped)
        labels.append(1 if sample.observed_positive else 0)

    if clamp_count > 0:
        notes.append(f"CALIBRATION_SCORE_CLAMPED_{clamp_count}")

    bin_width = 1.0 / float(n_bins)
    bin_scores: list[list[float]] = [[] for _ in range(n_bins)]
    bin_labels: list[list[int]] = [[] for _ in range(n_bins)]

    for score, label in zip(clamped_scores, labels):
        bin_index = min(int(score / bin_width), n_bins - 1)
        bin_scores[bin_index].append(score)
        bin_labels[bin_index].append(label)

    calibration_bins: list[CDRCalibrationBin] = []
    total = len(clamped_scores)
    ece = 0.0
    mce = 0.0
    for index in range(n_bins):
        lower = round(index * bin_width, 6)
        upper = round((index + 1) * bin_width, 6)
        scores = bin_scores[index]
        bucket_labels = bin_labels[index]
        count = len(scores)
        if count == 0:
            mean_score = 0.0
            observed_rate = 0.0
            gap = 0.0
        else:
            mean_score = sum(scores) / float(count)
            observed_rate = sum(bucket_labels) / float(count)
            gap = abs(mean_score - observed_rate)
            ece += (float(count) / float(total)) * gap
            mce = max(mce, gap)

        calibration_bins.append(
            CDRCalibrationBin(
                index=index,
                lower_bound=lower,
                upper_bound=upper,
                count=count,
                mean_score=round(mean_score, 6),
                observed_rate=round(observed_rate, 6),
                abs_calibration_gap=round(gap, 6),
            )
        )

    brier = (
        sum((score - float(label)) ** 2 for score, label in zip(clamped_scores, labels))
        / float(total)
    )

    positives = sum(labels)
    negatives = total - positives
    auc_roc: float | None
    if positives == 0 or negatives == 0:
        auc_roc = None
        notes.append("CALIBRATION_AUC_UNDEFINED_SINGLE_CLASS")
    else:
        auc_roc = round(_rank_auc(clamped_scores, labels), 6)

    return CDRCalibrationReport(
        ready=True,
        method="equal_width_binning",
        n_samples=total,
        n_bins=n_bins,
        ece=round(ece, 6),
        mce=round(mce, 6),
        brier_score=round(brier, 6),
        auc_roc=auc_roc,
        bins=calibration_bins,
        notes=notes,
    )


def _rank_auc(scores: list[float], labels: list[int]) -> float:
    ranked = sorted(enumerate(scores), key=lambda item: item[1])
    ranks = [0.0] * len(scores)

    cursor = 0
    while cursor < len(ranked):
        end = cursor
        while end + 1 < len(ranked) and ranked[end + 1][1] == ranked[cursor][1]:
            end += 1
        avg_rank = (cursor + 1 + end + 1) / 2.0
        for slot in range(cursor, end + 1):
            ranks[ranked[slot][0]] = avg_rank
        cursor = end + 1

    positive_count = sum(labels)
    negative_count = len(labels) - positive_count
    positive_rank_sum = sum(rank for rank, label in zip(ranks, labels) if label == 1)
    u_stat = positive_rank_sum - (positive_count * (positive_count + 1) / 2.0)
    return u_stat / float(positive_count * negative_count)
