from __future__ import annotations

from threading import Event
from time import sleep

import pytest

from abby_api.workers.backend import (
    get_worker_backend,
    get_worker_backend_type,
    initialize_worker_backend,
    shutdown_worker_backend,
)


def teardown_function() -> None:
    shutdown_worker_backend()


def test_inline_backend_executes_task_immediately() -> None:
    initialize_worker_backend(backend_type="inline")
    backend = get_worker_backend()

    marker: list[str] = []
    task_id = backend.submit("inline-task", lambda: marker.append("ran"))

    assert task_id
    assert marker == ["ran"]
    assert get_worker_backend_type() == "inline"


def test_in_process_backend_executes_task_asynchronously() -> None:
    initialize_worker_backend(backend_type="in_process", worker_count=1)
    backend = get_worker_backend()

    event = Event()
    task_id = backend.submit("threaded-task", event.set)

    assert task_id
    assert event.wait(1.0)
    assert get_worker_backend_type() == "in_process"
    task = backend.get_task(task_id)
    assert task is not None
    assert task.status == "completed"
    assert task.started_at is not None
    assert task.finished_at is not None


def test_in_process_backend_captures_failed_task_state() -> None:
    initialize_worker_backend(backend_type="in_process", worker_count=1)
    backend = get_worker_backend()

    def _boom() -> None:
        raise RuntimeError("kaboom")

    task_id = backend.submit("failing-task", _boom)
    assert task_id

    deadline_seconds = 1.0
    elapsed = 0.0
    task = backend.get_task(task_id)
    while (task is None or task.status in {"queued", "running"}) and elapsed < deadline_seconds:
        sleep(0.02)
        elapsed += 0.02
        task = backend.get_task(task_id)

    assert task is not None
    assert task.status == "failed"
    assert task.error is not None
    assert "kaboom" in task.error
    assert task.finished_at is not None


def test_backend_type_switch_reinitializes_backend() -> None:
    initialize_worker_backend(backend_type="in_process", worker_count=1)
    assert get_worker_backend_type() == "in_process"

    initialize_worker_backend(backend_type="inline")
    assert get_worker_backend_type() == "inline"


def test_celery_stub_backend_is_selectable_and_fails_fast_on_submit() -> None:
    initialize_worker_backend(backend_type="celery_stub")
    backend = get_worker_backend()

    assert get_worker_backend_type() == "celery_stub"
    with pytest.raises(RuntimeError, match="celery_stub"):
        backend.submit("stub-task", lambda: None)
