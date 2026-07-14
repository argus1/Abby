"""Worker task submission helpers.

These wrappers expose a backend-agnostic async interface so service code can
submit tasks without knowing worker runtime details.
"""

from __future__ import annotations

from collections.abc import Callable

from abby_api.core.config import get_settings
from abby_api.workers.backend import (
    WorkerBackend,
    WorkerBackendType,
    get_worker_backend,
    initialize_worker_backend,
)


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


# ---------------------------------------------------------------------------
# Phase 5: dedicated simulation worker runtime
# ---------------------------------------------------------------------------

_simulation_backend: WorkerBackend | None = None
_simulation_backend_type: WorkerBackendType | None = None


def initialize_simulation_worker_backend(
    *,
    backend_type: WorkerBackendType | None = None,
    worker_count: int | None = None,
) -> WorkerBackend:
    """Start and return the dedicated simulation worker backend.

    The simulation backend is isolated from the general prediction queue so
    that long-running GROMACS jobs do not delay normal prediction requests.
    Settings default to ``ABBY_SIMULATION_WORKER_BACKEND`` / ``ABBY_SIMULATION_WORKER_THREADS``.
    """
    global _simulation_backend, _simulation_backend_type

    settings = get_settings()
    resolved_type: WorkerBackendType = backend_type or settings.simulation_worker_backend
    resolved_count = (
        worker_count if worker_count is not None else settings.simulation_worker_threads
    )

    if _simulation_backend is not None and _simulation_backend_type != resolved_type:
        _simulation_backend.stop()
        _simulation_backend = None

    if _simulation_backend is None:
        from abby_api.workers.backend import _make_backend

        _simulation_backend = _make_backend(backend_type=resolved_type, worker_count=resolved_count)
        _simulation_backend_type = resolved_type

    _simulation_backend.start()
    return _simulation_backend


def get_simulation_worker_backend() -> WorkerBackend:
    """Return the active simulation worker backend.

    Raises ``RuntimeError`` when the backend has not been initialized.
    """
    if _simulation_backend is None:
        raise RuntimeError("Simulation worker backend has not been initialized.")
    return _simulation_backend


def shutdown_simulation_worker_backend() -> None:
    """Stop the simulation worker backend and clear the singleton."""
    global _simulation_backend, _simulation_backend_type
    if _simulation_backend is None:
        return
    _simulation_backend.stop()
    _simulation_backend = None
    _simulation_backend_type = None


def submit_simulation_task(runner: Callable[[], None]) -> str:
    """Submit a simulation task to the dedicated simulation worker backend.

    If the simulation backend has not been initialized yet, it is started
    automatically using the ``ABBY_SIMULATION_WORKER_BACKEND`` setting.
    """
    try:
        backend = get_simulation_worker_backend()
    except RuntimeError:
        backend = initialize_simulation_worker_backend()
    return backend.submit(task_name="simulation", run=runner)
