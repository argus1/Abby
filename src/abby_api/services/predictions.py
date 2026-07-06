from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from abby_api.core.config import get_settings
from abby_api.repositories.memory import (
    get_structure_file,
    get_structure,
    save_feature_summary_artifact,
    save_prediction,
)
from abby_api.schemas.common import PredictionInterval, Provenance
from abby_api.schemas.predictions import (
    ModelPrediction,
    PredictionConsensus,
    PredictionQueuedResponse,
    PredictionRequest,
    PredictionResult,
)
from abby_api.services.baseline_models import (
    derive_delta_g_kcal_mol,
    run_baseline_affinity_models,
)
from abby_api.services.feature_extraction import (
    build_descriptor_bundle,
    calculate_inter_partner_contacts,
    calculate_solvent_accessibility,
    make_explainability_summary,
    make_feature_summary,
)
from abby_api.services.structure_parsing import parse_structure_file
from abby_api.storage.object_store import ObjectStore


def _persist_feature_summary_artifact(
    *,
    object_store: ObjectStore,
    prediction_id: UUID,
    request: PredictionRequest,
    descriptor_hash: str,
    feature_summary_payload: dict[str, object],
) -> tuple[str, str]:
    artifact_key = f"projects/{request.project_id}/predictions/{prediction_id}/feature_summary.json"
    artifact_payload: dict[str, object] = {
        "prediction_id": str(prediction_id),
        "project_id": str(request.project_id),
        "structure_id": str(request.structure_id),
        "mode": request.mode,
        "descriptor_hash": descriptor_hash,
        "contact_distance_cutoff_angstrom": request.options.contact_distance_cutoff_angstrom,
        "feature_summary": feature_summary_payload,
    }
    object_store.put_json(artifact_key, artifact_payload)
    artifact_url = object_store.signed_download_url(artifact_key)
    save_feature_summary_artifact(
        prediction_id=prediction_id,
        project_id=request.project_id,
        structure_id=request.structure_id,
        descriptor_hash=descriptor_hash,
        artifact_key=artifact_key,
        artifact_url=artifact_url,
    )
    return artifact_key, artifact_url


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

    contact_observation = None
    solvent_accessibility = None
    structure_file = get_structure_file(request.structure_id)
    if structure_file is not None:
        try:
            parsed_structure, _ = parse_structure_file(
                structure_file,
                "mmcif" if structure.format in {"mmcif", "cif"} else "pdb",
            )
            contact_observation = calculate_inter_partner_contacts(
                parsed_structure,
                structure.validation,
                distance_cutoff=request.options.contact_distance_cutoff_angstrom,
            )
            solvent_accessibility = calculate_solvent_accessibility(
                parsed_structure,
                structure.validation,
            )
        except Exception:
            contact_observation = None
            solvent_accessibility = None

    bundle = build_descriptor_bundle(
        structure.summary,
        structure.validation,
        request.mode,
        contact_observation=contact_observation,
        solvent_accessibility=solvent_accessibility,
        contact_distance_cutoff=request.options.contact_distance_cutoff_angstrom,
    )
    scoring = run_baseline_affinity_models(bundle.descriptors)
    log_k = scoring.consensus_log_k
    delta_g = derive_delta_g_kcal_mol(log_k, request.options.temperature_kelvin)
    best = scoring.scores[0]
    all_model_predictions = [
        ModelPrediction(
            model_id=item.model_id,
            log_k=item.log_k,
            delta_g_kcal_mol=derive_delta_g_kcal_mol(item.log_k, request.options.temperature_kelvin),
            r_validation=item.r_validation,
        )
        for item in scoring.scores
    ]
    settings = get_settings()
    prediction_id = uuid4()
    feature_summary = make_feature_summary(bundle)
    object_store = ObjectStore()
    artifact_key, artifact_url = _persist_feature_summary_artifact(
        object_store=object_store,
        prediction_id=prediction_id,
        request=request,
        descriptor_hash=bundle.descriptor_hash,
        feature_summary_payload=feature_summary.model_dump(mode="json"),
    )
    feature_summary.artifact_key = artifact_key
    feature_summary.artifact_url = artifact_url

    result = PredictionResult(
        prediction_id=prediction_id,
        status="completed",
        mode=request.mode,
        consensus=PredictionConsensus(
            log_k=log_k,
            delta_g_kcal_mol=delta_g,
            pi90=PredictionInterval(
                lower=round(log_k - scoring.interval_half_width, 2),
                upper=round(log_k + scoring.interval_half_width, 2),
            ),
            confidence=scoring.confidence,
            ood_flag=scoring.ood_flag,
        ),
        best_model=ModelPrediction(
            model_id=best.model_id,
            log_k=best.log_k,
            delta_g_kcal_mol=derive_delta_g_kcal_mol(best.log_k, request.options.temperature_kelvin),
            r_validation=best.r_validation,
        ),
        all_models=all_model_predictions if request.options.return_all_models else [],
        feature_summary=feature_summary,
        explainability=make_explainability_summary(bundle) if request.options.include_explainability else None,
        provenance=Provenance(
            model_bundle_version=settings.model_bundle_version,
            preprocess_version=settings.preprocess_version,
            descriptor_hash=bundle.descriptor_hash,
            contact_distance_cutoff_angstrom=request.options.contact_distance_cutoff_angstrom,
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
