from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from abby_api.schemas.predictions import (
    BatchCounts,
    BatchJob,
    PredictionConsensus,
    PredictionResult,
)
from abby_api.schemas.projects import Project
from abby_api.schemas.structures import StructureDetail, StructureInput, StructureSummary, StructureValidationResult


@dataclass
class MemoryStore:
    projects: dict[UUID, Project] = field(default_factory=dict)
    structures: dict[UUID, StructureDetail] = field(default_factory=dict)
    structure_files: dict[UUID, Path] = field(default_factory=dict)
    predictions: dict[UUID, PredictionResult] = field(default_factory=dict)
    feature_summary_artifacts: dict[UUID, FeatureSummaryArtifactRecord] = field(default_factory=dict)
    batch_jobs: dict[UUID, BatchJob] = field(default_factory=dict)
    batch_job_execution: dict[UUID, BatchJobExecutionRecord] = field(default_factory=dict)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


store = MemoryStore()


@dataclass
class FeatureSummaryArtifactRecord:
    prediction_id: UUID
    project_id: UUID
    structure_id: UUID
    descriptor_hash: str
    artifact_key: str
    artifact_url: str
    created_at: datetime


@dataclass
class BatchJobExecutionRecord:
    job_id: UUID
    prediction_ids: list[UUID] = field(default_factory=list)
    prediction_items: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)


def new_project(name: str) -> Project:
    project = Project(project_id=uuid4(), name=name, owner="local-dev", created_at=store.now())
    store.projects[project.project_id] = project
    return project


def save_structure(
    structure: StructureInput,
    *,
    file_path: Path | None = None,
    summary: StructureSummary | None = None,
) -> StructureDetail:
    detail = StructureDetail(**structure.model_dump(), validation=None, summary=summary)
    store.structures[structure.structure_id] = detail
    if file_path is not None:
        store.structure_files[structure.structure_id] = file_path
    return detail


def get_structure(structure_id: UUID) -> StructureDetail | None:
    return store.structures.get(structure_id)


def get_structure_file(structure_id: UUID) -> Path | None:
    return store.structure_files.get(structure_id)


def set_validation(structure_id: UUID, validation: StructureValidationResult) -> StructureDetail | None:
    detail = store.structures.get(structure_id)
    if detail is None:
        return None
    detail.validation = validation
    return detail


def set_structure_summary(structure_id: UUID, summary: StructureSummary) -> StructureDetail | None:
    detail = store.structures.get(structure_id)
    if detail is None:
        return None
    detail.summary = summary
    return detail


def save_prediction(prediction: PredictionResult) -> PredictionResult:
    store.predictions[prediction.prediction_id] = prediction
    return prediction


def save_feature_summary_artifact(
    *,
    prediction_id: UUID,
    project_id: UUID,
    structure_id: UUID,
    descriptor_hash: str,
    artifact_key: str,
    artifact_url: str,
) -> FeatureSummaryArtifactRecord:
    record = FeatureSummaryArtifactRecord(
        prediction_id=prediction_id,
        project_id=project_id,
        structure_id=structure_id,
        descriptor_hash=descriptor_hash,
        artifact_key=artifact_key,
        artifact_url=artifact_url,
        created_at=store.now(),
    )
    store.feature_summary_artifacts[prediction_id] = record
    return record


def get_feature_summary_artifact(prediction_id: UUID) -> FeatureSummaryArtifactRecord | None:
    return store.feature_summary_artifacts.get(prediction_id)


def list_project_feature_summary_artifacts(project_id: UUID) -> list[FeatureSummaryArtifactRecord]:
    return [
        item
        for item in store.feature_summary_artifacts.values()
        if item.project_id == project_id
    ]


def get_prediction(prediction_id: UUID) -> PredictionResult | None:
    return store.predictions.get(prediction_id)


def save_batch_job(batch_job: BatchJob) -> BatchJob:
    store.batch_jobs[batch_job.job_id] = batch_job
    return batch_job


def get_batch_job(job_id: UUID) -> BatchJob | None:
    return store.batch_jobs.get(job_id)


def list_project_jobs(project_id: UUID) -> list[BatchJob]:
    return [job for job in store.batch_jobs.values() if job.project_id == project_id]


def save_batch_job_execution(
    *,
    job_id: UUID,
    prediction_ids: list[UUID],
    prediction_items: list[dict[str, str]] | None = None,
    failures: list[dict[str, str]],
) -> BatchJobExecutionRecord:
    normalized_prediction_items = prediction_items or [
        {
            "prediction_id": str(prediction_id),
            "structure_id": "",
        }
        for prediction_id in prediction_ids
    ]
    record = BatchJobExecutionRecord(
        job_id=job_id,
        prediction_ids=prediction_ids,
        prediction_items=normalized_prediction_items,
        failures=failures,
    )
    store.batch_job_execution[job_id] = record
    return record


def get_batch_job_execution(job_id: UUID) -> BatchJobExecutionRecord | None:
    return store.batch_job_execution.get(job_id)
