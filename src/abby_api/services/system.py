from __future__ import annotations

from datetime import datetime, timezone
from importlib.util import find_spec

from abby_api import __version__
from abby_api.core.config import get_settings
from abby_api.schemas.system import (
    DependencyStatus,
    HealthResponse,
    ModelBundle,
    ModelListResponse,
    VersionResponse,
)


def _dependency_status(
    name: str, *, required: bool = False, import_name: str | None = None, detail: str | None = None
) -> DependencyStatus:
    module_name = import_name or name
    available = find_spec(module_name) is not None
    return DependencyStatus(name=name, available=available, required=required, detail=detail)


def _health_dependencies() -> list[DependencyStatus]:
    return [
        _dependency_status(
            "BioPython",
            required=True,
            import_name="Bio.PDB",
            detail="Structure parsing and connectivity preservation",
        ),
        _dependency_status("Gemmi", import_name="gemmi", detail="PDB→mmCIF conversion helper"),
        _dependency_status(
            "MDAnalysis", import_name="MDAnalysis", detail="Optional trajectory aggregation"
        ),
        _dependency_status("freesasa", import_name="freesasa", detail="Optional SASA acceleration"),
        _dependency_status(
            "Gromacs-CIF",
            import_name="gmx",
            detail="Optional CIF-aware simulation backend / gmx CLI",
        ),
    ]


def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=__version__,
        dependencies=_health_dependencies(),
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
