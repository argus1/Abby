from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Callable, Literal, Protocol
from uuid import uuid4


TaskCallable = Callable[[], None]
WorkerBackendType = Literal["in_process", "inline", "celery_stub"]


@dataclass
class _QueuedTask:
    task_id: str
    task_name: str
    run: TaskCallable


class WorkerBackend(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def submit(self, task_name: str, run: TaskCallable) -> str: ...


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
        self._queue.put(_QueuedTask(task_id=task_id, task_name=task_name, run=run))
        return task_id

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
                task.run()
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
        _ = task_name
        task_id = str(uuid4())
        run()
        return task_id


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


_backend: WorkerBackend | None = None
_backend_type: WorkerBackendType | None = None


def _make_backend(*, backend_type: WorkerBackendType, worker_count: int) -> WorkerBackend:
    if backend_type == "celery_stub":
        return CeleryStubWorkerBackend()
    if backend_type == "inline":
        return InlineWorkerBackend()
    return InProcessWorkerBackend(worker_count=worker_count)


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
