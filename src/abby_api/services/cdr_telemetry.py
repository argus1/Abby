from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from abby_api.schemas.system import CDRAnnotationTelemetrySnapshot
from abby_api.services.cdr_annotation import (
    CDR_BOUNDARY_AMBIGUOUS,
    CDR_CHAIN_ROLE_AMBIGUOUS,
    CDR_MOTIF_FALLBACK_USED,
)


@dataclass(slots=True)
class _TelemetryCounts:
    total_antibody_summaries: int = 0
    numbering_based_count: int = 0
    motif_fallback_count: int = 0
    ambiguous_or_failed_count: int = 0


class _CDRTelemetryCollector:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts = _TelemetryCounts()

    def reset(self) -> None:
        with self._lock:
            self._counts = _TelemetryCounts()

    def record(self, annotation: dict[str, Any]) -> None:
        warnings = {
            str(code).strip()
            for code in annotation.get("warnings", [])
            if str(code).strip()
        }
        boundary_source = str(annotation.get("boundary_source") or "").strip()
        available = bool(annotation.get("available", False))

        with self._lock:
            self._counts.total_antibody_summaries += 1

            if boundary_source == "numbered":
                self._counts.numbering_based_count += 1

            if (
                boundary_source in {"motif_fallback", "hybrid"}
                or CDR_MOTIF_FALLBACK_USED in warnings
            ):
                self._counts.motif_fallback_count += 1

            if (
                not available
                or CDR_BOUNDARY_AMBIGUOUS in warnings
                or CDR_CHAIN_ROLE_AMBIGUOUS in warnings
            ):
                self._counts.ambiguous_or_failed_count += 1

    def snapshot(self) -> CDRAnnotationTelemetrySnapshot:
        with self._lock:
            counts = _TelemetryCounts(
                total_antibody_summaries=self._counts.total_antibody_summaries,
                numbering_based_count=self._counts.numbering_based_count,
                motif_fallback_count=self._counts.motif_fallback_count,
                ambiguous_or_failed_count=self._counts.ambiguous_or_failed_count,
            )

        return CDRAnnotationTelemetrySnapshot(
            total_antibody_summaries=counts.total_antibody_summaries,
            numbering_based_count=counts.numbering_based_count,
            numbering_based_percent=_to_percent(
                counts.numbering_based_count,
                counts.total_antibody_summaries,
            ),
            motif_fallback_count=counts.motif_fallback_count,
            motif_fallback_percent=_to_percent(
                counts.motif_fallback_count,
                counts.total_antibody_summaries,
            ),
            ambiguous_or_failed_count=counts.ambiguous_or_failed_count,
            ambiguous_or_failed_percent=_to_percent(
                counts.ambiguous_or_failed_count,
                counts.total_antibody_summaries,
            ),
        )


def _to_percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


_collector = _CDRTelemetryCollector()


def record_cdr_annotation_telemetry(annotation: dict[str, Any]) -> None:
    _collector.record(annotation)


def get_cdr_annotation_telemetry_snapshot() -> CDRAnnotationTelemetrySnapshot:
    return _collector.snapshot()


def reset_cdr_annotation_telemetry() -> None:
    _collector.reset()