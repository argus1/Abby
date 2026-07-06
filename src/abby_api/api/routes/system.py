from __future__ import annotations

from fastapi import APIRouter

from abby_api.schemas.system import HealthResponse, ModelListResponse, VersionResponse
from abby_api.services import system

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return system.get_health()


@router.get("/version", response_model=VersionResponse)
def get_version() -> VersionResponse:
    return system.get_version()


@router.get("/models", response_model=ModelListResponse)
def list_models() -> ModelListResponse:
    return system.list_models()
