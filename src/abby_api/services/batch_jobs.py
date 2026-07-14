from __future__ import annotations

from csv import DictWriter
from datetime import datetime, timezone
from io import StringIO
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from abby_api.repositories.memory import (
    get_batch_job,
    get_batch_job_execution,
    get_prediction,
    list_project_jobs,
    save_batch_job,
    save_batch_job_execution,
)
from abby_api.schemas.predictions import (
    BatchCounts,
    BatchJob,
    BatchJobQueuedResponse,
    BatchJobRequest,
    BatchResultsPage,
    ExportResponse,
    PredictionRequest,
)
from abby_api.services import predictions
from abby_api.storage.object_store import ObjectStore
from abby_api.workers.tasks import submit_batch_job_task


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_csv_export_payload(job: BatchJob, items: list[dict[str, str]]) -> bytes:
    buffer = StringIO()
    writer = DictWriter(
        buffer,
        fieldnames=[
            "job_id",
            "prediction_id",
            "structure_id",
            "status",
            "mode",
            "log_k",
            "delta_g_kcal_mol",
            "confidence",
            "ood_flag",
            "descriptor_hash",
            "contact_distance_cutoff_angstrom",
            "error",
        ],
    )
    writer.writeheader()
    for item in items:
        writer.writerow(item)
    return buffer.getvalue().encode("utf-8")


def _collect_export_rows(job_id: UUID) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    execution = get_batch_job_execution(job_id)
    if execution is None:
        return [], []

    rows: list[dict[str, str]] = []
    prediction_payloads: list[dict[str, str]] = []
    prediction_items = execution.prediction_items or [
        {
            "prediction_id": str(prediction_id),
            "structure_id": "",
        }
        for prediction_id in execution.prediction_ids
    ]
    for prediction_item in prediction_items:
        raw_prediction_id = prediction_item.get("prediction_id")
        if raw_prediction_id is None:
            continue
        prediction = get_prediction(UUID(raw_prediction_id))
        if prediction is None:
            continue
        structure_id = prediction_item.get("structure_id", "")
        prediction_payloads.append(
            {
                "prediction_id": str(prediction.prediction_id),
                "structure_id": structure_id,
                "status": prediction.status,
                "mode": prediction.mode,
                "log_k": "" if prediction.consensus is None else str(prediction.consensus.log_k),
                "delta_g_kcal_mol": ""
                if prediction.consensus is None
                else str(prediction.consensus.delta_g_kcal_mol),
            }
        )
        rows.append(
            {
                "job_id": str(job_id),
                "prediction_id": str(prediction.prediction_id),
                "structure_id": structure_id,
                "status": prediction.status,
                "mode": prediction.mode,
                "log_k": "" if prediction.consensus is None else str(prediction.consensus.log_k),
                "delta_g_kcal_mol": ""
                if prediction.consensus is None
                else str(prediction.consensus.delta_g_kcal_mol),
                "confidence": ""
                if prediction.consensus is None
                else prediction.consensus.confidence,
                "ood_flag": ""
                if prediction.consensus is None
                else str(prediction.consensus.ood_flag),
                "descriptor_hash": ""
                if prediction.provenance is None
                else prediction.provenance.descriptor_hash,
                "contact_distance_cutoff_angstrom": ""
                if prediction.provenance is None
                else str(prediction.provenance.contact_distance_cutoff_angstrom),
                "error": "",
            }
        )

    for failure in execution.failures:
        rows.append(
            {
                "job_id": str(job_id),
                "prediction_id": "",
                "structure_id": failure.get("structure_id", ""),
                "status": "failed",
                "mode": "",
                "log_k": "",
                "delta_g_kcal_mol": "",
                "confidence": "",
                "ood_flag": "",
                "descriptor_hash": "",
                "contact_distance_cutoff_angstrom": "",
                "error": failure.get("error", "Batch prediction failed"),
            }
        )

    return rows, prediction_payloads


def create_batch_job(request: BatchJobRequest) -> BatchJobQueuedResponse:
    if not request.structure_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="At least one structure is required."
        )
    now = _now_utc()
    job = BatchJob(
        job_id=uuid4(),
        project_id=request.project_id,
        status="queued",
        counts=BatchCounts(queued=len(request.structure_ids), running=0, completed=0, failed=0),
        created_at=now,
        updated_at=now,
    )
    save_batch_job(job)

    submit_batch_job_task(lambda: _execute_batch_job(job_id=job.job_id, request=request))
    return BatchJobQueuedResponse(job_id=job.job_id, status="queued")


def _execute_batch_job(*, job_id: UUID, request: BatchJobRequest) -> None:
    job = get_job(job_id)
    running_job = BatchJob(
        job_id=job.job_id,
        project_id=job.project_id,
        status="running",
        counts=BatchCounts(queued=0, running=len(request.structure_ids), completed=0, failed=0),
        created_at=job.created_at,
        updated_at=_now_utc(),
    )
    save_batch_job(running_job)

    prediction_ids: list[UUID] = []
    prediction_items: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []

    try:
        for structure_id in request.structure_ids:
            try:
                queued = predictions.create_prediction(
                    PredictionRequest(
                        project_id=request.project_id,
                        mode=request.mode,
                        structure_id=structure_id,
                        options=request.options,
                        metadata={"batch_job_id": str(job_id)},
                    )
                )
                prediction_ids.append(queued.prediction_id)
                prediction_items.append(
                    {
                        "prediction_id": str(queued.prediction_id),
                        "structure_id": str(structure_id),
                    }
                )
            except HTTPException as exc:
                failures.append(
                    {
                        "structure_id": str(structure_id),
                        "error": str(exc.detail),
                    }
                )
    except Exception as exc:  # pragma: no cover - defensive failure capture
        failures.append(
            {
                "structure_id": "*",
                "error": f"Unexpected batch execution error: {exc}",
            }
        )

    completed_count = len(prediction_ids)
    failed_count = len(failures)
    terminal_status = "completed" if completed_count > 0 else "failed"
    finalized_job = BatchJob(
        job_id=job_id,
        project_id=request.project_id,
        status=terminal_status,
        counts=BatchCounts(queued=0, running=0, completed=completed_count, failed=failed_count),
        created_at=job.created_at,
        updated_at=_now_utc(),
    )
    save_batch_job(finalized_job)
    save_batch_job_execution(
        job_id=job_id,
        prediction_ids=prediction_ids,
        prediction_items=prediction_items,
        failures=failures,
    )


def get_job(job_id: UUID) -> BatchJob:
    job = get_batch_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch job not found.")
    return job


def list_jobs(project_id: UUID) -> list[BatchJob]:
    return list_project_jobs(project_id)


def get_results(job_id: UUID, page: int, page_size: int) -> BatchResultsPage:
    _ = get_job(job_id)
    execution = get_batch_job_execution(job_id)
    all_predictions = []
    if execution is not None:
        all_predictions = [
            prediction
            for prediction_id in execution.prediction_ids
            if (prediction := get_prediction(prediction_id)) is not None
        ]

    total = len(all_predictions)
    items = all_predictions[(page - 1) * page_size : page * page_size]
    return BatchResultsPage(page=page, page_size=page_size, total=total, items=items)


def export_results(job_id: UUID, export_format: str) -> ExportResponse:
    job = get_job(job_id)
    rows, prediction_payloads = _collect_export_rows(job_id)
    object_store = ObjectStore()
    artifact_key = f"projects/{job.project_id}/batch_jobs/{job_id}/results.{export_format}"

    if export_format == "json":
        object_store.put_json(
            artifact_key,
            {
                "job_id": str(job_id),
                "project_id": str(job.project_id),
                "status": job.status,
                "counts": job.counts.model_dump(),
                "predictions": prediction_payloads,
                "failures": get_batch_job_execution(job_id).failures
                if get_batch_job_execution(job_id)
                else [],
                "rows": rows,
            },
        )
    else:
        object_store.put_bytes(artifact_key, _build_csv_export_payload(job, rows))

    return ExportResponse(
        format=export_format, download_url=object_store.signed_download_url(artifact_key)
    )
