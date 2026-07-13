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


class ArtifactReference(AbbyBaseModel):
    artifact_type: str
    artifact_key: str | None = None
    artifact_url: str | None = None
    external_url: str | None = None
    format: str | None = None


class TopologyHandoffMetadata(AbbyBaseModel):
    normalized_chain_map: dict[str, str] = Field(default_factory=dict)
    canonical_partner_1: list[str] = Field(default_factory=list)
    canonical_partner_2: list[str] = Field(default_factory=list)
    preserved_connectivity: dict[str, Any] = Field(default_factory=dict)
    non_standard_residues: dict[str, dict[str, int]] = Field(default_factory=dict)
    preprocessing_warnings: list[str] = Field(default_factory=list)


class SimulationProvenance(AbbyBaseModel):
    source: str = "none"
    imported: bool = False
    force_field: str | None = None
    water_model: str | None = None
    ionization: str | None = None
    minimization_protocol: str | None = None
    seed: int | None = None
    engine: str | None = None
    engine_version: str | None = None
    notes: list[str] = Field(default_factory=list)


class ArtifactRegistry(AbbyBaseModel):
    normalized_structure: ArtifactReference | None = None
    topology_reference: ArtifactReference | None = None
    trajectory_summary: ArtifactReference | None = None
    feature_summary: ArtifactReference | None = None


class Provenance(AbbyBaseModel):
    model_bundle_version: str
    preprocess_version: str
    descriptor_hash: str
    contact_distance_cutoff_angstrom: float
    created_at: datetime
    topology_handoff: TopologyHandoffMetadata | None = None
    simulation: SimulationProvenance | None = None
    artifacts: ArtifactRegistry | None = None
