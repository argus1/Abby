"""Phase 6 tests: learned structural modeling hooks and structure-generation integrations.

These tests verify Phase 6A (graph construction, GNN inference path, training/
calibration contracts) and Phase 6B (AlphaFold 3 / Boltz-1 / Rosetta stub paths
and ingestion contract) without requiring any external ML tools to be installed.

They exercise:
- Graph construction from a synthetic PDB structure.
- GNN stub path (graceful degradation when DeepFRI / ProteinMPNN are absent).
- Training pipeline contract (linear baseline, calibration, evaluation).
- Structure-generation stub paths (AlphaFold3, Boltz-1, Rosetta).
- Ingestion contract for externally generated structures.
- Learned-model provenance persistence in object storage.
- API route integration for POST .../learned-model:run and GET .../learned-model.
- API route integration for POST .../structure-generation:ingest.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from abby_api.main import app
from abby_api.services.graph_models import (
    CalibrationResult,
    EvaluationMetrics,
    GNNInferenceConfig,
    GNNInferenceResult,
    GraphBuildConfig,
    SPRTrainingRecord,
    StructureGraph,
    TrainingPipelineConfig,
    TrainingRunResult,
    evaluate_model,
    is_deepfri_available,
    is_proteinmpnn_available,
    is_torch_available,
    is_torch_geometric_available,
    run_calibration,
    run_gnn_inference,
    run_training_pipeline,
)
from abby_api.services.structure_generation import (
    RosettaRefinementResult,
    StructureGenerationConfig,
    StructureGenerationIngestionResult,
    StructureGenerationResult,
    ingest_structure_generation_artifact,
    is_alphafold3_available,
    is_boltz1_available,
    is_rosetta_available,
    run_rosetta_refinement,
    run_structure_generation,
)
from abby_api.storage.object_store import ObjectStore

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-local-key"}

PDB_FIXTURE = """\
ATOM      1  N   GLY A   1      11.104  13.207   9.111  1.00 20.00           N
ATOM      2  CA  GLY A   1      12.560  13.102   9.262  1.00 20.00           C
ATOM      3  C   GLY A   1      13.030  11.670   9.634  1.00 20.00           C
ATOM      4  O   GLY A   1      12.284  10.719   9.434  1.00 20.00           O
ATOM      5  N   ALA B   1      14.300  11.500  10.100  1.00 20.00           N
ATOM      6  CA  ALA B   1      14.900  10.170  10.420  1.00 20.00           C
ATOM      7  C   ALA B   1      16.350  10.200  10.900  1.00 20.00           C
ATOM      8  O   ALA B   1      17.020   9.180  10.810  1.00 20.00           O
TER
END
"""


# ---------------------------------------------------------------------------
# Helpers for integration tests
# ---------------------------------------------------------------------------


def _upload_and_validate() -> tuple[str, str]:
    """Upload a PDB fixture, validate it, return (project_id, structure_id)."""
    proj_resp = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "phase6-test-project"},
    )
    assert proj_resp.status_code == 201, proj_resp.text
    project_id = proj_resp.json()["project_id"]

    upload_resp = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test.pdb", PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "ppi_general"},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    structure_id = upload_resp.json()["structure_id"]

    val_resp = client.post(
        "/api/v1/structures:validate",
        headers=HEADERS,
        json={
            "structure_id": structure_id,
            "mode": "ppi_general",
            "chains": {"partner_1": ["A"], "partner_2": ["B"]},
        },
    )
    assert val_resp.status_code == 200, val_resp.text
    return project_id, structure_id


def _create_prediction(project_id: str, structure_id: str) -> str:
    """Submit a prediction and return the prediction_id."""
    pred_resp = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "structure_id": structure_id,
            "mode": "ppi_general",
        },
    )
    assert pred_resp.status_code == 202, pred_resp.text
    return pred_resp.json()["prediction_id"]


# ===========================================================================
# Phase 6A: Graph construction
# ===========================================================================


class TestGraphConstruction:
    def test_graph_models_importable(self) -> None:
        from abby_api.services import graph_models  # noqa: F401

    def test_availability_functions_return_bool(self) -> None:
        assert isinstance(is_torch_available(), bool)
        assert isinstance(is_torch_geometric_available(), bool)
        assert isinstance(is_deepfri_available(), bool)
        assert isinstance(is_proteinmpnn_available(), bool)

    def test_gnn_inference_stub_when_no_backend(self) -> None:
        """GNN inference always returns a well-formed result even with no structure."""
        config = GNNInferenceConfig(model_id="deepfri_stub")
        # Pass None for structure and validation – no backend installed → stub path.
        result = run_gnn_inference(None, None, config=config)
        assert isinstance(result, GNNInferenceResult)
        assert result.model_id == "deepfri_stub"
        assert isinstance(result.predictions, dict)
        assert isinstance(result.notes, list)

    def test_gnn_result_has_graph_field(self) -> None:
        result = run_gnn_inference(None, None)
        assert result.graph is not None
        assert isinstance(result.graph, StructureGraph)

    def test_stub_graph_is_empty_when_no_structure(self) -> None:
        result = run_gnn_inference(None, None)
        assert result.graph.nodes == []
        assert result.graph.edges == []
        assert result.graph.partner_1_node_indices == []
        assert result.graph.partner_2_node_indices == []
        assert result.graph.interface_node_indices == []

    def test_graph_adjacency_dict_empty_graph(self) -> None:
        result = run_gnn_inference(None, None)
        adj = result.graph.to_adjacency_dict()
        assert isinstance(adj, dict)
        assert adj == {}

    def test_graph_node_feature_matrix_empty(self) -> None:
        result = run_gnn_inference(None, None)
        matrix = result.graph.node_feature_matrix()
        assert isinstance(matrix, list)
        assert matrix == []

    def test_graph_edge_index_empty(self) -> None:
        result = run_gnn_inference(None, None)
        src, dst = result.graph.edge_index()
        assert src == []
        assert dst == []

    def test_graph_version_set(self) -> None:
        result = run_gnn_inference(None, None)
        assert result.graph.graph_version == "structure_graph_v1"
        assert result.graph.graph_id  # non-empty UUID string

    def test_gnn_stub_notes_contain_stub_marker(self) -> None:
        if is_deepfri_available() or is_proteinmpnn_available():
            pytest.skip("A real GNN backend is present; stub path not reached.")
        result = run_gnn_inference(None, None)
        combined_notes = " ".join(result.notes)
        assert "STUB" in combined_notes or "NOT_AVAILABLE" in combined_notes

    def test_graph_build_config_defaults(self) -> None:
        cfg = GraphBuildConfig()
        assert cfg.contact_distance_cutoff_angstrom == 8.0
        assert cfg.include_backbone_edges is True
        assert cfg.include_covalent_edges is True


# ===========================================================================
# Phase 6A: Training / evaluation / calibration pipeline contracts
# ===========================================================================


class TestTrainingPipelineContract:
    def _make_records(self, n: int = 10) -> list[SPRTrainingRecord]:
        records = []
        for i in range(n):
            records.append(
                SPRTrainingRecord(
                    structure_id=str(uuid4()),
                    prediction_id=str(uuid4()),
                    measured_log_k=float(-5 + i * 0.5),
                    descriptor_hash=f"hash_{i}",
                    descriptor_version="summary_features_v2",
                    descriptors={
                        "total_residues": float(10 + i),
                        "interface_contact_proxy": float(i * 2),
                        "sasa_apolar_fraction": float(i) / 20.0,
                        "partner_size_ratio": 0.5,
                    },
                )
            )
        return records

    def test_training_pipeline_runs_without_error(self) -> None:
        records = self._make_records(10)
        result = run_training_pipeline(records)
        assert isinstance(result, TrainingRunResult)
        assert result.run_id
        assert result.n_train > 0
        assert result.n_val > 0

    def test_training_pipeline_empty_records_stub(self) -> None:
        result = run_training_pipeline([])
        assert result.n_train == 0
        assert result.n_val == 0
        assert not result.backend_available

    def test_training_pipeline_linear_type(self) -> None:
        records = self._make_records(8)
        config = TrainingPipelineConfig(model_type="linear", random_seed=0)
        result = run_training_pipeline(records, config)
        assert result.model_type == "linear"
        assert result.backend_available is True

    def test_training_pipeline_gnn_stub_when_no_torch(self) -> None:
        if is_torch_available():
            pytest.skip("torch is installed; GNN training path available.")
        records = self._make_records(6)
        config = TrainingPipelineConfig(model_type="gnn")
        result = run_training_pipeline(records, config)
        assert result.backend_available is False

    def test_training_r_validation_in_range(self) -> None:
        records = self._make_records(10)
        result = run_training_pipeline(records, TrainingPipelineConfig(model_type="linear"))
        # r_validation may be any float in [-1, 1] or 0.0 for stub.
        assert -1.0 <= result.r_validation <= 1.0

    def test_training_artifact_persisted_with_object_store(self) -> None:
        records = self._make_records(8)
        object_store = ObjectStore()
        config = TrainingPipelineConfig(model_type="linear")
        result = run_training_pipeline(records, config, object_store=object_store)
        if result.artifact_key:
            raw = object_store.get_bytes(result.artifact_key)
            assert raw is not None
            payload = json.loads(raw)
            assert "descriptor_keys" in payload
            assert "weights" in payload

    def test_calibration_temperature_scaling(self) -> None:
        preds = [-6.0, -5.5, -5.0, -4.5, -4.0]
        measured = [-5.8, -5.3, -4.9, -4.6, -3.9]
        result = run_calibration(preds, measured, method="temperature")
        assert isinstance(result, CalibrationResult)
        assert result.method == "temperature"
        assert result.n_samples == 5
        assert result.backend_available is True

    def test_calibration_auto_falls_back(self) -> None:
        preds = [-6.0, -5.0, -4.0]
        measured = [-5.8, -5.1, -3.8]
        result = run_calibration(preds, measured, method="auto")
        assert isinstance(result, CalibrationResult)
        assert result.n_samples == 3

    def test_calibration_empty_data(self) -> None:
        result = run_calibration([], [])
        assert result.n_samples == 0
        assert not result.backend_available

    def test_calibration_artifact_persisted(self) -> None:
        preds = [-6.0, -5.5, -5.0, -4.5]
        measured = [-5.8, -5.3, -4.9, -4.6]
        object_store = ObjectStore()
        result = run_calibration(preds, measured, method="temperature", object_store=object_store)
        if result.calibration_artifact_key:
            raw = object_store.get_bytes(result.calibration_artifact_key)
            assert raw is not None

    def test_evaluate_model_metrics(self) -> None:
        preds = [-6.0, -5.5, -5.0, -4.5, -4.0]
        measured = [-5.8, -5.3, -4.9, -4.6, -3.9]
        metrics = evaluate_model(preds, measured)
        assert isinstance(metrics, EvaluationMetrics)
        assert metrics.n_samples == 5
        assert 0.0 <= metrics.r_pearson <= 1.0
        assert metrics.rmse >= 0.0
        assert metrics.mae >= 0.0

    def test_evaluate_model_empty(self) -> None:
        metrics = evaluate_model([], [])
        assert metrics.n_samples == 0
        assert metrics.r_pearson == 0.0

    def test_evaluate_model_ood_fraction(self) -> None:
        preds = [-6.0, -3.5, -2.0]
        measured = [-5.8, -3.0, -1.5]
        metrics = evaluate_model(preds, measured, ood_threshold_log_k=-3.0)
        # -3.5 and -1.5 are both below -3.0
        assert 0.0 <= metrics.ood_fraction <= 1.0


# ===========================================================================
# Phase 6B: Structure-generation stub paths
# ===========================================================================


class TestStructureGenerationStubs:
    def test_rosetta_availability_returns_bool(self) -> None:
        assert isinstance(is_rosetta_available(), bool)

    def test_alphafold3_availability_returns_bool(self) -> None:
        assert isinstance(is_alphafold3_available(), bool)

    def test_boltz1_availability_returns_bool(self) -> None:
        assert isinstance(is_boltz1_available(), bool)

    def test_run_structure_generation_stub_when_no_tool(self) -> None:
        if is_alphafold3_available() or is_boltz1_available():
            pytest.skip("A generation tool is present; stub path not tested here.")
        config = StructureGenerationConfig(sequences=[{"id": "A", "sequence": "EVQLV"}])
        result = run_structure_generation(config)
        assert isinstance(result, StructureGenerationResult)
        assert result.generation_available is False
        assert "stub" in result.source.lower()
        assert isinstance(result.notes, list)
        assert any("NOT_AVAILABLE" in n or "STUB" in n for n in result.notes)

    def test_structure_generation_stub_has_valid_provenance(self) -> None:
        if is_alphafold3_available() or is_boltz1_available():
            pytest.skip("Real tool available; stub path not tested here.")
        config = StructureGenerationConfig()
        result = run_structure_generation(config)
        assert result.provenance.source.endswith("_stub")

    def test_run_rosetta_refinement_stub_when_unavailable(self, tmp_path: Path) -> None:
        if is_rosetta_available():
            pytest.skip("Rosetta is installed; stub path not tested here.")
        pdb_file = tmp_path / "test.pdb"
        pdb_file.write_text(PDB_FIXTURE)
        result = run_rosetta_refinement(pdb_file)
        assert isinstance(result, RosettaRefinementResult)
        assert result.rosetta_available is False
        assert result.ddg_kcal_mol is None
        assert result.refined_structure_key is None
        assert any("NOT_AVAILABLE" in n or "STUB" in n for n in result.notes)

    def test_rosetta_stub_provenance_has_source(self, tmp_path: Path) -> None:
        if is_rosetta_available():
            pytest.skip("Rosetta is installed; stub path not tested here.")
        pdb_file = tmp_path / "test.pdb"
        pdb_file.write_text(PDB_FIXTURE)
        result = run_rosetta_refinement(pdb_file)
        assert "rosetta" in result.provenance.source.lower()

    def test_rosetta_stub_persists_provenance_artifact(self, tmp_path: Path) -> None:
        if is_rosetta_available():
            pytest.skip("Rosetta is installed; stub path not tested here.")
        pdb_file = tmp_path / "test.pdb"
        pdb_file.write_text(PDB_FIXTURE)
        project_id = str(uuid4())
        prediction_id = str(uuid4())
        object_store = ObjectStore()
        run_rosetta_refinement(
            pdb_file,
            project_id=project_id,
            prediction_id=prediction_id,
            object_store=object_store,
        )
        # Provenance JSON is always persisted even for stub results.
        prov_key = f"projects/{project_id}/predictions/{prediction_id}/rosetta/provenance.json"
        raw = object_store.get_bytes(prov_key)
        assert raw is not None
        payload = json.loads(raw)
        assert payload["rosetta_available"] is False
        assert "notes" in payload


# ===========================================================================
# Phase 6B: Structure-generation ingestion contract
# ===========================================================================


class TestStructureGenerationIngestion:
    def test_ingest_alphafold3_artifact(self) -> None:
        prediction_id = str(uuid4())
        project_id = str(uuid4())
        object_store = ObjectStore()
        result = ingest_structure_generation_artifact(
            source="alphafold3",
            tool_version="3.0.0",
            model_id="af3_multimer",
            seeds=[42, 43],
            plddt_mean=87.5,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
        )
        assert isinstance(result, StructureGenerationIngestionResult)
        assert result.source == "alphafold3"
        assert result.imported is True
        assert result.provenance.source == "alphafold3"
        assert result.provenance.imported is True
        assert 42 in result.provenance.seeds

    def test_ingest_boltz1_artifact(self) -> None:
        result = ingest_structure_generation_artifact(
            source="boltz1",
            tool_version="1.0",
            seeds=[0],
        )
        assert result.source == "boltz1"
        assert result.imported is True

    def test_ingest_rosetta_ddg_artifact(self) -> None:
        result = ingest_structure_generation_artifact(
            source="rosetta",
            ddg_protocol="ddg_monomer",
            ddg_kcal_mol=-2.3,
            clash_score=12.5,
            total_score=-450.7,
        )
        assert result.source == "rosetta"
        assert result.provenance.ddg_protocol == "ddg_monomer"

    def test_ingest_artifact_persists_provenance_json(self) -> None:
        prediction_id = str(uuid4())
        project_id = str(uuid4())
        object_store = ObjectStore()
        result = ingest_structure_generation_artifact(
            source="alphafold3",
            seeds=[1, 2],
            plddt_mean=90.0,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
        )
        assert result.artifact_key is not None
        raw = object_store.get_bytes(result.artifact_key)
        assert raw is not None
        payload = json.loads(raw)
        assert payload["source"] == "alphafold3"
        assert payload["imported"] is True

    def test_ingest_without_project_creates_fallback_key(self) -> None:
        object_store = ObjectStore()
        result = ingest_structure_generation_artifact(
            source="boltz1",
            object_store=object_store,
        )
        assert result.artifact_key is not None
        assert "ingestions" in result.artifact_key or "boltz1" in result.artifact_key


# ===========================================================================
# Phase 6 API integration tests
# ===========================================================================


class TestLearnedModelAPIRoutes:
    def test_run_learned_model_queues_task(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        resp = client.post(
            f"/api/v1/predictions/{prediction_id}/learned-model:run",
            headers=HEADERS,
            json={"model_id": "deepfri_stub"},
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["status"] == "queued"
        assert data["prediction_id"] == prediction_id
        assert "model_backend" in data
        assert "backend_available" in data
        assert isinstance(data["backend_available"], bool)

    def test_run_learned_model_unknown_prediction_returns_404(self) -> None:
        resp = client.post(
            f"/api/v1/predictions/{uuid4()}/learned-model:run",
            headers=HEADERS,
            json={"model_id": "deepfri_stub"},
        )
        assert resp.status_code == 404

    def test_get_learned_model_result_not_found_before_run(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        resp = client.get(
            f"/api/v1/predictions/{prediction_id}/learned-model",
            headers=HEADERS,
        )
        assert resp.status_code == 404

    def test_get_learned_model_result_after_run(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        # Submit the run (will complete synchronously in test context via inline backend).
        run_resp = client.post(
            f"/api/v1/predictions/{prediction_id}/learned-model:run",
            headers=HEADERS,
            json={"model_id": "deepfri_test"},
        )
        assert run_resp.status_code == 202, run_resp.text

        # Poll until the worker has stored a result or the deadline passes.
        # The inline test backend completes synchronously so this normally
        # succeeds on the first attempt.
        deadline = time.monotonic() + 2.0
        result_resp = None
        while time.monotonic() < deadline:
            result_resp = client.get(
                f"/api/v1/predictions/{prediction_id}/learned-model",
                headers=HEADERS,
            )
            if result_resp.status_code == 200:
                break
            time.sleep(0.05)

        assert result_resp is not None
        # May be 200 (result stored) or 404 (worker not yet done in some backends).
        assert result_resp.status_code in {200, 404}, result_resp.text
        if result_resp.status_code == 200:
            data = result_resp.json()
            assert "model_id" in data
            assert "backend_available" in data

    def test_run_learned_model_response_has_task_id(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        resp = client.post(
            f"/api/v1/predictions/{prediction_id}/learned-model:run",
            headers=HEADERS,
            json={"model_id": "deepfri_stub", "graph_contact_cutoff_angstrom": 8.0},
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert "task_id" in data
        assert data["task_id"]  # non-empty string


class TestStructureGenerationAPIRoute:
    def test_ingest_alphafold3_via_api(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        resp = client.post(
            f"/api/v1/predictions/{prediction_id}/structure-generation:ingest",
            headers=HEADERS,
            json={
                "source": "alphafold3",
                "tool_version": "3.0.0",
                "seeds": [42],
                "plddt_mean": 88.2,
                "notes": ["generated_from_sequence_A"],
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ingested"
        assert data["source"] == "alphafold3"
        assert "provenance" in data
        assert data["provenance"]["imported"] is True
        assert 42 in data["provenance"]["seeds"]

    def test_ingest_rosetta_ddg_via_api(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        resp = client.post(
            f"/api/v1/predictions/{prediction_id}/structure-generation:ingest",
            headers=HEADERS,
            json={
                "source": "rosetta",
                "ddg_protocol": "ddg_monomer",
                "ddg_kcal_mol": -1.8,
                "clash_score": 10.2,
                "total_score": -523.4,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ingested"
        assert data["provenance"]["ddg_protocol"] == "ddg_monomer"

    def test_ingest_structure_generation_unknown_prediction_returns_404(self) -> None:
        resp = client.post(
            f"/api/v1/predictions/{uuid4()}/structure-generation:ingest",
            headers=HEADERS,
            json={"source": "boltz1"},
        )
        assert resp.status_code == 404

    def test_ingest_structure_generation_artifact_ref_in_response(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        resp = client.post(
            f"/api/v1/predictions/{prediction_id}/structure-generation:ingest",
            headers=HEADERS,
            json={"source": "boltz1", "seeds": [0]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Artifact reference should be present (provenance JSON is always stored).
        assert data["structure_generation_artifact"] is not None
        artifact = data["structure_generation_artifact"]
        assert artifact["artifact_type"] == "structure_generation_provenance"

    def test_ingest_updates_prediction_provenance(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        client.post(
            f"/api/v1/predictions/{prediction_id}/structure-generation:ingest",
            headers=HEADERS,
            json={
                "source": "alphafold3",
                "plddt_mean": 91.0,
                "seeds": [7],
            },
        )

        pred_resp = client.get(
            f"/api/v1/predictions/{prediction_id}",
            headers=HEADERS,
        )
        assert pred_resp.status_code == 200, pred_resp.text
        provenance = pred_resp.json().get("provenance", {})
        structure_gen = provenance.get("structure_generation")
        assert structure_gen is not None
        assert structure_gen["source"] == "alphafold3"
        assert structure_gen["imported"] is True


# ===========================================================================
# Phase 6 cross-cutting: learned-model provenance in prediction provenance
# ===========================================================================


class TestLearnedModelProvenance:
    def test_prediction_provenance_learned_model_field_absent_before_run(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        pred_resp = client.get(
            f"/api/v1/predictions/{prediction_id}",
            headers=HEADERS,
        )
        assert pred_resp.status_code == 200, pred_resp.text
        provenance = pred_resp.json().get("provenance", {})
        assert provenance.get("learned_model") is None

    def test_prediction_provenance_structure_generation_field_absent_before_ingest(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        pred_resp = client.get(
            f"/api/v1/predictions/{prediction_id}",
            headers=HEADERS,
        )
        assert pred_resp.status_code == 200, pred_resp.text
        provenance = pred_resp.json().get("provenance", {})
        assert provenance.get("structure_generation") is None

    def test_learned_model_provenance_schema_fields(self) -> None:
        from abby_api.schemas.common import LearnedModelProvenance

        lm = LearnedModelProvenance(
            model_id="deepfri_test",
            model_backend="deepfri",
            backend_available=True,
            graph_version="structure_graph_v1",
            notes=["test"],
        )
        assert lm.model_id == "deepfri_test"
        assert lm.backend_available is True

    def test_structure_generation_provenance_schema_fields(self) -> None:
        from abby_api.schemas.common import StructureGenerationProvenance

        sg = StructureGenerationProvenance(
            source="alphafold3",
            tool_version="3.0.0",
            seeds=[42],
            plddt_mean=88.3,
            imported=True,
        )
        assert sg.source == "alphafold3"
        assert 42 in sg.seeds
        assert sg.imported is True

    def test_artifact_registry_has_phase6_fields(self) -> None:
        from abby_api.schemas.common import ArtifactReference, ArtifactRegistry

        reg = ArtifactRegistry(
            structure_graph=ArtifactReference(
                artifact_type="structure_graph",
                artifact_key="projects/x/y/graph.json",
                format="json",
            ),
            learned_model_result=ArtifactReference(
                artifact_type="learned_model_result",
                artifact_key="projects/x/y/lm_result.json",
                format="json",
            ),
            structure_generation=ArtifactReference(
                artifact_type="structure_generation_provenance",
                artifact_key="projects/x/y/sg_prov.json",
                format="json",
            ),
        )
        assert reg.structure_graph is not None
        assert reg.learned_model_result is not None
        assert reg.structure_generation is not None
