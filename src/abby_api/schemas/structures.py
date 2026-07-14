from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from abby_api.schemas.common import AbbyBaseModel, PredictionMode, StructureFormat


class ChainMapping(AbbyBaseModel):
    partner_1: list[str] = Field(default_factory=list)
    partner_2: list[str] = Field(default_factory=list)


class StructureInput(AbbyBaseModel):
    structure_id: UUID
    format: StructureFormat
    source: Literal["upload", "pdb_id", "derived"]
    filename: str
    sha256: str
    chains: ChainMapping | None = None
    mode: PredictionMode


class StructureValidationRequest(AbbyBaseModel):
    structure_id: UUID
    mode: PredictionMode
    chains: ChainMapping


class StructureValidationIssue(AbbyBaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StructureSummary(AbbyBaseModel):
    parser_name: str
    model_count: int
    available_chains: list[str] = Field(default_factory=list)
    residue_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    warning_details: list[StructureValidationIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructureValidationResult(AbbyBaseModel):
    valid: bool
    normalized_format: Literal["pdb", "mmcif"]
    inferred_roles: dict[str, str] = Field(default_factory=dict)
    available_chains: list[str] = Field(default_factory=list)
    model_count: int = 0
    chain_groups: ChainMapping | None = None
    partner_residue_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    warning_details: list[StructureValidationIssue] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    error_details: list[StructureValidationIssue] = Field(default_factory=list)
    md_handoff: dict[str, Any] = Field(default_factory=dict)


class StructureDetail(StructureInput):
    validation: StructureValidationResult | None = None
    summary: StructureSummary | None = None
