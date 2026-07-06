from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from abby_api.core.security import require_api_key
from abby_api.schemas.predictions import (
    BatchJob,
    BatchJobQueuedResponse,
    BatchJobRequest,
    BatchResultsPage,
    ExportResponse,
)
from abby_api.services import batch_jobs

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("", response_model=BatchJobQueuedResponse, status_code=202)
def create_batch_job(payload: BatchJobRequest) -> BatchJobQueuedResponse:
    return batch_jobs.create_batch_job(payload)


@router.get("/{job_id}", response_model=BatchJob)
def get_batch_job(job_id: UUID) -> BatchJob:
    return batch_jobs.get_job(job_id)


@router.get("/{job_id}/results", response_model=BatchResultsPage)
def list_batch_results(
    job_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> BatchResultsPage:
    return batch_jobs.get_results(job_id, page, page_size)


@router.get("/{job_id}/export", response_model=ExportResponse)
def export_batch_results(job_id: UUID, format: str = Query(..., pattern="^(csv|json)$")) -> ExportResponse:
    return batch_jobs.export_results(job_id, format)
