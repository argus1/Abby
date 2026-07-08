from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from abby_api import __version__
from abby_api.api.router import api_router
from abby_api.core.config import get_settings
from abby_api.workers.backend import initialize_worker_backend, shutdown_worker_backend


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    initialize_worker_backend(
        backend_type=settings.worker_backend,
        worker_count=settings.worker_threads,
    )
    yield
    shutdown_worker_backend()


settings = get_settings()
app = FastAPI(
    title="Abby API",
    version=__version__,
    summary="Starter FastAPI server for Abby affinity prediction workflows",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
