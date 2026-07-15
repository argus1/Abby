from __future__ import annotations

from datetime import datetime, timezone
from importlib.util import find_spec

from abby_api import __version__
from abby_api.core.config import get_settings
from abby_api.schemas.system import (
    CDRAnnotationCapabilityStatus,
    DependencyStatus,
    HealthCapabilities,
    HealthResponse,
    ModelBundle,
    ModelListResponse,
    VersionResponse,
)
from abby_api.services.cdr_annotation import CDR_REGION_NAMES, CDR_WARNING_ERROR_CODES
from abby_api.services.cdr_telemetry import get_cdr_annotation_telemetry_snapshot


def _module_available(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _dependency_status(
    name: str, *, required: bool = False, import_name: str | None = None, detail: str | None = None
) -> DependencyStatus:
    module_name = import_name or name
    available = _module_available(module_name)
    return DependencyStatus(name=name, available=available, required=required, detail=detail)


def _cdr_annotation_capabilities() -> HealthCapabilities:
    backend_available = _module_available("Bio.PDB")
    numbering_support_available = backend_available and bool(CDR_REGION_NAMES)
    motif_fallback_available = backend_available
    typed_validation_issues_available = backend_available and bool(CDR_WARNING_ERROR_CODES)
    telemetry = get_cdr_annotation_telemetry_snapshot()
    detail = (
        "Deterministic CDR annotation backend is available with numbered boundaries, "
        "motif fallback, typed validation issues, and in-process telemetry counters."
        if backend_available
        else "BioPython is unavailable, so structural CDR annotation cannot run."
    )
    return HealthCapabilities(
        cdr_annotation=CDRAnnotationCapabilityStatus(
            backend_available=backend_available,
            numbering_support_available=numbering_support_available,
            motif_fallback_available=motif_fallback_available,
            typed_validation_issues_available=typed_validation_issues_available,
            telemetry=telemetry,
            detail=detail,
        )
    )


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
        capabilities=_cdr_annotation_capabilities(),
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
