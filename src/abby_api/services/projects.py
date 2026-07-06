from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from abby_api.repositories.memory import new_project, store
from abby_api.schemas.projects import Project


def create_project(name: str) -> Project:
    return new_project(name)


def get_project(project_id: UUID) -> Project:
    project = store.projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project
