from __future__ import annotations

from abby_api.schemas.common import AbbyBaseModel


class DependencyStatus(AbbyBaseModel):
    name: str
    available: bool
    required: bool = False
    detail: str | None = None


class HealthResponse(AbbyBaseModel):
    status: str
    timestamp: str
    version: str
    dependencies: list[DependencyStatus] = []


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
