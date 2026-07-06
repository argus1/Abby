from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from abby_api.schemas.common import AbbyBaseModel
from abby_api.schemas.predictions import BatchJob


class ProjectCreateRequest(AbbyBaseModel):
    name: str = Field(min_length=1, max_length=200)


class Project(AbbyBaseModel):
    project_id: UUID
    name: str
    owner: str
    created_at: datetime


class ProjectJobsResponse(AbbyBaseModel):
    jobs: list[BatchJob]
