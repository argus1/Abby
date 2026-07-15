from __future__ import annotations

from abby_api.schemas.common import AbbyBaseModel


class DependencyStatus(AbbyBaseModel):
    name: str
    available: bool
    required: bool = False
    detail: str | None = None


class CDRAnnotationCapabilityStatus(AbbyBaseModel):
    backend_available: bool
    numbering_support_available: bool
    motif_fallback_available: bool
    typed_validation_issues_available: bool
    telemetry: "CDRAnnotationTelemetrySnapshot | None" = None
    detail: str | None = None


class CDRAnnotationTelemetrySnapshot(AbbyBaseModel):
    total_antibody_summaries: int = 0
    numbering_based_count: int = 0
    numbering_based_percent: float = 0.0
    motif_fallback_count: int = 0
    motif_fallback_percent: float = 0.0
    ambiguous_or_failed_count: int = 0
    ambiguous_or_failed_percent: float = 0.0


class HealthCapabilities(AbbyBaseModel):
    cdr_annotation: CDRAnnotationCapabilityStatus


class HealthResponse(AbbyBaseModel):
    status: str
    timestamp: str
    version: str
    dependencies: list[DependencyStatus] = []
    capabilities: HealthCapabilities | None = None


class VersionResponse(AbbyBaseModel):
    api_version: str
    model_bundle_version: str
    preprocess_version: str


class ModelBundle(AbbyBaseModel):
    model_bundle_version: str
    modes: list[str]
    validation_metrics: dict[str, float]


class ModelListResponse(AbbyBaseModel):
    models: list[ModelBundle]
