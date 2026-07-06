from __future__ import annotations

"""Worker entry points for future async execution.

These functions are placeholders that mirror the worker types described in
Backend_Architecture_Abby.md. They can later be bound to Celery, RQ, or another
job orchestration system.
"""


def validate_structure_task(structure_id: str) -> None:
    _ = structure_id


def generate_descriptors_task(structure_id: str, mode: str) -> None:
    _ = (structure_id, mode)


def run_prediction_task(prediction_id: str) -> None:
    _ = prediction_id


def export_batch_results_task(job_id: str, export_format: str) -> None:
    _ = (job_id, export_format)
