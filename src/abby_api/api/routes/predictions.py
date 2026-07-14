from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from abby_api.core.security import require_api_key
from abby_api.schemas.common import Explainability
from abby_api.schemas.predictions import (
    LearnedModelInferenceResult,
    LearnedModelRunRequest,
    LearnedModelRunResponse,
    PredictionQueuedResponse,
    PredictionRequest,
    PredictionResult,
    SimulationImportRequest,
    SimulationImportResponse,
    SimulationRunRequest,
    SimulationRunResponse,
    StructureGenerationIngestionRequest,
    StructureGenerationIngestionResponse,
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


@router.post(
    "/{prediction_id}/simulation:run", response_model=SimulationRunResponse, status_code=202
)
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


# ---------------------------------------------------------------------------
# Phase 6A: Learned structural modeling endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{prediction_id}/learned-model:run",
    response_model=LearnedModelRunResponse,
    status_code=202,
)
def run_learned_model(
    prediction_id: UUID,
    payload: LearnedModelRunRequest,
) -> LearnedModelRunResponse:
    """Submit a GNN inference task for an existing prediction.

    Dispatches to the first available GNN backend (DeepFRI → ProteinMPNN →
    stub).  The task runs asynchronously through the general worker backend.
    Query ``GET /{prediction_id}`` provenance for the result.

    Phase 6A: GNN integration path.
    """
    return predictions.run_learned_model(prediction_id, payload)


@router.get(
    "/{prediction_id}/learned-model",
    response_model=LearnedModelInferenceResult,
)
def get_learned_model_result(prediction_id: UUID) -> LearnedModelInferenceResult:
    """Return the learned-model inference result for a prediction.

    Returns 404 when no learned-model run has been submitted yet.

    Phase 6A: learned-model provenance retrieval.
    """
    return predictions.get_learned_model_result(prediction_id)


# ---------------------------------------------------------------------------
# Phase 6B: Structure-generation ingestion endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/{prediction_id}/structure-generation:ingest",
    response_model=StructureGenerationIngestionResponse,
)
def ingest_structure_generation(
    prediction_id: UUID,
    payload: StructureGenerationIngestionRequest,
) -> StructureGenerationIngestionResponse:
    """Import an externally generated or refined structure into a prediction.

    Supports AlphaFold 3, Boltz-1, Rosetta, and generic external structures.
    Stores structured provenance metadata and an artifact reference so Abby
    can trace the origin of each structure under analysis.

    Phase 6B: upstream structure-generation ingestion contract.
    """
    return predictions.ingest_structure_generation(prediction_id, payload)
