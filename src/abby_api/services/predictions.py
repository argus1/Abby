from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from abby_api.core.config import get_settings
from abby_api.repositories.memory import get_structure, get_structure_file, save_feature_summary_artifact, save_prediction
from abby_api.schemas.common import (
    ArtifactReference,
    ArtifactRegistry,
    PredictionInterval,
    Provenance,
    SimulationProvenance,
    TopologyHandoffMetadata,
)
from abby_api.schemas.predictions import (
    ModelPrediction,
    PredictionConsensus,
    PredictionQueuedResponse,
    PredictionRequest,
    PredictionResult,
    SimulationImportRequest,
    SimulationImportResponse,
    SimulationRunRequest,
    SimulationRunResponse,
)
from abby_api.services.baseline_models import (
    derive_delta_g_kcal_mol,
    run_baseline_affinity_models,
)
from abby_api.services.feature_extraction import (
    build_descriptor_bundle,
    calculate_inter_partner_contacts,
    calculate_radius_of_gyration,
    calculate_residue_depth,
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


def _persist_normalized_structure_artifact(
    *,
    object_store: ObjectStore,
    prediction_id: UUID,
    request: PredictionRequest,
) -> tuple[str, str] | None:
    structure_file = get_structure_file(request.structure_id)
    if structure_file is None:
        return None
    extension = structure_file.suffix.lower() or ".pdb"
    artifact_key = (
        f"projects/{request.project_id}/predictions/{prediction_id}/normalized_structure{extension}"
    )
    object_store.put_bytes(artifact_key, structure_file.read_bytes())
    return artifact_key, object_store.signed_download_url(artifact_key)


def _build_topology_handoff_metadata(
    *,
    structure_summary: object,
    structure_validation: object,
) -> TopologyHandoffMetadata:
    summary_metadata = getattr(structure_summary, "metadata", {}) or {}
    validation_warnings = list(getattr(structure_validation, "warnings", []) or [])
    md_handoff = getattr(structure_validation, "md_handoff", {}) or {}
    return TopologyHandoffMetadata(
        normalized_chain_map=dict(md_handoff.get("canonical_chain_map", {})),
        canonical_partner_1=list(md_handoff.get("canonical_partner_1", [])),
        canonical_partner_2=list(md_handoff.get("canonical_partner_2", [])),
        preserved_connectivity=dict(summary_metadata.get("connectivity", {})),
        non_standard_residues=dict(summary_metadata.get("unsupported_residue_counts", {})),
        preprocessing_warnings=validation_warnings,
    )


def _project_id_from_prediction(prediction: PredictionResult) -> UUID:
    artifact_key = prediction.feature_summary.artifact_key if prediction.feature_summary else None
    if not artifact_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction does not include project artifact metadata required for simulation import.",
        )
    prefix = "projects/"
    if not artifact_key.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to derive project scope from artifact key.",
        )
    remainder = artifact_key[len(prefix):]
    segments = remainder.split("/")
    if len(segments) < 2 or not segments[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction artifact key is missing required project path segments.",
        )
    project_token = segments[0]
    try:
        return UUID(project_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction artifact key includes an invalid project identifier.",
        ) from exc


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
    residue_depth_observation = None
    radius_of_gyration_observation = None
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
            residue_depth_observation = calculate_residue_depth(
                parsed_structure,
                structure.validation,
                distance_cutoff=request.options.contact_distance_cutoff_angstrom,
            )
            radius_of_gyration_observation = calculate_radius_of_gyration(
                parsed_structure,
                structure.validation,
            )
        except Exception:
            contact_observation = None
            solvent_accessibility = None
            residue_depth_observation = None
            radius_of_gyration_observation = None

    bundle = build_descriptor_bundle(
        structure.summary,
        structure.validation,
        request.mode,
        contact_observation=contact_observation,
        solvent_accessibility=solvent_accessibility,
        residue_depth_observation=residue_depth_observation,
        radius_of_gyration_observation=radius_of_gyration_observation,
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
    normalized_artifact = _persist_normalized_structure_artifact(
        object_store=object_store,
        prediction_id=prediction_id,
        request=request,
    )
    feature_summary.artifact_key = artifact_key
    feature_summary.artifact_url = artifact_url
    topology_handoff = _build_topology_handoff_metadata(
        structure_summary=structure.summary,
        structure_validation=structure.validation,
    )

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
            topology_handoff=topology_handoff,
            simulation=SimulationProvenance(
                source="none",
                imported=False,
                notes=["SIMULATION_NOT_YET_RUN"],
            ),
            artifacts=ArtifactRegistry(
                normalized_structure=(
                    ArtifactReference(
                        artifact_type="normalized_structure",
                        artifact_key=normalized_artifact[0],
                        artifact_url=normalized_artifact[1],
                        format=structure.format,
                    )
                    if normalized_artifact is not None
                    else None
                ),
                feature_summary=ArtifactReference(
                    artifact_type="feature_summary",
                    artifact_key=artifact_key,
                    artifact_url=artifact_url,
                    format="json",
                ),
            ),
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


def import_simulation_summary(
    prediction_id: UUID,
    payload: SimulationImportRequest,
) -> SimulationImportResponse:
    prediction = get_prediction(prediction_id)
    if prediction.provenance is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction provenance is required before importing simulation artifacts.",
        )

    project_id = _project_id_from_prediction(prediction)
    object_store = ObjectStore()
    artifact_key = (
        f"projects/{project_id}/predictions/{prediction_id}/simulation/trajectory_summary.json"
    )
    object_store.put_json(
        artifact_key,
        {
            "prediction_id": str(prediction_id),
            "trajectory_summary": payload.trajectory_summary,
            "notes": payload.notes,
        },
    )
    trajectory_artifact = ArtifactReference(
        artifact_type="trajectory_summary",
        artifact_key=artifact_key,
        artifact_url=object_store.signed_download_url(artifact_key),
        format="json",
    )

    existing_artifacts = prediction.provenance.artifacts
    if existing_artifacts is None:
        existing_artifacts = ArtifactRegistry()
        prediction.provenance.artifacts = existing_artifacts
    existing_artifacts.trajectory_summary = trajectory_artifact
    if payload.topology_reference_url:
        existing_artifacts.topology_reference = ArtifactReference(
            artifact_type="topology_reference",
            external_url=payload.topology_reference_url,
            format=payload.topology_reference_format or "unknown",
        )

    simulation = SimulationProvenance(
        source="external_import",
        imported=True,
        force_field=payload.force_field,
        water_model=payload.water_model,
        ionization=payload.ionization,
        minimization_protocol=payload.minimization_protocol,
        seed=payload.seed,
        engine=payload.engine,
        engine_version=payload.engine_version,
        notes=payload.notes,
    )
    prediction.provenance.simulation = simulation
    prediction.provenance.artifacts = existing_artifacts
    save_prediction(prediction)

    refreshed_prediction = get_prediction(prediction_id)
    if refreshed_prediction.provenance is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simulation import failed to persist provenance.",
        )
    return SimulationImportResponse(
        prediction_id=prediction_id,
        status="imported",
        simulation=simulation,
        provenance=refreshed_prediction.provenance,
        trajectory_summary_artifact=trajectory_artifact,
    )


def run_simulation(
    prediction_id: UUID,
    payload: SimulationRunRequest,
) -> SimulationRunResponse:
    """Submit a GROMACS-backed simulation task for an existing prediction.

    The simulation runs asynchronously via the dedicated simulation worker
    backend so it does not block the default prediction queue.  When GROMACS
    is not installed the task still completes immediately with a stub result
    so the caller receives a well-formed response.

    Phase 5A: optional GROMACS-CIF execution path.
    """
    from abby_api.services.simulation import (
        SimulationRunConfig,
        is_gromacs_available,
        run_gromacs_cif_simulation,
    )
    from abby_api.workers.tasks import submit_simulation_task

    prediction = get_prediction(prediction_id)
    if prediction.provenance is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction provenance is required before running a simulation.",
        )

    project_id = _project_id_from_prediction(prediction)

    # Resolve structure file from prediction provenance artifact registry.
    structure_file_path: Path | None = None
    if prediction.provenance.artifacts and prediction.provenance.artifacts.normalized_structure:
        artifact_key = prediction.provenance.artifacts.normalized_structure.artifact_key
        if artifact_key:
            object_store = ObjectStore()
            raw = object_store.get_bytes(artifact_key)
            if raw is not None:
                import tempfile
                suffix = f".{artifact_key.rsplit('.', 1)[-1]}" if "." in artifact_key else ".pdb"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(raw)
                tmp.flush()
                structure_file_path = Path(tmp.name)

    config = SimulationRunConfig(
        force_field=payload.force_field,
        water_model=payload.water_model,
        ionization=payload.ionization,
        minimization_protocol=payload.minimization_protocol,
        seed=payload.seed,
        max_steps=payload.max_steps,
    )
    gromacs_ready = is_gromacs_available()
    notes: list[str] = []

    def _run() -> None:
        import tempfile as _tempfile
        if structure_file_path is not None:
            _structure_path = structure_file_path
        else:
            # Create a minimal empty temp file so run_gromacs_cif_simulation
            # receives a real path (GROMACS will error, which produces a stub result).
            _tmp = _tempfile.NamedTemporaryFile(delete=False, suffix=".pdb")
            _tmp.close()
            _structure_path = Path(_tmp.name)
        result = run_gromacs_cif_simulation(
            _structure_path,
            config,
            prediction_id=prediction_id,
            project_id=project_id,
        )
        # Persist updated simulation provenance back to the prediction.
        _prediction = get_prediction(prediction_id)
        if _prediction.provenance is not None:
            _prediction.provenance.simulation = result.provenance
            existing = _prediction.provenance.artifacts or ArtifactRegistry()
            if result.artifact_registry.topology_reference is not None:
                existing.topology_reference = result.artifact_registry.topology_reference
            if result.artifact_registry.trajectory_summary is not None:
                existing.trajectory_summary = result.artifact_registry.trajectory_summary
            _prediction.provenance.artifacts = existing
            save_prediction(_prediction)

    task_id = submit_simulation_task(_run)
    return SimulationRunResponse(
        prediction_id=prediction_id,
        task_id=task_id,
        status="queued",
        gromacs_available=gromacs_ready,
        notes=notes,
    )
