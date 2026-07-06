# Abby Frontend Architecture Sketch

This document sketches a frontend for Abby that is compatible with the containerized development and deployment setup defined by [`docker-compose.yml`](./docker-compose.yml), the API contract in [`OpenAPI_Abby_v1.yaml`](./OpenAPI_Abby_v1.yaml), and the backend service boundaries in [`Backend_Architecture_Abby.md`](./Backend_Architecture_Abby.md).

## 1. Frontend goals

The Abby frontend should enable end-to-end usage for life science researchers by supporting:

- project creation and project-level navigation
- structure upload and validation
- single prediction workflows
- batch job submission and progress tracking
- prediction interpretation and export
- variant comparison and shortlist generation

## 2. Recommended frontend stack

For Abby v1, a practical frontend stack is:

- **React + TypeScript** for UI development
- **Vite** for fast local development and simple container integration
- **React Router** for multi-page workflow navigation
- **TanStack Query** for API fetching, caching, and polling
- **Zod** or generated TypeScript types for response validation
- **Tailwind CSS** or a minimal component system for fast UI iteration

Why this stack works well with option 3:

- Vite runs cleanly in its own dev container or local Node environment
- the frontend can target `http://localhost:8000/api/v1`
- TanStack Query handles the asynchronous prediction and batch-job states naturally
- React is flexible enough for upload flows, tables, and scientific result views

## 3. Container compatibility model

The frontend should be designed to run as a separate service from the Abby API.

### Local containerized topology

```text
Browser
  |
  +--> Frontend dev server (future: port 5173)
  |
  +--> Abby API (port 8000)
           |
           +--> Postgres
           +--> Redis
           +--> Object Storage (MinIO)
```

### Frontend runtime assumptions

- API base URL is configured via environment variable
- frontend never talks directly to Postgres/Redis/MinIO
- long-running operations are modeled as async API jobs
- polling or server push can be introduced later without changing page structure

Recommended frontend env var:

- `VITE_ABBY_API_BASE_URL=http://localhost:8000/api/v1`

## 4. Primary user flows

### 4.1 Single prediction flow

1. User lands on dashboard.
2. User creates/selects a project.
3. User uploads a structure file.
4. User validates chain mappings.
5. User submits a prediction.
6. Frontend polls prediction status.
7. User views result, explainability, and exports.

### 4.2 Batch campaign flow

1. User opens a project campaign page.
2. User uploads or selects many structures.
3. User submits a batch job.
4. Frontend polls batch job progress.
5. User views ranked result table.
6. User exports shortlisted candidates.

### 4.3 Compare flow

1. User opens a prediction result.
2. User selects a baseline prediction.
3. Frontend renders side-by-side summary and descriptor deltas.
4. User saves a comparison snapshot to the project.

## 5. Suggested page map

- `/` — dashboard / recent projects
- `/projects/:projectId` — project overview
- `/projects/:projectId/new-prediction` — guided single prediction flow
- `/projects/:projectId/structures/:structureId` — structure validation detail
- `/predictions/:predictionId` — prediction result page
- `/projects/:projectId/batch-jobs/:jobId` — batch job progress and result table
- `/compare/:leftPredictionId/:rightPredictionId` — comparison view
- `/settings` — API key and environment settings for local/dev usage

## 6. Suggested component structure

```text
frontend/
├── src/
│   ├── app/
│   │   ├── router.tsx
│   │   ├── query-client.ts
│   │   └── providers.tsx
│   ├── components/
│   │   ├── layout/
│   │   ├── forms/
│   │   ├── tables/
│   │   ├── charts/
│   │   └── status/
│   ├── features/
│   │   ├── projects/
│   │   ├── structures/
│   │   ├── predictions/
│   │   ├── batch-jobs/
│   │   └── compare/
│   ├── lib/
│   │   ├── api-client.ts
│   │   ├── config.ts
│   │   └── formatters.ts
│   ├── pages/
│   │   ├── dashboard/
│   │   ├── compare/
│   │   ├── project/
│   │   ├── prediction/
│   │   └── batch-job/
│   └── types/
│       └── api.ts
```

## 7. API integration pattern

The frontend should treat the Abby API as the source of truth for all workflow state.

### Query patterns

- standard fetch for static resources:
  - `GET /health`
  - `GET /version`
  - `GET /models`
- mutation + invalidate for writes:
  - `POST /projects`
  - `POST /structures:upload`
  - `POST /structures:validate`
  - `POST /predictions`
  - `POST /batch-jobs`
- polling for async results:
  - `GET /predictions/{prediction_id}`
  - `GET /batch-jobs/{job_id}`
  - `GET /batch-jobs/{job_id}/results`

### Frontend state boundaries

Keep these server-driven:

- projects
- structures
- validation status
- prediction status/results
- batch job status/results
- export links

Keep these client-driven:

- upload form draft state
- selected filters/sorts
- comparison view selections
- visualization toggles

## 7A. Service-layer feature stubs in the UI

The first frontend scaffold should make the planned backend logic visible even before all scientific services are fully implemented.

### Mapping from service-layer plan to UI stubs

| Planned backend module | UI surface | Stub behavior in the first frontend |
| :-- | :-- | :-- |
| `services/structures.py` | Upload + structure detail views | Show chain grouping fields, parser choice, validation warnings, and partner mapping status |
| `services/structure_parsing.py` | Structure detail view | Show normalized-format summary and parser/consistency checks as read-only diagnostics |
| `services/feature_extraction.py` | Prediction result + dashboard | Show planned contact bins, RSA/NIS descriptors, and explainability descriptor families |
| `services/baseline_models.py` | Prediction result page | Show placeholder baseline sections for $\Delta G$, $K_d$, and log-scale output |
| `services/exports.py` | Prediction result + batch job views | Show disabled or stubbed actions for contact list export, PyMOL script generation, and descriptor bundle download |

### Why stubbing this way matters

This lets frontend and backend development proceed in parallel:

- frontend can establish page structure and user workflows now
- backend can replace stub payloads incrementally as services mature
- the UI already reflects Abby's scientific architecture instead of a generic file-upload shell

## 8. UX expectations for scientific users

The frontend should optimize for trust and throughput, not flash.

Important UX behaviors:

- show exact file names and chain mappings during upload/validation
- clearly differentiate `queued`, `running`, `completed`, and `failed`
- show confidence level alongside affinity values
- expose provenance and model version in result details
- make exports easy and obvious
- make it simple to revisit historical jobs inside a project

## 9. Frontend and option 3 alignment

Option 3 improves frontend development by giving Abby a predictable local backend stack:

- backend always lives at a known address and port
- Redis/Postgres/MinIO are available without manual setup
- developers can test file upload and long-running job UX against a real stack shape
- future frontend containerization can be added without redesigning API usage

## 10. Suggested next frontend step

When you are ready to move beyond the sketch, the best next step is to scaffold a dedicated frontend app with:

- `frontend/` directory
- Vite + React + TypeScript
- generated API types from `OpenAPI_Abby_v1.yaml`
- TanStack Query hooks for Abby endpoints
- first screens: dashboard, upload/validate flow, prediction results
