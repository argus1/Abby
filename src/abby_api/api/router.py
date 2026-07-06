from __future__ import annotations

from fastapi import APIRouter

from abby_api.api.routes import batch_jobs, predictions, projects, structures, system

api_router = APIRouter()
api_router.include_router(system.router, tags=["System"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(structures.router, tags=["Structures"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
api_router.include_router(batch_jobs.router, prefix="/batch-jobs", tags=["Batch Jobs"])
