from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from abby_api.core.security import require_api_key
from abby_api.schemas.projects import Project, ProjectCreateRequest, ProjectJobsResponse
from abby_api.services import batch_jobs, projects

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("", response_model=Project, status_code=201)
def create_project(payload: ProjectCreateRequest) -> Project:
    return projects.create_project(payload.name)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: UUID) -> Project:
    return projects.get_project(project_id)


@router.get("/{project_id}/jobs", response_model=ProjectJobsResponse)
def list_project_jobs(project_id: UUID) -> ProjectJobsResponse:
    projects.get_project(project_id)
    return ProjectJobsResponse(jobs=batch_jobs.list_jobs(project_id))
