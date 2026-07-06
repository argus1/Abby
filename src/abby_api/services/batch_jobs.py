from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from abby_api.repositories.memory import get_batch_job, get_prediction, list_project_jobs, save_batch_job
from abby_api.schemas.predictions import (
    BatchCounts,
    BatchJob,
    BatchJobQueuedResponse,
    BatchJobRequest,
    BatchResultsPage,
    ExportResponse,
)


def create_batch_job(request: BatchJobRequest) -> BatchJobQueuedResponse:
    if not request.structure_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one structure is required.")
    now = datetime.now(timezone.utc)
    job = BatchJob(
        job_id=uuid4(),
        project_id=request.project_id,
        status="queued",
        counts=BatchCounts(queued=len(request.structure_ids), running=0, completed=0, failed=0),
        created_at=now,
        updated_at=now,
    )
    save_batch_job(job)
    return BatchJobQueuedResponse(job_id=job.job_id, status="queued")


def get_job(job_id: UUID) -> BatchJob:
    job = get_batch_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch job not found.")
    return job


def list_jobs(project_id: UUID) -> list[BatchJob]:
    return list_project_jobs(project_id)


def get_results(job_id: UUID, page: int, page_size: int) -> BatchResultsPage:
    job = get_job(job_id)
    items = []
    total = 0
    if job.status == "completed":
        all_predictions = []
        total = len(all_predictions)
        items = all_predictions[(page - 1) * page_size : page * page_size]
    return BatchResultsPage(page=page, page_size=page_size, total=total, items=items)


def export_results(job_id: UUID, export_format: str) -> ExportResponse:
    _ = get_job(job_id)
    return ExportResponse(format=export_format, download_url=f"https://downloads.abby.local/{job_id}.{export_format}")
