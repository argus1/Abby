from __future__ import annotations

from datetime import datetime, timezone

from abby_api import __version__
from abby_api.core.config import get_settings
from abby_api.schemas.system import HealthResponse, ModelBundle, ModelListResponse, VersionResponse


def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=__version__,
    )


def get_version() -> VersionResponse:
    settings = get_settings()
    return VersionResponse(
        api_version=__version__,
        model_bundle_version=settings.model_bundle_version,
        preprocess_version=settings.preprocess_version,
    )


def list_models() -> ModelListResponse:
    settings = get_settings()
    return ModelListResponse(
        models=[
            ModelBundle(
                model_bundle_version=settings.model_bundle_version,
                modes=["ppi_general", "antibody_antigen"],
                validation_metrics={"ppi_general_r": 0.87, "antibody_antigen_r": 0.85},
            )
        ]
    )
