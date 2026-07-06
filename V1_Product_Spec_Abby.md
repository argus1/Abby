# Abby v1 Product Specification

## 1) Product Summary

Abby v1 is a researcher-facing web and API platform for predicting binding affinity of protein-protein and antibody-antigen complexes from 3D structures, with uncertainty, interpretability, and batch workflows suitable for discovery campaigns.

This project is an independent implementation that builds on published area-based affinity modeling concepts, without implying formal collaboration with external authors or maintenance teams.

### Related documents
- System development plan: [`Dev_Plan.md`](./Dev_Plan.md)
- Technical implementation plan: [`Dev_Plan_Biopython.md`](./Dev_Plan_Biopython.md)
- API contract: [`OpenAPI_Abby_v1.yaml`](./OpenAPI_Abby_v1.yaml)
- Backend architecture: [`Backend_Architecture_Abby.md`](./Backend_Architecture_Abby.md)
- Frontend architecture sketch: [`Frontend_Architecture_Abby.md`](./Frontend_Architecture_Abby.md)
- Structural format and data integrity references: see the linked research notes in the repo root

### Problem
Current affinity predictors are often hard to operationalize in wet-lab workflows due to format friction, weak confidence reporting, and limited campaign-scale support.

### v1 Goal
Turn area-based affinity prediction into a practical decision tool that helps scientists choose which variants to test next.

### v1 Success Criteria
- Median time-to-result for a single complex: < 90 seconds.
- Batch processing: >= 1,000 complexes/job.
- Calibration: 90% prediction interval covers observed values on benchmark holdout >= 85% of time.
- Usability: user can upload, run, interpret, and export in < 5 clicks from dashboard.

---

## 2) Target Users

1. **Antibody engineers** (lead optimization; variant triage)
2. **Computational biologists** (pipeline automation via API)
3. **Protein scientists** (complex comparison and hypothesis generation)
4. **Translational teams** (supporting SPR/BLI assay planning)

---

## 3) In-Scope for v1

### Core Functional Scope
- Predict affinity for:
  - general protein-protein complexes
  - antibody-antigen complexes
- Input formats:
  - PDB
  - mmCIF / PDBx/mmCIF (native support)
- Run modes:
  - Single prediction
  - Batch prediction
- Outputs:
  - point estimate (log(K), ΔG)
  - uncertainty interval
  - model consensus score
  - feature contribution summary
- Export:
  - CSV
  - JSON

### Explicitly Out of Scope (v1)
- Full molecular dynamics simulation orchestration
- De novo structure generation
- Wet-lab inventory / LIMS as first-party module (API hooks only)
- Multi-tenant enterprise RBAC beyond project-level roles

---

## 4) Key Features (v1)

### F1. Native Structure Ingestion
- Accepts PDB and mmCIF directly.
- Automatic structure normalization and validation.
- Detects common issues (missing chain IDs, multiple models, incompatible residues count).

### F2. Affinity Prediction Engine
- Uses curated model families:
  - linear
  - random forest
  - neural network
  - mixed models
- Supports mode:
  - `ppi_general`
  - `antibody_antigen`
- Produces:
  - predicted `log_k`
  - derived `delta_g_kcal_mol`
  - confidence interval (calibrated)

### F3. Consensus + Confidence
- Aggregates across eligible models into consensus prediction.
- Reports confidence class:
  - High
  - Medium
  - Low
- Flags out-of-distribution inputs.

### F4. Explainability Panel
- Top contributing area descriptors.
- Interface composition breakdown by amino-acid class groups.
- “What changed” comparison between two structures/variants.

### F5. Batch Campaign Workflow
- Upload list of structures and metadata.
- Async processing with job status and retry.
- Ranking by user objective:
  - strongest affinity
  - largest predicted gain vs baseline
  - high-confidence candidates only

### F6. Research Export & Reproducibility
- Full provenance bundle:
  - model version
  - preprocessing version
  - run timestamp
  - descriptor snapshot hash
- Machine-readable export for notebook and ELN/LIMS integration.

---

## 5) Data Contracts

All timestamps are ISO-8601 UTC. IDs are UUIDv4 unless otherwise noted.

### 5.1 Entity: Project
```json
{
  "project_id": "2a6e7ce9-3c4f-4871-8f44-5adf0d72e4bf",
  "name": "HER2 Optimization Round 3",
  "owner": "user_123",
  "created_at": "2026-07-05T10:03:22Z"
}
```

### 5.2 Entity: StructureInput
```json
{
  "structure_id": "e8c61d7d-0f0f-4dd1-b87a-6fb863807fef",
  "format": "mmcif",
  "source": "upload",
  "filename": "af3_candidate_017.cif",
  "sha256": "b9f3...",
  "chains": {
    "partner_1": ["H", "L"],
    "partner_2": ["A"]
  },
  "mode": "antibody_antigen"
}
```

### 5.3 Entity: PredictionRequest
```json
{
  "project_id": "2a6e7ce9-3c4f-4871-8f44-5adf0d72e4bf",
  "mode": "antibody_antigen",
  "structure_id": "e8c61d7d-0f0f-4dd1-b87a-6fb863807fef",
  "options": {
    "return_all_models": true,
    "include_explainability": true,
    "temperature_kelvin": 298.15
  },
  "metadata": {
    "candidate_id": "C017",
    "baseline_candidate_id": "WT"
  }
}
```

### 5.4 Entity: PredictionResult
```json
{
  "prediction_id": "3df6b500-3f18-4377-b6b8-e0f7e01ec6bb",
  "status": "completed",
  "mode": "antibody_antigen",
  "consensus": {
    "log_k": -8.42,
    "delta_g_kcal_mol": -11.48,
    "pi90": {
      "lower": -9.01,
      "upper": -7.89
    },
    "confidence": "high",
    "ood_flag": false
  },
  "best_model": {
    "model_id": "mixed_nn_v1_3",
    "log_k": -8.47,
    "delta_g_kcal_mol": -11.55,
    "r_validation": 0.85
  },
  "all_models": [
    {
      "model_id": "linear_v1_2",
      "log_k": -8.10
    },
    {
      "model_id": "rf_v1_11",
      "log_k": -8.39
    }
  ],
  "explainability": {
    "top_descriptors": [
      {"name": "A10_nonpolar_nonpolar_interface", "contribution": 0.31},
      {"name": "A19_total_rsa", "contribution": -0.19},
      {"name": "A16_nonpolar_polar_interface", "contribution": 0.14}
    ]
  },
  "provenance": {
    "model_bundle_version": "2026.07.v1",
    "preprocess_version": "2.1.0",
    "descriptor_hash": "6f9a...",
    "created_at": "2026-07-05T10:22:45Z"
  }
}
```

### 5.5 Entity: BatchJob
```json
{
  "job_id": "03e8e1d4-5308-4a05-bd30-8a5eb64f62ab",
  "project_id": "2a6e7ce9-3c4f-4871-8f44-5adf0d72e4bf",
  "status": "running",
  "counts": {
    "queued": 1000,
    "running": 120,
    "completed": 740,
    "failed": 140
  },
  "created_at": "2026-07-05T11:00:00Z",
  "updated_at": "2026-07-05T11:06:41Z"
}
```

### 5.6 Standard Error Contract
```json
{
  "error": {
    "code": "INVALID_CHAIN_MAPPING",
    "message": "Chain identifiers do not map to two valid binding partners.",
    "details": {
      "partner_1": ["H", "L"],
      "partner_2": ["Z"]
    },
    "request_id": "d0f0d11a-51cd-4987-98de-0542ef4ce92a"
  }
}
```

---

## 6) API Endpoints (v1)

Base path: `/api/v1`

### Authentication
- v1 supports API key authentication:
  - Header: `X-API-Key: <token>`

### 6.1 Projects
- `POST /projects` — create project
- `GET /projects/{project_id}` — get project
- `GET /projects/{project_id}/jobs` — list jobs in project

### 6.2 Structures
- `POST /structures:upload` — multipart upload (`.pdb`, `.cif`, `.mmcif`)
- `POST /structures:validate` — validate and preview parsed partners/chains
- `GET /structures/{structure_id}` — metadata + validation report

### 6.3 Predictions (Single)
- `POST /predictions` — submit single prediction request
- `GET /predictions/{prediction_id}` — get result/status
- `GET /predictions/{prediction_id}/explainability` — detailed descriptor contributions

### 6.4 Predictions (Batch)
- `POST /batch-jobs` — submit batch request
- `GET /batch-jobs/{job_id}` — status/progress
- `GET /batch-jobs/{job_id}/results` — paginated results
- `GET /batch-jobs/{job_id}/export?format=csv|json` — downloadable export

### 6.5 Health and Versioning
- `GET /health` — service health
- `GET /models` — available model bundles and validation metrics
- `GET /version` — API and preprocessing versions

### 6.6 Example Request/Response
`POST /api/v1/predictions`
```json
{
  "project_id": "2a6e7ce9-3c4f-4871-8f44-5adf0d72e4bf",
  "mode": "ppi_general",
  "structure_id": "e8c61d7d-0f0f-4dd1-b87a-6fb863807fef",
  "options": {
    "return_all_models": false,
    "include_explainability": true
  }
}
```

`202 Accepted`
```json
{
  "prediction_id": "3df6b500-3f18-4377-b6b8-e0f7e01ec6bb",
  "status": "queued"
}
```

---

## 7) UI Flow (v1)

### 7.1 Primary Flow: Single Prediction
1. **Dashboard** → click “New Prediction”.
2. **Upload Structure** (PDB/mmCIF) or select existing structure.
3. **Map Chains** to Partner 1 / Partner 2 (or Antibody / Antigen).
4. **Choose Mode** (`ppi_general` or `antibody_antigen`).
5. **Run Prediction**.
6. **Results Page**:
   - consensus affinity (log(K), ΔG)
   - confidence interval and confidence class
   - top descriptors and contributions
   - optional per-model detail panel
7. **Export** CSV/JSON or add to campaign list.

### 7.2 Secondary Flow: Batch Campaign
1. Campaign page → “Create Batch Job”.
2. Upload ZIP/manifest CSV with structure references.
3. Validate all entries (errors downloadable).
4. Run async job with live progress.
5. Ranked results table with filters:
   - confidence = high
   - top predicted binders
   - predicted gain vs baseline
6. Export shortlist for lab testing.

### 7.3 Compare Flow: Variant vs Baseline
1. Open candidate result.
2. Click “Compare to Baseline”.
3. View delta panel:
   - Δlog(K)
   - ΔΔG
   - descriptor change chart
4. Save comparison snapshot to project.

---

## 8) Non-Functional Requirements

- **Performance:**
  - p50 single inference < 60s; p95 < 120s
  - batch throughput >= 10 predictions/sec under nominal load
- **Reliability:** 99.5% monthly uptime target
- **Scalability:** horizontal worker scaling for async jobs
- **Security:** TLS, API key hashing, file malware scan, signed download URLs
- **Auditability:** every prediction has immutable provenance metadata

---

## 9) Acceptance Criteria (v1)

### Product Acceptance
- User can complete single prediction from upload to export in one session without docs.
- User can run a 500-entry batch and download ranked results with confidence labels.

### Technical Acceptance
- API contracts match examples in this spec.
- Validation catches malformed chain mapping and unsupported file payloads.
- Results include consensus + interval + provenance for all successful predictions.

### Scientific Acceptance
- Reproduces baseline expected performance of representative mixed models.
- Confidence calibration documented on holdout benchmark.

---

## 10) v1 Risks and Mitigations

1. **Risk:** Prediction quality drops for low-quality modeled structures.  
   **Mitigation:** quality gates + confidence downgrade + OOD flag.

2. **Risk:** User confusion between model outputs.  
   **Mitigation:** default consensus view; hide advanced model panels behind expandable section.

3. **Risk:** Batch failures due to inconsistent chain metadata.  
   **Mitigation:** preflight validator + downloadable error report + guided fix hints.

---

## 11) v1.1 Forward Extensions (Not in v1)

- Mutation scanning endpoint (`/mutations:scan`) with ΔΔG ranking.
- SPR/BLI assay planning assistant from confidence and affinity bins.
- Deeper mmCIF chemistry support (glycans/PTMs as explicit model inputs).
- Notebook SDK helpers for campaign analytics.
