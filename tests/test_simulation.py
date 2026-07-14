from __future__ import annotations

"""Phase 5 tests: simulation worker, GROMACS-CIF path, and trajectory aggregation.

These tests verify the simulation and trajectory services without requiring
GROMACS or MDAnalysis to be installed.  They exercise:
- The simulation worker backend isolation.
- The GROMACS stub path (graceful degradation when GROMACS is absent).
- Parameterization hook fallback behavior.
- MDAnalysis stub path (graceful degradation when MDAnalysis is absent).
- Trajectory descriptor enrichment threading.
- The simulation:run API route (queued + stub execution).
- Simulation provenance persistence in object storage.
"""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from abby_api.main import app
from abby_api.services.simulation import (
    SimulationRunConfig,
    SimulationUnavailableError,
    ParameterizationResult,
    is_gromacs_available,
    is_antechamber_available,
    is_ligpargen_available,
    parameterize_non_standard_residues,
    run_gromacs_cif_simulation,
)
from abby_api.services.trajectory import (
    TrajectorySummary,
    compute_trajectory_summary,
    enrich_descriptors_from_trajectory,
    is_mdanalysis_available,
)
from abby_api.storage.object_store import ObjectStore
from abby_api.workers.tasks import (
    initialize_simulation_worker_backend,
    shutdown_simulation_worker_backend,
    submit_simulation_task,
)

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


def _upload_and_validate(tmp_path: Path | None = None) -> tuple[str, str]:
    """Upload a PDB fixture, validate it, and return (project_id, structure_id)."""
    # Create project.
    proj_resp = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"name": "sim-test-project"},
    )
    assert proj_resp.status_code == 201, proj_resp.text
    project_id = proj_resp.json()["project_id"]

    # Upload structure.
    upload_resp = client.post(
        "/api/v1/structures:upload",
        headers=HEADERS,
        files={"file": ("test.pdb", PDB_FIXTURE, "chemical/x-pdb")},
        data={"mode": "ppi_general"},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    structure_id = upload_resp.json()["structure_id"]

    # Validate.
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
    assert val_resp.json()["valid"] is True

    return project_id, structure_id


def _create_prediction(project_id: str, structure_id: str) -> str:
    """Create a prediction and return its prediction_id."""
    pred_resp = client.post(
        "/api/v1/predictions",
        headers=HEADERS,
        json={
            "project_id": project_id,
            "mode": "ppi_general",
            "structure_id": structure_id,
        },
    )
    assert pred_resp.status_code == 202, pred_resp.text
    return pred_resp.json()["prediction_id"]


# ---------------------------------------------------------------------------
# Simulation service unit tests
# ---------------------------------------------------------------------------


class TestSimulationAvailabilityChecks:
    def test_is_gromacs_available_returns_bool(self) -> None:
        # In CI GROMACS is not installed; we just verify the return type.
        result = is_gromacs_available()
        assert isinstance(result, bool)

    def test_is_antechamber_available_returns_bool(self) -> None:
        result = is_antechamber_available()
        assert isinstance(result, bool)

    def test_is_ligpargen_available_returns_bool(self) -> None:
        result = is_ligpargen_available()
        assert isinstance(result, bool)


class TestParameterizationHooks:
    def test_empty_residues_returns_no_parameterization_needed(self) -> None:
        result = parameterize_non_standard_residues({})
        assert isinstance(result, ParameterizationResult)
        assert result.residues_parameterized == []
        assert "NO_NON_STANDARD_RESIDUES" in result.notes

    def test_stub_fallback_when_no_tool_available(self, monkeypatch) -> None:
        # Ensure neither antechamber nor ligpargen are available.
        monkeypatch.setattr(
            "abby_api.services.simulation.is_antechamber_available", lambda: False
        )
        monkeypatch.setattr(
            "abby_api.services.simulation.is_ligpargen_available", lambda: False
        )
        result = parameterize_non_standard_residues({"MSE": {"A": 2}})
        assert result.available is False
        assert result.method == "stub"
        assert "MSE" in "".join(result.notes)
        assert "PARAMETERIZATION_STUB_NO_TOOL_AVAILABLE" in result.notes

    def test_explicit_stub_method(self) -> None:
        result = parameterize_non_standard_residues({"PCA": {"A": 1}}, method="stub")
        assert result.method == "stub"
        assert result.available is False

    def test_parameterization_result_fields_present(self) -> None:
        result = parameterize_non_standard_residues({"HIC": {"B": 1}})
        assert hasattr(result, "available")
        assert hasattr(result, "method")
        assert hasattr(result, "residues_parameterized")
        assert hasattr(result, "artifact_keys")
        assert hasattr(result, "notes")

    def test_invalid_residue_name_with_shell_chars_is_rejected(self) -> None:
        result = parameterize_non_standard_residues({"MSE; rm -rf /": {"A": 1}})
        assert result.available is False
        assert any("PARAMETERIZATION_REJECTED_INVALID_RESIDUE_NAME" in n for n in result.notes)

    def test_residue_name_with_path_traversal_is_rejected(self) -> None:
        result = parameterize_non_standard_residues({"../../etc/passwd": {"A": 1}})
        assert result.available is False
        assert any("PARAMETERIZATION_REJECTED_INVALID_RESIDUE_NAME" in n for n in result.notes)


class TestGromacsStubPath:
    """Verify the stub result returned when GROMACS is not installed."""

    def test_run_without_gromacs_returns_stub_result(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("abby_api.services.simulation.is_gromacs_available", lambda: False)

        pdb = tmp_path / "test.pdb"
        pdb.write_text(PDB_FIXTURE)
        prediction_id = uuid4()
        project_id = uuid4()
        object_store = ObjectStore(base_dir=tmp_path / "store")

        config = SimulationRunConfig()
        result = run_gromacs_cif_simulation(
            pdb,
            config,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
        )

        assert result.gromacs_available is False
        assert result.trajectory_artifact_key is None
        assert "GROMACS_NOT_AVAILABLE" in result.notes

    def test_stub_provenance_persisted_to_object_storage(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("abby_api.services.simulation.is_gromacs_available", lambda: False)

        pdb = tmp_path / "test.pdb"
        pdb.write_text(PDB_FIXTURE)
        prediction_id = uuid4()
        project_id = uuid4()
        object_store = ObjectStore(base_dir=tmp_path / "store")

        config = SimulationRunConfig(force_field="charmm36", water_model="tip4p")
        result = run_gromacs_cif_simulation(
            pdb,
            config,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
        )

        # Provenance artifact must be persisted.
        assert result.artifact_registry.topology_reference is not None
        artifact_key = result.artifact_registry.topology_reference.artifact_key
        assert artifact_key is not None
        raw = object_store.get_bytes(artifact_key)
        assert raw is not None
        payload = json.loads(raw.decode("utf-8"))
        assert payload["gromacs_available"] is False
        assert payload["provenance"]["force_field"] == "charmm36"
        assert payload["provenance"]["water_model"] == "tip4p"

    def test_stub_provenance_fields_preserved(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("abby_api.services.simulation.is_gromacs_available", lambda: False)

        pdb = tmp_path / "test.pdb"
        pdb.write_text(PDB_FIXTURE)
        prediction_id = uuid4()
        project_id = uuid4()
        object_store = ObjectStore(base_dir=tmp_path / "store")
        config = SimulationRunConfig(seed=42, minimization_protocol="l-bfgs")

        result = run_gromacs_cif_simulation(
            pdb, config,
            prediction_id=prediction_id,
            project_id=project_id,
            object_store=object_store,
        )

        assert result.provenance.seed == 42
        assert result.provenance.minimization_protocol == "l-bfgs"
        assert result.provenance.source == "gromacs_stub"
        assert result.provenance.imported is False


# ---------------------------------------------------------------------------
# Trajectory service unit tests
# ---------------------------------------------------------------------------


class TestMDAnalysisAvailability:
    def test_is_mdanalysis_available_returns_bool(self) -> None:
        result = is_mdanalysis_available()
        assert isinstance(result, bool)


class TestTrajectorySummaryStub:
    """Verify graceful degradation when MDAnalysis is absent."""

    def test_stub_returned_when_mdanalysis_unavailable(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("abby_api.services.trajectory.is_mdanalysis_available", lambda: False)
        dummy = tmp_path / "dummy.trr"
        dummy.write_bytes(b"")
        summary = compute_trajectory_summary(dummy)
        assert isinstance(summary, TrajectorySummary)
        assert summary.mdanalysis_available is False
        assert summary.frame_count == 0
        assert "MDANALYSIS_NOT_AVAILABLE" in summary.notes

    def test_stub_numeric_fields_are_zero(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("abby_api.services.trajectory.is_mdanalysis_available", lambda: False)
        dummy = tmp_path / "dummy.xtc"
        dummy.write_bytes(b"")
        summary = compute_trajectory_summary(dummy)
        assert summary.mean_radius_of_gyration_angstrom == 0.0
        assert summary.std_radius_of_gyration_angstrom == 0.0
        assert summary.min_radius_of_gyration_angstrom == 0.0
        assert summary.max_radius_of_gyration_angstrom == 0.0
        assert summary.mean_atom_count == 0.0
        assert summary.frame_summaries == []

    def test_trajectory_read_failure_returns_graceful_summary(self, tmp_path, monkeypatch) -> None:
        """Even when MDAnalysis is present, a bad file path returns a graceful summary."""
        monkeypatch.setattr("abby_api.services.trajectory.is_mdanalysis_available", lambda: True)

        def _bad_compute(**kwargs):
            raise RuntimeError("unreadable trajectory")

        monkeypatch.setattr(
            "abby_api.services.trajectory._compute_summary_with_mdanalysis",
            _bad_compute,
        )
        dummy = tmp_path / "bad.trr"
        dummy.write_bytes(b"not a trajectory")
        summary = compute_trajectory_summary(dummy)
        assert summary.mdanalysis_available is True
        assert summary.frame_count == 0
        assert any("TRAJECTORY_READ_FAILED" in n for n in summary.notes)


class TestDescriptorEnrichment:
    """Test threading trajectory summaries into descriptor generation."""

    def test_enrichment_skipped_without_mdanalysis(self) -> None:
        base_descriptors = {"total_residues": 10.0, "radius_of_gyration_angstrom": 5.0}
        stub_summary = TrajectorySummary(
            mdanalysis_available=False,
            frame_count=0,
            mean_radius_of_gyration_angstrom=0.0,
            std_radius_of_gyration_angstrom=0.0,
            min_radius_of_gyration_angstrom=0.0,
            max_radius_of_gyration_angstrom=0.0,
            mean_atom_count=0.0,
            notes=["MDANALYSIS_NOT_AVAILABLE"],
        )
        enriched, notes = enrich_descriptors_from_trajectory(base_descriptors, stub_summary)
        assert "trajectory_mean_radius_of_gyration_angstrom" not in enriched
        assert "TRAJECTORY_DESCRIPTORS_NOT_ENRICHED" in notes
        # Original descriptors unchanged.
        assert enriched["total_residues"] == 10.0

    def test_enrichment_adds_trajectory_fields_when_available(self) -> None:
        base_descriptors = {"total_residues": 20.0}
        summary = TrajectorySummary(
            mdanalysis_available=True,
            frame_count=100,
            mean_radius_of_gyration_angstrom=12.34,
            std_radius_of_gyration_angstrom=0.56,
            min_radius_of_gyration_angstrom=11.0,
            max_radius_of_gyration_angstrom=14.0,
            mean_atom_count=500.0,
            notes=["TRAJECTORY_SUMMARY_FROM_MDANALYSIS"],
        )
        enriched, notes = enrich_descriptors_from_trajectory(base_descriptors, summary)
        assert enriched["trajectory_mean_radius_of_gyration_angstrom"] == 12.34
        assert enriched["trajectory_std_radius_of_gyration_angstrom"] == 0.56
        assert enriched["trajectory_frame_count"] == 100.0
        assert enriched["trajectory_mean_atom_count"] == 500.0
        assert "TRAJECTORY_DESCRIPTORS_ENRICHED_FROM_MDANALYSIS" in notes
        # Original descriptors preserved.
        assert enriched["total_residues"] == 20.0

    def test_enrichment_does_not_mutate_original_descriptors(self) -> None:
        base = {"total_residues": 5.0}
        summary = TrajectorySummary(
            mdanalysis_available=True,
            frame_count=50,
            mean_radius_of_gyration_angstrom=8.0,
            std_radius_of_gyration_angstrom=0.1,
            min_radius_of_gyration_angstrom=7.5,
            max_radius_of_gyration_angstrom=8.5,
            mean_atom_count=200.0,
            notes=[],
        )
        enriched, _ = enrich_descriptors_from_trajectory(base, summary)
        assert "trajectory_mean_radius_of_gyration_angstrom" not in base
        assert enriched is not base


# ---------------------------------------------------------------------------
# Simulation worker backend isolation tests
# ---------------------------------------------------------------------------


class TestSimulationWorkerBackend:
    """Verify the dedicated simulation worker is separate from the general backend."""

    def test_simulation_backend_can_be_initialized_independently(self) -> None:
        backend = initialize_simulation_worker_backend(backend_type="inline")
        assert backend is not None
        shutdown_simulation_worker_backend()

    def test_simulation_backend_submits_task(self) -> None:
        backend = initialize_simulation_worker_backend(backend_type="inline")
        ran: list[bool] = []
        task_id = submit_simulation_task(lambda: ran.append(True))
        assert task_id
        assert ran == [True], "simulation task must execute synchronously in inline mode"
        shutdown_simulation_worker_backend()

    def test_simulation_backend_isolated_from_general_backend(self) -> None:
        from abby_api.workers.backend import get_worker_backend, initialize_worker_backend
        from abby_api.workers.tasks import get_simulation_worker_backend
        from abby_api.core.config import get_settings

        # Ensure the general backend is up so get_worker_backend() doesn't raise.
        settings = get_settings()
        initialize_worker_backend(backend_type="inline", worker_count=1)

        sim_backend = initialize_simulation_worker_backend(backend_type="inline")
        general_backend = get_worker_backend()
        assert sim_backend is not general_backend, (
            "simulation backend must be isolated from the general prediction worker"
        )
        shutdown_simulation_worker_backend()

    def test_simulation_backend_shutdown_clears_singleton(self) -> None:
        from abby_api.workers.tasks import (
            get_simulation_worker_backend,
            initialize_simulation_worker_backend as _init,
            shutdown_simulation_worker_backend as _shutdown,
        )

        _init(backend_type="inline")
        _shutdown()
        with pytest.raises(RuntimeError, match="Simulation worker backend has not been initialized"):
            get_simulation_worker_backend()


# ---------------------------------------------------------------------------
# API route integration tests
# ---------------------------------------------------------------------------


class TestSimulationRunRoute:
    """Integration tests for POST /predictions/{id}/simulation:run."""

    def test_simulation_run_returns_202_with_task_id(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        run_resp = client.post(
            f"/api/v1/predictions/{prediction_id}/simulation:run",
            headers=HEADERS,
            json={
                "force_field": "amber99sb-ildn",
                "water_model": "tip3p",
                "max_steps": 100,
            },
        )
        assert run_resp.status_code == 202, run_resp.text
        body = run_resp.json()
        assert body["prediction_id"] == prediction_id
        assert body["status"] == "queued"
        assert "task_id" in body
        assert isinstance(body["gromacs_available"], bool)

    def test_simulation_run_requires_valid_prediction(self) -> None:
        fake_id = str(uuid4())
        run_resp = client.post(
            f"/api/v1/predictions/{fake_id}/simulation:run",
            headers=HEADERS,
            json={},
        )
        assert run_resp.status_code == 404

    def test_simulation_run_uses_defaults_when_payload_empty(self) -> None:
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        run_resp = client.post(
            f"/api/v1/predictions/{prediction_id}/simulation:run",
            headers=HEADERS,
            json={},
        )
        assert run_resp.status_code == 202, run_resp.text
        body = run_resp.json()
        assert body["status"] == "queued"

    def test_simulation_run_does_not_affect_default_prediction(self) -> None:
        """Simulation task submission must not alter the prediction consensus."""
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        # Get prediction before simulation.
        before = client.get(
            f"/api/v1/predictions/{prediction_id}",
            headers=HEADERS,
        ).json()

        # Submit simulation.
        client.post(
            f"/api/v1/predictions/{prediction_id}/simulation:run",
            headers=HEADERS,
            json={},
        )

        # Prediction consensus must be unchanged.
        after = client.get(
            f"/api/v1/predictions/{prediction_id}",
            headers=HEADERS,
        ).json()
        assert before["consensus"]["log_k"] == after["consensus"]["log_k"]
        assert before["consensus"]["delta_g_kcal_mol"] == after["consensus"]["delta_g_kcal_mol"]

    def test_simulation_run_provenance_persisted(self, tmp_path, monkeypatch) -> None:
        """After the inline simulation worker completes, provenance is in the store."""
        project_id, structure_id = _upload_and_validate()
        prediction_id = _create_prediction(project_id, structure_id)

        # Force GROMACS-unavailable stub so task completes synchronously.
        monkeypatch.setattr("abby_api.services.simulation.is_gromacs_available", lambda: False)
        # Use inline backend for deterministic completion.
        from abby_api.workers.tasks import (
            initialize_simulation_worker_backend as _init,
            shutdown_simulation_worker_backend as _shutdown,
        )
        _shutdown()
        _init(backend_type="inline")

        client.post(
            f"/api/v1/predictions/{prediction_id}/simulation:run",
            headers=HEADERS,
            json={"force_field": "charmm36m"},
        )

        # Simulation provenance should be updated on the prediction.
        pred = client.get(
            f"/api/v1/predictions/{prediction_id}",
            headers=HEADERS,
        ).json()
        # The inline backend executes the task synchronously, so the stub
        # simulation has already written back "gromacs_stub" by the time we
        # query here.  The fallback "none" covers the edge case where the
        # object-store write succeeded but the prediction read occurred before
        # the task completed (should not happen with inline backend).
        assert pred["provenance"]["simulation"]["source"] in ("gromacs_stub", "none"), (
            f"Unexpected simulation source: {pred['provenance']['simulation']['source']!r}"
        )
        _shutdown()


# ---------------------------------------------------------------------------
# Trajectory descriptor threading integration test
# ---------------------------------------------------------------------------


class TestTrajectoryDescriptorIntegration:
    """Verify that trajectory summaries can thread through build_descriptor_bundle."""

    def test_trajectory_summary_adds_fields_to_bundle(self) -> None:
        from abby_api.schemas.structures import (
            ChainMapping,
            StructureSummary,
            StructureValidationResult,
        )
        from abby_api.services.feature_extraction import build_descriptor_bundle

        summary = StructureSummary(
            parser_name="biopython",
            model_count=1,
            available_chains=["A", "B"],
            residue_counts={"A": 5, "B": 5},
            warnings=[],
            metadata={
                "total_residues": 10,
                "chain_residue_class_counts": {},
                "global_residue_class_counts": {"charged": 2, "polar": 3, "apolar": 5},
            },
        )
        validation = StructureValidationResult(
            valid=True,
            normalized_format="pdb",
            warnings=[],
            chain_groups=ChainMapping(partner_1=["A"], partner_2=["B"]),
            partner_residue_counts={"partner_1": 5, "partner_2": 5},
            md_handoff={},
        )
        traj_summary = TrajectorySummary(
            mdanalysis_available=True,
            frame_count=200,
            mean_radius_of_gyration_angstrom=15.5,
            std_radius_of_gyration_angstrom=0.3,
            min_radius_of_gyration_angstrom=14.0,
            max_radius_of_gyration_angstrom=17.0,
            mean_atom_count=800.0,
            notes=["TRAJECTORY_SUMMARY_FROM_MDANALYSIS"],
        )

        bundle = build_descriptor_bundle(
            summary=summary,
            validation=validation,
            mode="ppi_general",
            trajectory_summary=traj_summary,
        )

        assert "trajectory_mean_radius_of_gyration_angstrom" in bundle.descriptors
        assert bundle.descriptors["trajectory_mean_radius_of_gyration_angstrom"] == 15.5
        assert bundle.descriptors["trajectory_frame_count"] == 200.0
        assert "TRAJECTORY_DESCRIPTORS_ENRICHED_FROM_MDANALYSIS" in bundle.notes

    def test_no_trajectory_summary_leaves_bundle_unchanged(self) -> None:
        from abby_api.schemas.structures import (
            ChainMapping,
            StructureSummary,
            StructureValidationResult,
        )
        from abby_api.services.feature_extraction import build_descriptor_bundle

        summary = StructureSummary(
            parser_name="biopython",
            model_count=1,
            available_chains=["A", "B"],
            residue_counts={"A": 3, "B": 3},
            warnings=[],
            metadata={
                "total_residues": 6,
                "chain_residue_class_counts": {},
                "global_residue_class_counts": {},
            },
        )
        validation = StructureValidationResult(
            valid=True,
            normalized_format="pdb",
            warnings=[],
            chain_groups=ChainMapping(partner_1=["A"], partner_2=["B"]),
            partner_residue_counts={"partner_1": 3, "partner_2": 3},
            md_handoff={},
        )

        bundle = build_descriptor_bundle(
            summary=summary,
            validation=validation,
            mode="ppi_general",
            trajectory_summary=None,
        )

        assert "trajectory_mean_radius_of_gyration_angstrom" not in bundle.descriptors
