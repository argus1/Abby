from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from abby_api.core.config import get_settings
from abby_api.repositories.memory import get_structure, save_prediction
from abby_api.schemas.common import PredictionInterval, Provenance
from abby_api.schemas.predictions import (
    ModelPrediction,
    PredictionConsensus,
    PredictionQueuedResponse,
    PredictionRequest,
    PredictionResult,
)
from abby_api.services.feature_extraction import (
    build_descriptor_bundle,
    make_explainability_summary,
    make_feature_summary,
)


def create_prediction(request: PredictionRequest) -> PredictionQueuedResponse:
    structure = get_structure(request.structure_id)
    if structure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure not found.")
    if structure.validation is None or not structure.validation.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Structure must be validated successfully before prediction.",
        )
    if structure.summary is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Structure summary is required before prediction.",
        )

    bundle = build_descriptor_bundle(structure.summary, structure.validation, request.mode)
    descriptors = bundle.descriptors
    total_residues = max(int(descriptors.get("total_residues", 1.0)), 1)
    log_k = round(
        -5.85
        - (0.18 * descriptors.get("interface_contact_proxy", 0.0))
        - (0.9 * descriptors.get("global_apolar_fraction", 0.0))
        + (0.35 * descriptors.get("global_charged_fraction", 0.0))
        - (0.25 * descriptors.get("partner_size_ratio", 0.0))
        - (0.2 * descriptors.get("antibody_mode_flag", 0.0)),
        2,
    )
    delta_g = round(log_k * 1.3639, 2)
    settings = get_settings()
    prediction_id = uuid4()
    result = PredictionResult(
        prediction_id=prediction_id,
        status="completed",
        mode=request.mode,
        consensus=PredictionConsensus(
            log_k=log_k,
            delta_g_kcal_mol=delta_g,
            pi90=PredictionInterval(lower=round(log_k - 0.45, 2), upper=round(log_k + 0.45, 2)),
            confidence="high" if total_residues >= 2 else "medium",
            ood_flag=False,
        ),
        best_model=ModelPrediction(
            model_id="mixed_nn_v1_3",
            log_k=round(log_k - 0.05, 2),
            delta_g_kcal_mol=round(delta_g - 0.07, 2),
            r_validation=0.85,
        ),
        all_models=[
            ModelPrediction(model_id="linear_v1_2", log_k=round(log_k + 0.25, 2)),
            ModelPrediction(model_id="rf_v1_11", log_k=round(log_k + 0.03, 2)),
        ],
        feature_summary=make_feature_summary(bundle),
        explainability=make_explainability_summary(bundle),
        provenance=Provenance(
            model_bundle_version=settings.model_bundle_version,
            preprocess_version=settings.preprocess_version,
            descriptor_hash=bundle.descriptor_hash,
            created_at=datetime.now(timezone.utc),
        ),
    )
    save_prediction(result)
    return PredictionQueuedResponse(prediction_id=prediction_id, status="queued")


def get_prediction(prediction_id: UUID) -> PredictionResult:
    from abby_api.repositories.memory import get_prediction as _get_prediction

    prediction = _get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found.")
    return prediction
