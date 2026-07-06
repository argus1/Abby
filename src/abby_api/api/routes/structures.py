from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from abby_api.core.security import require_api_key
from abby_api.schemas.structures import StructureDetail, StructureInput, StructureValidationRequest, StructureValidationResult
from abby_api.services import structures

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/structures:upload", response_model=StructureInput, status_code=201)
async def upload_structure(
    file: UploadFile = File(...),
    mode: str = Form(...),
    project_id: str | None = Form(default=None),
) -> StructureInput:
    _ = project_id
    return await structures.upload_structure(file=file, mode=mode)


@router.post("/structures:validate", response_model=StructureValidationResult)
def validate_structure(payload: StructureValidationRequest) -> StructureValidationResult:
    return structures.validate_structure(payload)


@router.get("/structures/{structure_id}", response_model=StructureDetail)
def get_structure(structure_id: UUID) -> StructureDetail:
    return structures.get_structure_detail(structure_id)
