from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Callable, Literal, Protocol
from uuid import uuid4


TaskCallable = Callable[[], None]
WorkerBackendType = Literal["in_process", "inline", "celery_stub"]
WorkerTaskStatus = Literal["queued", "running", "completed", "failed"]


@dataclass
class _QueuedTask:
    task_id: str
    task_name: str
    run: TaskCallable


@dataclass
class WorkerTaskRecord:
    task_id: str
    task_name: str
    status: WorkerTaskStatus
    submitted_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class WorkerBackend(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def submit(self, task_name: str, run: TaskCallable) -> str: ...

    def get_task(self, task_id: str) -> WorkerTaskRecord | None: ...


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InProcessWorkerBackend:
    """Simple in-process async worker backend.

    This backend provides a true asynchronous interface for local/dev execution
    by queueing tasks and processing them on background worker threads.
    """

    def __init__(self, *, worker_count: int = 1) -> None:
        self._worker_count = max(1, worker_count)
        self._queue: Queue[_QueuedTask | None] = Queue()
        self._threads: list[Thread] = []
        self._stop_event = Event()
        self._started = False
        self._lock = Lock()
        self._task_lock = Lock()
        self._tasks: dict[str, WorkerTaskRecord] = {}

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._stop_event.clear()
            self._threads = [
                Thread(target=self._worker_loop, name=f"abby-worker-{index}", daemon=True)
                for index in range(self._worker_count)
            ]
            for thread in self._threads:
                thread.start()
            self._started = True

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            self._stop_event.set()
            for _ in self._threads:
                self._queue.put(None)
            for thread in self._threads:
                thread.join(timeout=2.0)
            self._threads = []
            self._started = False

    def submit(self, task_name: str, run: TaskCallable) -> str:
        task_id = str(uuid4())
        with self._task_lock:
            self._tasks[task_id] = WorkerTaskRecord(
                task_id=task_id,
                task_name=task_name,
                status="queued",
                submitted_at=_utc_now_iso(),
            )
        self._queue.put(_QueuedTask(task_id=task_id, task_name=task_name, run=run))
        return task_id

    def get_task(self, task_id: str) -> WorkerTaskRecord | None:
        with self._task_lock:
            return self._tasks.get(task_id)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if task is None:
                self._queue.task_done()
                continue
            try:
                with self._task_lock:
                    task_record = self._tasks.get(task.task_id)
                    if task_record is not None:
                        task_record.status = "running"
                        task_record.started_at = _utc_now_iso()
                task.run()
                with self._task_lock:
                    task_record = self._tasks.get(task.task_id)
                    if task_record is not None:
                        task_record.status = "completed"
                        task_record.finished_at = _utc_now_iso()
            except Exception as exc:  # pragma: no cover - exercised through integration paths
                with self._task_lock:
                    task_record = self._tasks.get(task.task_id)
                    if task_record is not None:
                        task_record.status = "failed"
                        task_record.error = str(exc)
                        task_record.finished_at = _utc_now_iso()
            finally:
                self._queue.task_done()


class InlineWorkerBackend:
    """Executes submitted tasks immediately in the caller thread.

    Useful for tests, debugging, or deterministic execution modes.
    """

    def start(self) -> None:  # pragma: no cover - trivial no-op
        return

    def stop(self) -> None:  # pragma: no cover - trivial no-op
        return

    def submit(self, task_name: str, run: TaskCallable) -> str:
        task_id = str(uuid4())
        self._tasks[task_id] = WorkerTaskRecord(
            task_id=task_id,
            task_name=task_name,
            status="running",
            submitted_at=_utc_now_iso(),
            started_at=_utc_now_iso(),
        )
        try:
            run()
            self._tasks[task_id].status = "completed"
        except Exception as exc:
            self._tasks[task_id].status = "failed"
            self._tasks[task_id].error = str(exc)
            raise
        finally:
            self._tasks[task_id].finished_at = _utc_now_iso()
        return task_id

    def __init__(self) -> None:
        self._tasks: dict[str, WorkerTaskRecord] = {}

    def get_task(self, task_id: str) -> WorkerTaskRecord | None:
        return self._tasks.get(task_id)


class CeleryStubWorkerBackend:
    """Stub backend placeholder for a future Celery integration.

    This backend intentionally fails fast on submit with a clear configuration
    message so deployments don't silently accept tasks that will never run.
    """

    def start(self) -> None:  # pragma: no cover - trivial no-op
        return

    def stop(self) -> None:  # pragma: no cover - trivial no-op
        return

    def submit(self, task_name: str, run: TaskCallable) -> str:
        _ = (task_name, run)
        raise RuntimeError(
            "Worker backend 'celery_stub' is a placeholder. Configure a real Celery adapter before submitting tasks."
        )

    def get_task(self, task_id: str) -> WorkerTaskRecord | None:
        _ = task_id
        return None


_backend: WorkerBackend | None = None
_backend_type: WorkerBackendType | None = None


def _make_backend(*, backend_type: WorkerBackendType, worker_count: int) -> WorkerBackend:
    if backend_type == "celery_stub":
        return CeleryStubWorkerBackend()
    if backend_type == "inline":
        return InlineWorkerBackend()
    if backend_type == "in_process":
        return InProcessWorkerBackend(worker_count=worker_count)
    raise ValueError(f"Unsupported worker backend type: {backend_type}")


def initialize_worker_backend(
    *,
    backend_type: WorkerBackendType = "in_process",
    worker_count: int = 1,
) -> WorkerBackend:
    global _backend, _backend_type
    if _backend is not None and _backend_type != backend_type:
        _backend.stop()
        _backend = None

    if _backend is None:
        _backend = _make_backend(backend_type=backend_type, worker_count=worker_count)
        _backend_type = backend_type

    _backend.start()
    return _backend


def get_worker_backend() -> WorkerBackend:
    if _backend is None:
        raise RuntimeError("Worker backend has not been initialized.")
    return _backend


def get_worker_backend_type() -> WorkerBackendType | None:
    return _backend_type


def shutdown_worker_backend() -> None:
    global _backend, _backend_type
    if _backend is None:
        return
    _backend.stop()
    _backend = None
    _backend_type = None
