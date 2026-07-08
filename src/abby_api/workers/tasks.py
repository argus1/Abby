from __future__ import annotations

"""Worker task submission helpers.

These wrappers expose a backend-agnostic async interface so service code can
submit tasks without knowing worker runtime details.
"""

from collections.abc import Callable

from abby_api.core.config import get_settings
from abby_api.workers.backend import get_worker_backend, initialize_worker_backend


def submit_task(task_name: str, runner: Callable[[], None]) -> str:
    settings = get_settings()
    try:
        backend = get_worker_backend()
    except RuntimeError:
        backend = initialize_worker_backend(
            backend_type=settings.worker_backend,
            worker_count=settings.worker_threads,
        )
    return backend.submit(task_name=task_name, run=runner)


def submit_batch_job_task(runner: Callable[[], None]) -> str:
    return submit_task("batch_job", runner)


def submit_export_batch_results_task(runner: Callable[[], None]) -> str:
    return submit_task("export_batch_results", runner)
