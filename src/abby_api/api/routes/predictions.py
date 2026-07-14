from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from abby_api.core.security import require_api_key
from abby_api.schemas.common import Explainability
from abby_api.schemas.predictions import (
    PredictionQueuedResponse,
    PredictionRequest,
    PredictionResult,
    SimulationImportRequest,
    SimulationImportResponse,
    SimulationRunRequest,
    SimulationRunResponse,
)
from abby_api.services import predictions

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("", response_model=PredictionQueuedResponse, status_code=202)
def create_prediction(payload: PredictionRequest) -> PredictionQueuedResponse:
    return predictions.create_prediction(payload)


@router.get("/{prediction_id}", response_model=PredictionResult)
def get_prediction(prediction_id: UUID) -> PredictionResult:
    return predictions.get_prediction(prediction_id)


@router.get("/{prediction_id}/explainability", response_model=Explainability)
def get_explainability(prediction_id: UUID) -> Explainability:
    prediction = predictions.get_prediction(prediction_id)
    return prediction.explainability or Explainability(top_descriptors=[])


@router.post("/{prediction_id}/simulation-summary:import", response_model=SimulationImportResponse)
def import_simulation_summary(
    prediction_id: UUID,
    payload: SimulationImportRequest,
) -> SimulationImportResponse:
    return predictions.import_simulation_summary(prediction_id, payload)


@router.post("/{prediction_id}/simulation:run", response_model=SimulationRunResponse, status_code=202)
def run_simulation(
    prediction_id: UUID,
    payload: SimulationRunRequest,
) -> SimulationRunResponse:
    """Submit an optional GROMACS-backed simulation task for this prediction.

    The task is dispatched to the dedicated simulation worker backend and does
    not affect the default prediction queue.  Returns immediately with a task
    ID; query the prediction provenance later to retrieve simulation outputs.
    """
    return predictions.run_simulation(prediction_id, payload)
