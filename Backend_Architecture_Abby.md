# Abby Backend Architecture

This document describes the backend architecture for Abby and maps the system design to the product requirements in [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md), the high-level pipeline strategy in [`Dev_Plan.md`](./Dev_Plan.md), and the structure-processing implementation plan in [`Dev_Plan_Biopython.md`](./Dev_Plan_Biopython.md).

## 1. Architecture goals

Abby v1 backend should:

- support native `PDB` and `mmCIF/PDBx` ingestion
- validate and normalize structures before inference
- run single and batch affinity predictions asynchronously
- expose reproducible, versioned outputs through a stable API
- separate heavy structure processing from lightweight request handling
- keep full molecular simulation orchestration optional in v1 while preserving a clear path to phased GROMACS adoption

## 2. System context

At a high level, Abby has four backend responsibilities:

1. **API serving** for projects, uploads, predictions, jobs, and exports
2. **Structure processing** for parsing, validation, normalization, and descriptor generation
3. **Model inference orchestration** for consensus scoring and explainability
4. **Persistence and provenance** for files, metadata, results, and audit history

## 3. Logical architecture

```text
Client UI / SDK
    |
    v
API Layer (FastAPI)
    |
    +--> Auth & Request Validation
    +--> Project / Job Metadata Service
    +--> Object Storage Access Layer
    +--> Queue Publisher
                  |
                  v
        Async Workers / Orchestrator
                  |
                  +--> Structure Validation Service
                  +--> Descriptor Generation Service
                  +--> Model Inference Service
                  +--> Explainability / Consensus Service
                  |
                  v
        Postgres + Object Storage + Redis
```

## 4. Core backend components

## 4A. Initial folder structure

The starter repository structure should mirror the backend service boundaries while staying compact enough for early implementation:

```text
Abby/
├── .env
├── .gitignore
├── pyproject.toml
├── OpenAPI_Abby_v1.yaml
├── Backend_Architecture_Abby.md
├── V1_Product_Spec_Abby.md
├── Dev_Plan.md
├── Dev_Plan_Biopython.md
├── src/
│   └── abby_api/
│       ├── __init__.py
│       ├── main.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── router.py
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── batch_jobs.py
│       │       ├── predictions.py
│       │       ├── projects.py
│       │       ├── structures.py
│       │       └── system.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── security.py
│       ├── db/
│       │   └── session.py
│       ├── repositories/
│       │   ├── __init__.py
│       │   └── memory.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── common.py
│       │   ├── predictions.py
│       │   ├── projects.py
│       │   ├── structures.py
│       │   └── system.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── batch_jobs.py
│       │   ├── predictions.py
│       │   ├── projects.py
│       │   ├── structures.py
│       │   └── system.py
│       ├── storage/
│       │   └── object_store.py
│       └── workers/
│           ├── __init__.py
│           └── tasks.py
└── tests/
  └── test_health.py
```

### 4.1 API layer

**Recommended stack:** Python + FastAPI

Responsibilities:
- expose all `v1` REST endpoints from [`OpenAPI_Abby_v1.yaml`](./OpenAPI_Abby_v1.yaml)
- authenticate requests using API keys
- validate request payloads and schemas
- return job-oriented responses for async work
- serve signed export links and metadata

Why FastAPI:
- strong OpenAPI alignment
- good async support
- natural fit with Pydantic data contracts
- easy integration with scientific Python services

### 4.2 Auth and access control

Responsibilities:
- API key verification
- project-level authorization
- request-level audit identity propagation

v1 scope:
- single-tenant or low-complexity project ownership model
- no enterprise RBAC beyond project ownership and API-key scoping

### 4.3 Structure ingestion service

Responsibilities:
- accept uploaded `pdb`, `cif`, and `mmcif` files
- store original files in object storage
- calculate content hash (`sha256`)
- detect file type and route to parser pipeline

Implementation notes:
- use object storage for binary structure files
- avoid storing large structural payloads directly in Postgres
- emit a validation task after successful upload

### 4.4 Structure validation and normalization service

Responsibilities:
- parse structures using BioPython-based workflows
- normalize input to Abby's internal representation
- validate chain mapping and role assignment
- detect common issues:
  - missing chain identifiers
  - multiple structural models
  - unsupported residue counts
  - malformed mmCIF/PDB records

Primary libraries:
- `Bio.PDB`
- `MMCIFParser`
- `MMCIF2Dict`
- optional `MDAnalysis` for future trajectory-aware workflows

Outputs:
- normalized structure metadata
- validation report
- chain-role inference hints
- warnings/errors for UI and API clients

Additional v1 requirement for future MD integration:
- preserve simulation-handoff metadata (connectivity, chain mapping, and normalization provenance) so optional GROMACS workflows can be attached without changing core ingestion contracts
- treat `validation_dataset/ANDD_pdb/` as the canonical corpus for PDB→mmCIF conversion checks before validation or simulation handoff
- prefer the CIF-modified `Gromacs-CIF` backend for any mmCIF-driven topology generation path instead of vanilla GROMACS

Dataset-backed validation requirement:
- use `validation_dataset/ANDD_pdb/` as the canonical local regression corpus for validation, normalization, and export behavior
- keep the validation service aligned with that corpus so future parser or chain-mapping changes can be verified against representative Abby inputs
- extend validation summaries and tests whenever the dataset grows so roadmap docs and runtime behavior stay synchronized

### 4.5 Descriptor generation service

Responsibilities:
- compute structure-derived features needed by the predictive models
- generate interface and surface descriptors
- persist descriptor snapshots and descriptor hash for provenance

Inputs:
- normalized structure object
- validated chain mapping
- prediction mode (`ppi_general` or `antibody_antigen`)

Outputs:
- descriptor vector
- feature summary for explainability
- reproducible descriptor artifact for re-scoring

### 4.6 Model inference service

Responsibilities:
- load model bundles by version
- run supported model families:
  - linear
  - random forest
  - neural network
  - mixed models
- compute point estimates for `log(K)` and derived `ΔG`
- return per-model results and consensus result

Implementation notes:
- expose model bundle version explicitly in result payloads
- support offline retraining and bundle promotion without API breakage
- keep inference stateless so workers scale horizontally

### 4.7 Consensus and explainability service

Responsibilities:
- aggregate outputs from eligible models
- compute calibrated interval estimates
- assign confidence class (`high`, `medium`, `low`)
- flag out-of-distribution inputs
- rank top descriptor contributions for user display

v1 approach:
- consensus aggregation over validated model outputs
- lightweight explainability summaries rather than full SHAP-heavy pipelines

### 4.8 Job orchestration and worker queue

Responsibilities:
- coordinate long-running prediction work
- support retries and progress reporting
- separate single prediction latency from batch throughput concerns

Recommended stack:
- Redis + RQ / Celery, or RabbitMQ + Celery

Worker types:
- validation workers
- descriptor workers
- inference workers
- export workers
- optional simulation workers (v1.1+) for explicit simulation-backed requests

Why async:
- structure parsing and scoring can be CPU-heavy
- batch jobs must not block API request threads
- easier observability and retry semantics

### 4.9 Metadata database

**Recommended store:** PostgreSQL

Store in Postgres:
- projects
- structure metadata
- validation summaries
- prediction requests
- prediction summaries
- job state
- provenance metadata
- audit metadata

Do not store in Postgres:
- raw uploaded structure binaries
- large export files
- future trajectory files

### 4.10 Object storage

**Recommended store:** S3-compatible object storage

Use for:
- uploaded structures
- normalized structure artifacts
- descriptor snapshots (optional serialized artifacts)
- batch exports
- future derived files from simulation or visualization pipelines

### 4.11 Caching and rate limiting

**Recommended store:** Redis

Use for:
- short-lived status caching
- rate-limiting counters
- queue backend if selected
- signed export lookup optimization

### 4.12 Optional molecular simulation integration (phased)

To align with [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md), GROMACS integration should be explicit but staged.

**Phase 1 (v1):**
- keep the primary upload/validate/predict workflow simulation-free by default
- accept and persist MD-ready structure artifacts and provenance fields
- optionally ingest externally generated simulation summaries as derived descriptors

**Phase 2 (v1.1):**
- add async simulation workers for explicitly requested jobs
- execute GROMACS in isolated worker runtime profiles
- store simulation protocol metadata (force field, solvent model, ion settings, equilibration settings, random seed)

**Phase 3 (post-v1.1):**
- integrate trajectory-derived aggregates into standard descriptor generation
- version simulation protocols independently from model bundles

## 5. Data flow by workflow

### 5.1 Single prediction flow

1. Client uploads structure via `POST /structures:upload`.
2. API stores file in object storage and creates structure metadata record.
3. Validation worker parses the structure and writes validation report.
4. Client submits `POST /predictions`.
5. API enqueues inference job.
6. Worker loads normalized structure, generates descriptors, runs models.
7. Consensus/explainability layer prepares result payload.
8. API returns result from `GET /predictions/{prediction_id}`.

### 5.2 Batch prediction flow

1. Client submits `POST /batch-jobs` with many `structure_ids`.
2. API creates batch job record and per-item child tasks.
3. Workers process items independently.
4. Progress counters update in Postgres/Redis.
5. Export worker generates `csv` or `json` package.
6. Client retrieves status and export link.

### 5.3 Optional simulation-backed flow (v1.1+)

1. Client submits a prediction request with simulation enabled.
2. API creates a simulation-backed job and enqueues simulation worker tasks.
3. Simulation worker runs protocolized GROMACS stages and writes artifacts to object storage.
4. Descriptor worker consumes trajectory summaries and emits descriptor bundle + provenance.
5. Inference and consensus proceed through the same result contract as non-simulation runs.

## 6. Deployment view

### v1 deployment recommendation

- **API service**: containerized FastAPI app
- **Worker service**: separate container image sharing codebase with API
- **Postgres**: managed relational database
- **Redis**: managed cache/queue backend
- **Object storage**: S3-compatible bucket
- **Reverse proxy / ingress**: TLS termination and routing

For simulation-enabled phases, add a dedicated simulation worker profile/image so GROMACS dependencies do not become a mandatory runtime dependency of the default inference workers.

### Scaling strategy

- scale API pods on request volume
- scale worker pods on queue depth and CPU usage
- keep inference workers stateless for horizontal scaling
- isolate export generation if it becomes bursty

## 7. Observability

### Logs
Capture:
- request id
- project id
- structure id
- prediction id / job id
- model bundle version
- worker stage and duration

### Metrics
Track:
- upload latency
- validation success rate
- prediction queue wait time
- single prediction p50/p95
- batch completion rate
- export generation time
- failure rate by stage

### Tracing
Use distributed tracing across:
- API request
- queue publish
- worker execution
- storage operations

## 8. Security and compliance posture

v1 controls:
- TLS everywhere
- API key hashing at rest
- malware scanning for uploaded files
- size limits on uploads
- signed URLs for exports
- immutable provenance metadata for scientific reproducibility

Future controls:
- stronger tenant isolation
- audit export for regulated environments
- KMS-backed encryption and secret rotation

## 9. Failure modes and mitigations

| Failure mode | Likely cause | Mitigation |
| :-- | :-- | :-- |
| Invalid chain mapping | user provided wrong chains | preflight validation and guided error payload |
| Bad mmCIF/PDB parsing | malformed input or unsupported records | parser fallback, structured errors, normalized validation report |
| Slow batch jobs | queue saturation or CPU bottleneck | autoscale workers, split worker pools by stage |
| Inconsistent results | untracked model changes | explicit model bundle versioning and descriptor hashing |
| Large-file handling issues | oversize upload or storage timeouts | file size limits, streaming upload, retry logic |
| Simulation job instability | resource exhaustion or protocol misconfiguration | isolated simulation worker pool, protocol validation, retries with capped runtime |

## 10. Recommended repository doc map

- Product scope: [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md)
- System strategy: [`Dev_Plan.md`](./Dev_Plan.md)
- Structure-processing implementation: [`Dev_Plan_Biopython.md`](./Dev_Plan_Biopython.md)
- API contract: [`OpenAPI_Abby_v1.yaml`](./OpenAPI_Abby_v1.yaml)
- Backend design: [`Backend_Architecture_Abby.md`](./Backend_Architecture_Abby.md)
- Frontend design sketch: [`Frontend_Architecture_Abby.md`](./Frontend_Architecture_Abby.md)

## 11. v1 implementation order

1. Build API skeleton from OpenAPI contract
2. Implement upload + validation pipeline
3. Implement metadata persistence and job queue
4. Implement descriptor generation and model inference workers
5. Implement explainability and exports
6. Add observability, hardening, and benchmark validation
