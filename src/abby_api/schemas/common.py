from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

PredictionMode = Literal["ppi_general", "antibody_antigen"]
ConfidenceClass = Literal["high", "medium", "low"]
JobStatus = Literal["queued", "running", "completed", "failed"]
StructureFormat = Literal["pdb", "cif", "mmcif"]


class AbbyBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ErrorObject(AbbyBaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: UUID


class ErrorResponse(AbbyBaseModel):
    error: ErrorObject


class PredictionInterval(AbbyBaseModel):
    lower: float
    upper: float


class DescriptorContribution(AbbyBaseModel):
    name: str
    contribution: float


class Explainability(AbbyBaseModel):
    top_descriptors: list[DescriptorContribution]


class Provenance(AbbyBaseModel):
    model_bundle_version: str
    preprocess_version: str
    descriptor_hash: str
    created_at: datetime
