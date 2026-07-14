from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal
from uuid import UUID

from pydantic import Field

from abby_api.schemas.common import (
    AbbyBaseModel,
    ArtifactReference,
    ConfidenceClass,
    Explainability,
    JobStatus,
    PredictionInterval,
    PredictionMode,
    Provenance,
    SimulationProvenance,
)


class PredictionOptions(AbbyBaseModel):
    return_all_models: bool = False
    include_explainability: bool = True
    temperature_kelvin: float = 298.15
    contact_distance_cutoff_angstrom: float = Field(default=5.5, gt=0.0, le=20.0)


class PredictionRequest(AbbyBaseModel):
    project_id: UUID
    mode: PredictionMode
    structure_id: UUID
    options: PredictionOptions = Field(default_factory=PredictionOptions)
    metadata: dict[str, str] = Field(default_factory=dict)


class ModelPrediction(AbbyBaseModel):
    model_id: str
    log_k: float
    delta_g_kcal_mol: float | None = None
    r_validation: float | None = None


class PredictionConsensus(AbbyBaseModel):
    log_k: float
    delta_g_kcal_mol: float
    pi90: PredictionInterval
    confidence: ConfidenceClass
    ood_flag: bool


class FeatureSummary(AbbyBaseModel):
    descriptor_version: str
    source: str
    artifact_key: str | None = None
    artifact_url: str | None = None
    descriptors: dict[str, float] = Field(default_factory=dict)
    partner_residues: dict[str, int] = Field(default_factory=dict)
    residue_class_fractions: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class PredictionResult(AbbyBaseModel):
    prediction_id: UUID
    status: JobStatus
    mode: PredictionMode
    consensus: PredictionConsensus | None = None
    best_model: ModelPrediction | None = None
    all_models: list[ModelPrediction] = Field(default_factory=list)
    feature_summary: FeatureSummary | None = None
    explainability: Explainability | None = None
    provenance: Provenance | None = None


class PredictionQueuedResponse(AbbyBaseModel):
    prediction_id: UUID
    status: Literal["queued"]


class BatchJobRequest(AbbyBaseModel):
    project_id: UUID
    mode: PredictionMode
    structure_ids: list[UUID]
    options: PredictionOptions = Field(default_factory=PredictionOptions)


class BatchCounts(AbbyBaseModel):
    queued: int
    running: int
    completed: int
    failed: int


class BatchJob(AbbyBaseModel):
    job_id: UUID
    project_id: UUID
    status: JobStatus
    counts: BatchCounts
    created_at: datetime
    updated_at: datetime


class BatchJobQueuedResponse(AbbyBaseModel):
    job_id: UUID
    status: Literal["queued"]


class BatchResultsPage(AbbyBaseModel):
    page: int
    page_size: int
    total: int
    items: list[PredictionResult]


class ExportResponse(AbbyBaseModel):
    format: Literal["csv", "json"]
    download_url: str


class SimulationImportRequest(AbbyBaseModel):
    force_field: str | None = None
    water_model: str | None = None
    ionization: str | None = None
    minimization_protocol: str | None = None
    seed: int | None = None
    engine: str = "gromacs_external"
    engine_version: str | None = None
    topology_reference_url: str | None = None
    topology_reference_format: str | None = None
    trajectory_summary: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class SimulationImportResponse(AbbyBaseModel):
    prediction_id: UUID
    status: Literal["imported"]
    simulation: SimulationProvenance
    provenance: Provenance
    trajectory_summary_artifact: ArtifactReference


class SimulationRunRequest(AbbyBaseModel):
    """Request an optional GROMACS-backed simulation run for a prediction.

    The simulation is dispatched to the dedicated simulation worker so it
    does not block the default prediction queue.
    """

    force_field: str = "amber99sb-ildn"
    water_model: str = "tip3p"
    ionization: str = "0.15M NaCl"
    minimization_protocol: str = "steepest_descent"
    seed: int | None = None
    max_steps: int = 500


class SimulationRunResponse(AbbyBaseModel):
    """Immediate response confirming that a simulation task was queued."""

    prediction_id: UUID
    task_id: str
    status: Literal["queued"]
    gromacs_available: bool
    notes: list[str] = Field(default_factory=list)
