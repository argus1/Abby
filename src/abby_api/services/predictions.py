from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from abby_api.core.config import get_settings
from abby_api.repositories.memory import (
    get_structure,
    get_structure_file,
    save_feature_summary_artifact,
    save_prediction,
)
from abby_api.schemas.common import (
    ArtifactReference,
    ArtifactRegistry,
    LearnedModelProvenance,
    PredictionInterval,
    Provenance,
    SimulationProvenance,
    TopologyHandoffMetadata,
)
from abby_api.schemas.predictions import (
    LearnedModelInferenceResult,
    LearnedModelRunRequest,
    LearnedModelRunResponse,
    ModelPrediction,
    PredictionConsensus,
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
            detail=(
                "Prediction does not include project artifact metadata required "
                "for simulation import."
            ),
        )
    prefix = "projects/"
    if not artifact_key.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to derive project scope from artifact key.",
        )
    remainder = artifact_key[len(prefix) :]
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
            delta_g_kcal_mol=derive_delta_g_kcal_mol(
                item.log_k, request.options.temperature_kelvin
            ),
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
            delta_g_kcal_mol=derive_delta_g_kcal_mol(
                best.log_k, request.options.temperature_kelvin
            ),
            r_validation=best.r_validation,
        ),
        all_models=all_model_predictions if request.options.return_all_models else [],
        feature_summary=feature_summary,
        explainability=make_explainability_summary(bundle)
        if request.options.include_explainability
        else None,
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
    # Write to a temp file so the simulation service receives a real Path.
    # The file is closed after writing; cleanup happens at the end of _run().
    structure_file_path: Path | None = None
    structure_tmp_path: Path | None = None  # tracks temp files for cleanup
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
                tmp.close()
                structure_file_path = Path(tmp.name)
                structure_tmp_path = structure_file_path

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
        import os as _os
        import tempfile as _tempfile

        created_tmp: Path | None = None
        if structure_file_path is not None:
            _structure_path = structure_file_path
        else:
            # Create a minimal empty temp file so run_gromacs_cif_simulation
            # receives a real path (GROMACS will error, which produces a stub result).
            fd, _tmp_name = _tempfile.mkstemp(suffix=".pdb")
            _os.close(fd)
            created_tmp = Path(_tmp_name)
            _structure_path = created_tmp

        try:
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
        finally:
            # Clean up temp files created by this task.
            # OSError is silenced here intentionally: cleanup is best-effort because
            # the OS will reclaim the files on process exit even if unlink fails
            # (e.g., due to a concurrent access or cross-filesystem restriction).
            for tmp_path in filter(None, [created_tmp, structure_tmp_path]):
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    task_id = submit_simulation_task(_run)
    return SimulationRunResponse(
        prediction_id=prediction_id,
        task_id=task_id,
        status="queued",
        gromacs_available=gromacs_ready,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Phase 6A: Learned structural modeling – run_learned_model
# ---------------------------------------------------------------------------


def run_learned_model(
    prediction_id: UUID,
    payload: LearnedModelRunRequest,
) -> LearnedModelRunResponse:
    """Submit a GNN inference task for an existing prediction.

    The graph is built from the prediction's structure data and dispatched to
    the first available GNN backend (DeepFRI → ProteinMPNN → stub).  The task
    runs asynchronously through the general worker backend so it does not block
    the prediction queue.

    Phase 6A: GNN integration path.
    """
    from abby_api.services.graph_models import (
        GNNInferenceConfig,
        is_deepfri_available,
        is_proteinmpnn_available,
        run_gnn_inference,
    )
    from abby_api.workers.tasks import submit_task

    prediction = get_prediction(prediction_id)
    if prediction.provenance is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction provenance is required before running a learned model.",
        )

    project_id = _project_id_from_prediction(prediction)

    # Determine which backend will be used for the response metadata.
    if is_deepfri_available():
        model_backend = "deepfri"
        backend_available = True
    elif is_proteinmpnn_available():
        model_backend = "proteinmpnn"
        backend_available = True
    else:
        model_backend = "stub"
        backend_available = False

    gnn_config = GNNInferenceConfig(
        model_id=payload.model_id,
        graph_contact_cutoff_angstrom=payload.graph_contact_cutoff_angstrom,
        include_backbone_edges=payload.include_backbone_edges,
        include_covalent_edges=payload.include_covalent_edges,
    )

    def _run() -> None:
        """Worker closure: build graph, run GNN, persist provenance."""
        structure = None
        validation = None

        # Re-derive structure file from the prediction artifact registry.
        artifact_key = (
            prediction.provenance.artifacts.normalized_structure.artifact_key
            if prediction.provenance
            and prediction.provenance.artifacts
            and prediction.provenance.artifacts.normalized_structure
            else None
        )
        if artifact_key:
            import tempfile as _tempfile

            # Validate the file extension against known structure formats to
            # prevent unexpected suffix values from reaching mkstemp.
            _ALLOWED_STRUCTURE_SUFFIXES = {".pdb", ".cif", ".mmcif", ".ent"}
            raw_suffix = (
                f".{artifact_key.rsplit('.', 1)[-1]}" if "." in artifact_key else ".pdb"
            )
            suffix = raw_suffix if raw_suffix in _ALLOWED_STRUCTURE_SUFFIXES else ".pdb"

            object_store_inner = ObjectStore()
            raw = object_store_inner.get_bytes(artifact_key)
            if raw is not None:
                import os as _os

                fd, tmp_name = _tempfile.mkstemp(suffix=suffix)
                _os.close(fd)
                _tmp_path = Path(tmp_name)
                _tmp_path.write_bytes(raw)
                try:
                    from abby_api.services.structure_parsing import parse_structure_file as _parse

                    fmt = "mmcif" if suffix in {".cif", ".mmcif"} else "pdb"
                    structure, _ = _parse(_tmp_path, fmt)
                finally:
                    try:
                        _tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass

        # Run GNN inference (stub when structure unavailable).
        gnn_result = run_gnn_inference(structure, validation, config=gnn_config)

        # Persist learned-model provenance back to the prediction.
        _prediction = get_prediction(prediction_id)
        if _prediction.provenance is not None:
            _prediction.provenance.learned_model = LearnedModelProvenance(
                model_id=gnn_config.model_id,
                model_backend=gnn_result.model_backend,
                backend_available=gnn_result.backend_available,
                graph_version=gnn_result.graph.graph_version if gnn_result.graph else None,
                notes=list(gnn_result.notes),
            )
            # Persist graph artifact summary to object storage.
            object_store_inner = ObjectStore()
            graph_key = (
                f"projects/{project_id}/predictions/{prediction_id}"
                f"/learned_model/graph_summary.json"
            )
            object_store_inner.put_json(
                graph_key,
                {
                    "prediction_id": str(prediction_id),
                    "model_id": gnn_config.model_id,
                    "model_backend": gnn_result.model_backend,
                    "backend_available": gnn_result.backend_available,
                    "graph_version": gnn_result.graph.graph_version if gnn_result.graph else None,
                    "n_nodes": len(gnn_result.graph.nodes) if gnn_result.graph else 0,
                    "n_edges": len(gnn_result.graph.edges) if gnn_result.graph else 0,
                    "interface_node_count": (
                        len(gnn_result.graph.interface_node_indices) if gnn_result.graph else 0
                    ),
                    "predictions": gnn_result.predictions,
                    "notes": list(gnn_result.notes),
                },
            )
            existing = _prediction.provenance.artifacts or ArtifactRegistry()
            existing.structure_graph = ArtifactReference(
                artifact_type="structure_graph",
                artifact_key=graph_key,
                artifact_url=object_store_inner.signed_download_url(graph_key),
                format="json",
            )
            _prediction.provenance.artifacts = existing
            save_prediction(_prediction)

    task_id = submit_task("learned_model", _run)
    return LearnedModelRunResponse(
        prediction_id=prediction_id,
        task_id=task_id,
        status="queued",
        model_backend=model_backend,
        backend_available=backend_available,
        notes=[],
    )


def get_learned_model_result(prediction_id: UUID) -> LearnedModelInferenceResult:
    """Return the learned-model inference result for a completed prediction.

    Phase 6A: retrieve learned-model provenance stored by ``run_learned_model``.
    """
    prediction = get_prediction(prediction_id)
    if prediction.provenance is None or prediction.provenance.learned_model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No learned-model result found for this prediction. "
                "Submit a learned-model run first via POST .../learned-model:run"
            ),
        )
    lm = prediction.provenance.learned_model
    return LearnedModelInferenceResult(
        prediction_id=prediction_id,
        model_id=lm.model_id,
        model_backend=lm.model_backend,
        backend_available=lm.backend_available,
        predictions={},
        provenance=lm,
        notes=list(lm.notes),
    )


# ---------------------------------------------------------------------------
# Phase 6B: Structure generation ingestion
# ---------------------------------------------------------------------------


def ingest_structure_generation(
    prediction_id: UUID,
    payload: StructureGenerationIngestionRequest,
) -> StructureGenerationIngestionResponse:
    """Import an externally generated or refined structure into a prediction.

    Stores structured provenance metadata and an artifact reference for the
    external structure so downstream analysis can trace back to the generation
    tool.  Compatible with AlphaFold 3, Boltz-1, Rosetta, and generic external
    sources.

    Phase 6B: upstream structure-generation ingestion contract.
    """
    from abby_api.services.structure_generation import ingest_structure_generation_artifact

    prediction = get_prediction(prediction_id)
    if prediction.provenance is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Prediction provenance is required before ingesting a "
                "structure-generation artifact."
            ),
        )

    project_id = _project_id_from_prediction(prediction)
    object_store = ObjectStore()

    ingestion_result = ingest_structure_generation_artifact(
        source=payload.source,
        tool_version=payload.tool_version,
        model_id=payload.model_id,
        seeds=payload.seeds,
        force_field=payload.force_field,
        ddg_protocol=payload.ddg_protocol,
        plddt_mean=payload.plddt_mean,
        structure_url=payload.structure_url,
        structure_format=payload.structure_format,
        ddg_kcal_mol=payload.ddg_kcal_mol,
        clash_score=payload.clash_score,
        total_score=payload.total_score,
        notes_extra=payload.notes,
        prediction_id=str(prediction_id),
        project_id=str(project_id),
        object_store=object_store,
    )

    # Persist structure-generation provenance back to the prediction.
    prediction.provenance.structure_generation = ingestion_result.provenance
    existing = prediction.provenance.artifacts or ArtifactRegistry()
    if ingestion_result.artifact_key:
        existing.structure_generation = ArtifactReference(
            artifact_type="structure_generation_provenance",
            artifact_key=ingestion_result.artifact_key,
            artifact_url=ingestion_result.artifact_url,
            format="json",
        )
    prediction.provenance.artifacts = existing
    save_prediction(prediction)

    artifact_ref = (
        ArtifactReference(
            artifact_type="structure_generation_provenance",
            artifact_key=ingestion_result.artifact_key,
            artifact_url=ingestion_result.artifact_url,
            format="json",
        )
        if ingestion_result.artifact_key
        else None
    )
    return StructureGenerationIngestionResponse(
        prediction_id=prediction_id,
        status="ingested",
        source=ingestion_result.source,
        provenance=ingestion_result.provenance,
        structure_generation_artifact=artifact_ref,
    )

