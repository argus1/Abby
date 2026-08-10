# PyTorch and Triton Integration Development Plan

## Executive assessment

PyTorch integration is feasible and fits the current architecture. Abby already
has the important boundaries in place:

- `src/abby_api/services/graph_models.py` defines a versioned `StructureGraph`
  with 28-dimensional residue-node features, contact/backbone/covalent edge
  types, and a learner-agnostic training contract.
- `run_gnn_inference()` and `run_training_pipeline()` already degrade to an
  explicit stub when optional ML libraries are unavailable.
- `predictions.py` submits learned-model work through the existing asynchronous
  worker interface and persists learned-model provenance and graph artifacts.
- Batch execution, object storage, prediction status, and export contracts are
  already available for scaling inference without changing the public workflow.

The current implementation is a contract and graph-builder, not a working
PyTorch model. It has no tensor conversion layer, checkpoint format, model
registry, real forward pass, or learned-model evaluation artifact. The active
environment also does not currently provide `torch`, `torch_geometric`,
`tritonclient`, or `onnx`.

Triton inference is also feasible, but it should be a gated deployment phase.
It becomes useful when Abby has a real, versioned model and enough concurrent
or batch traffic to justify a separate inference server. Triton should not be
introduced before local PyTorch inference has a measured performance and
correctness baseline. The first production path should remain a worker-local
PyTorch adapter with the existing stub fallback.

## Recommended scope and decisions

- [ ] Keep PyTorch and related ML packages optional for the default API install.
- [ ] Make the first supported learned model a small, deterministic PyTorch
      graph model consuming Abby's existing `StructureGraph` contract.
- [ ] Prefer plain PyTorch tensors and a small internal message contract before
      adopting PyTorch Geometric. PyG can be added when batching, graph
      convolution layers, or model ergonomics demonstrate a clear benefit.
- [ ] Keep graph construction, structure parsing, mmCIF connectivity, CDR
      annotation, and descriptor provenance independent of the tensor framework.
- [ ] Preserve `run_gnn_inference()` as the orchestration entry point and add a
      backend adapter beneath it rather than exposing framework details in API
      schemas.
- [ ] Treat Triton as an optional serving profile, separate from the FastAPI
      container and general worker process.
- [ ] Do not make GPU availability, Triton, PyG, or model downloads mandatory
      for structure upload, validation, baseline prediction, or simulation.

## Phase 0: Contract and data audit

**Goal:** freeze the inputs and outputs before adding a framework dependency.

- [ ] Confirm the graph schema version and document the exact tensor contract:
      node feature shape `[N, 28]`, edge index shape `[2, E]`, edge-type encoding,
      partner masks, interface mask, and graph metadata.
- [ ] Decide whether edge types are represented as a categorical edge feature,
      one-hot features, or separate relation masks.
- [ ] Define deterministic ordering for residues and edges, including multiple
      models, insertion codes, missing coordinates, and mmCIF `_struct_conn`
      records.
- [ ] Add a graph-to-tensor serialization test with fixed expected tensors for
      a small PDB fixture and an mmCIF connectivity fixture.
- [ ] Define the model output contract for affinity inference, including
      `log_k`, optional interval estimates, confidence, OOD flag, model ID,
      model version, and preprocessing/graph versions.
- [ ] Define failure semantics for malformed graphs, empty graphs, unsupported
      residues, missing optional observations, CPU-only execution, and model
      artifact failures.
- [ ] Add a model artifact manifest contract containing model ID, model version,
      graph version, descriptor version, preprocessing version, framework
      version, state-dict hash, training-data provenance, and calibration data.

## Phase 1: PyTorch runtime and tensor adapter

**Goal:** make PyTorch available without changing the default runtime behavior.

- [ ] Add a `ml` optional dependency group with a pinned, supportable PyTorch
      range and a documented CPU installation path.
- [ ] Add a separate optional group for PyG only if the first model needs it;
      avoid making compiled PyG wheels part of the base installation.
- [ ] Add configuration for ML backend selection, model artifact location,
      device (`cpu`, `cuda`, or automatic), and strict-versus-fallback mode.
- [ ] Implement an internal tensor adapter that converts `StructureGraph` into
      tensors without importing PyTorch at module import time.
- [ ] Validate tensor shapes, finite numeric values, index bounds, and graph
      version before inference.
- [ ] Add CPU deterministic settings and seed handling for test and evaluation
      runs; document which CUDA operations may remain nondeterministic.
- [ ] Expose ML capability and model readiness in health metadata while keeping
      missing optional packages a non-fatal dependency state.
- [ ] Add focused tests that pass with PyTorch absent and with PyTorch present.

## Phase 2: First real PyTorch model

**Goal:** replace the GNN hook's empty prediction path with a small verifiable
model, while preserving the existing API and worker lifecycle.

- [ ] Implement a minimal graph model using plain PyTorch modules first. It
      should aggregate node features and contact/interface information into an
      affinity prediction suitable for a baseline learned-model experiment.
- [ ] Add a model adapter interface with `load`, `predict`, `metadata`, and
      `close` responsibilities so future PyG, ONNX, or Triton adapters share a
      contract.
- [ ] Implement checkpoint loading from an object-store artifact or local test
      path with hash verification and safe map-location handling.
- [ ] Add a versioned model registry lookup keyed by `model_id`, with explicit
      rejection of unknown or incompatible graph/preprocessing versions.
- [ ] Update `run_gnn_inference()` to select the PyTorch adapter before the
      existing external backend hooks, according to explicit configuration.
- [ ] Persist model output, model manifest, input graph summary, and inference
      timing as learned-model artifacts.
- [ ] Thread model version, checkpoint hash, device, and inference status into
      `LearnedModelProvenance` without changing existing clients' required
      fields.
- [ ] Add tests for successful CPU inference, deterministic repeated inference,
      bad checkpoint hash, incompatible graph version, empty graph, and stub
      fallback.

## Phase 3: SPR-grounded training and evaluation

**Goal:** make a learned result scientifically testable rather than merely
technically executable.

- [ ] Define the training dataset manifest for `SPRTrainingRecord` inputs,
      including source, assay conditions, units, split assignment, and license
      or attribution metadata.
- [ ] Add deterministic train/validation/test splitting by structure or project
      family to prevent near-duplicate leakage.
- [ ] Implement the PyTorch branch of `run_training_pipeline()` with seeded
      training, checkpoint output, validation metrics, and early stopping.
- [ ] Add calibration artifacts and connect calibration version/hash to model
      provenance and prediction intervals.
- [ ] Report Pearson correlation, RMSE, MAE, rank correlation where useful,
      calibration error, and OOD performance with sample counts and split IDs.
- [ ] Add regression tests that verify artifact manifests, reproducible splits,
      checkpoint hashes, and stable metrics on a tiny synthetic dataset.
- [ ] Run a dataset-backed pilot using approved SPR data; do not treat synthetic
      tests as evidence of scientific accuracy.
- [ ] Define promotion criteria against the deterministic baseline before a
      PyTorch model can become the default learned backend.

## Phase 4: Batch and worker integration

**Goal:** use the existing asynchronous architecture safely at inference time.

- [ ] Add a worker-local model lifecycle so each worker loads a compatible model
      once and reuses it, rather than loading a checkpoint per prediction.
- [ ] Add bounded concurrency, queue backpressure, and maximum graph-size
      safeguards for single and batch learned-model jobs.
- [ ] Extend batch result/export payloads with learned-model status and artifact
      references while preserving baseline result compatibility.
- [ ] Record per-item inference duration, queue duration, device, backend, and
      failure category for observability.
- [ ] Add tests for concurrent batch inference, partial failures, retry behavior,
      model-load failure, and worker shutdown/reload behavior.
- [ ] Benchmark CPU throughput and p95 latency against the current baseline
      worker for representative small, medium, and large structures.

## Phase 5: Triton feasibility gate

**Goal:** decide from measurements whether a separate inference server is
justified.

- [ ] Establish target service objectives for interactive inference and batch
      campaigns: p50/p95 latency, throughput, cold-start time, memory ceiling,
      acceptable queue delay, and failure recovery time.
- [ ] Compare worker-local PyTorch against a Triton prototype using the same
      model, graph serialization, batch sizes, and hardware.
- [ ] Verify that the graph input contract can be represented by Triton's
      request tensors without losing masks, edge types, or provenance fields.
- [ ] Choose a serving format: TorchScript, ONNX, or a supported PyTorch backend;
      document unsupported operators and numerical-difference tolerances.
- [ ] Define the Triton model repository layout, model configuration, instance
      groups, dynamic batching policy, readiness checks, and resource limits.
- [ ] Add a thin Triton client adapter behind the same internal model interface;
      the API must not depend directly on Triton protocol details.
- [ ] Add request IDs and model-version headers/metadata so Triton responses
      remain traceable to Abby prediction and graph artifacts.
- [ ] Add a local CPU or GPU integration profile for Triton, marked optional in
      CI when the required runtime is unavailable.
- [ ] Add parity tests comparing worker-local and Triton outputs within defined
      tolerances on fixed graphs.
- [ ] Adopt Triton only if it materially improves the agreed latency/throughput
      target or provides required GPU isolation and operational scaling.

## Phase 6: Triton production hardening, if the gate passes

- [ ] Add a Triton service to an optional deployment profile rather than the
      default `docker-compose` path.
- [ ] Add API-to-Triton timeout, retry, circuit-breaker, and fallback behavior.
- [ ] Decide whether fallback means worker-local inference, queued retry, or an
      explicit unavailable result; record that decision in provenance.
- [ ] Add health checks for Triton liveness, readiness, model readiness, and
      model-version compatibility.
- [ ] Add metrics for request rate, batch size, queue time, inference time,
      GPU memory, errors, timeouts, and fallback count.
- [ ] Load-test concurrent single requests and batch requests with realistic
      structure-size distributions.
- [ ] Document model rollout, rollback, repository synchronization, and
      checkpoint security procedures.
- [ ] Add an end-to-end test covering upload, validate, baseline prediction,
      learned inference, artifact persistence, and result retrieval.

## Files and boundaries likely to change

- `src/abby_api/services/graph_models.py`: tensor adapter, model adapter,
  training branch, and backend selection.
- `src/abby_api/schemas/common.py` and `src/abby_api/schemas/predictions.py`:
  only additive provenance or status fields where required.
- `src/abby_api/services/predictions.py`: orchestration and artifact persistence,
  not tensor or framework-specific logic.
- `src/abby_api/workers/`: model lifecycle, resource limits, and optional serving
  dispatch.
- `src/abby_api/core/config.py`: optional ML and Triton configuration.
- `pyproject.toml`: optional dependency groups only; keep the base install light.
- `tests/test_learned_models.py` plus focused tensor/model/serving tests.
- `docker-compose.yml`: only an opt-in Triton profile after the feasibility gate.
- `OpenAPI_Abby_v1.yaml`: update only for intentional additive contract changes.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| PyTorch/PyG platform and CUDA dependency size | Keep packages optional; start with plain PyTorch and CPU tests. |
| Graph semantics drift from mmCIF/connectivity rules | Freeze graph fixtures and version compatibility checks before training. |
| Data leakage in SPR evaluation | Split by structure/project/family and persist split manifests. |
| Uncalibrated learned affinity outputs | Treat calibration as a required artifact, not an afterthought. |
| Triton adds operational complexity without benefit | Require benchmark evidence and keep worker-local inference as the baseline. |
| Model artifact or serving mismatch | Verify manifest hashes and graph/preprocessing versions at load time. |
| GPU-only assumptions break local development | Support CPU execution and explicit unavailable/stub behavior. |

## Exit criteria

- [ ] A real PyTorch model can run on a validated Abby graph on CPU with a
      reproducible result and complete provenance.
- [ ] Missing ML dependencies preserve all existing baseline and structure
      workflows, with explicit learned-model fallback behavior.
- [ ] Training, evaluation, calibration, and model artifacts are reproducible
      and traceable to input graph and dataset manifests.
- [ ] Batch learned inference has bounded resource use, partial-failure
      handling, and focused regression coverage.
- [ ] Triton adoption is backed by a recorded benchmark and parity result, or
      explicitly deferred with the reason documented.

## Suggested first implementation slice

- [ ] Add the optional PyTorch dependency group and ML configuration.
- [ ] Implement and test `StructureGraph` to tensor conversion.
- [ ] Add a tiny CPU-only PyTorch model adapter with deterministic checkpoint
      loading and manifest validation.
- [ ] Route one explicit `model_id` through `run_gnn_inference()` while leaving
      the current stub and external backend paths intact.
- [ ] Run `tests/test_learned_models.py`, the new tensor/model tests, and
      `ruff check .` before considering Triton design work.
