# Abby Development Plan — CompDetRAE (CDR Annotation Engine)

This document defines a detailed implementation roadmap for Abby’s **Complementarity-Determining Region Annotation Engine (CompDetRAE)**, with focus on robust **CDR-H3-aware** structural bookkeeping and extension to full heavy/light CDR annotation.

It complements:

- `Dev_Plan.md`
- `Dev_Plan_Biopython.md`
- `Dev_Plan_Implementation_Checklist.md`

---

## 1) Objective and scope

### Primary objective
Build a deterministic, mmCIF-first, provenance-backed CDR annotation engine that:

1. Identifies antibody chains robustly (not only `H`/`L` IDs).
2. Detects and annotates CDR boundaries (starting with CDR-H3, then H1/H2/L1/L2/L3).
3. Persists region-level metadata for downstream validation, explainability, and optional simulation/learned-model workflows.
4. Maintains strict backward compatibility with current Abby APIs.

### Out-of-scope (for this plan slice)

- End-to-end model retraining of full learned affinity models.
- Mandatory simulation execution in default prediction flow.
- Replacing mmCIF-first parsing with legacy PDB-first shortcuts.

---

## 2) Key weaknesses to address (current Abby)

From current implementation:

- `cdr_bookkeeping_ready_flag` is heuristic-only (depends on chain IDs like `H`/`L`).
- No persisted residue-level CDR map in structure summary/validation/provenance.
- No explicit numbering-scheme support (IMGT/Kabat/Chothia/AHo) for boundary mapping.
- No dedicated CDR tests asserting region boundaries and edge cases.

---

## 3) Borrowed logic (adapted, not copied)

This plan incorporates proven ideas from referenced repositories, adapted to Abby architecture.

### A. Motif-based extraction fallback (from `antibody_sequence_modeling_example`)

Borrowed pattern:

- Use a fallback regex-like motif for CDR-H3 extraction from heavy sequence (e.g., `C...WGxG`-style flank), when explicit annotations are absent.
- Enforce schema/invariant checks:
  - non-empty extracted loop
  - length bounds
  - deterministic normalization and deduping

Abby adaptation:

- Use motif fallback only when numbering/annotation unavailable.
- Treat motif-only annotations as lower confidence in provenance (`boundary_source=motif_fallback`).
- Never overwrite explicit numbering-derived boundaries with motif fallback.

### B. Position-encoded feature matrix + classical baseline (from Carol logistic workflow)

Borrowed pattern:

- Convert per-position residues into numeric/feature vectors.
- Use a simple transparent baseline (multinomial/logistic style) for sanity checks.
- Report classic metrics (accuracy/sensitivity/specificity/AUC).

Abby adaptation:

- Add optional **CDR boundary confidence baseline model** (not production affinity model):
  - predicts `boundary_confidence_class` from positional/motif features
  - used for QA and drift monitoring
- Use it as verification tooling to avoid opaque failures.

### C. Mutation/position safety and robust parsing guards (from TwinCysteine scripts)

Borrowed pattern:

- Strict parsing/validation of position tokens.
- Fail-fast with rich errors for invalid residue indices/codes.
- Batch summary reporting with success/failure rollups.

Abby adaptation:

- For CDR annotation, apply the same defensive style:
  - strict chain/residue identity validation
  - insertion-code-safe indexing
  - clear typed warning/error codes for boundary ambiguity and out-of-range residues

---

## 4) Architecture additions

## 4.1 New service modules

- `src/abby_api/services/cdr_annotation.py`
  - chain typing (heavy/light/unknown)
  - boundary detection pipeline
  - confidence scoring + notes

- `src/abby_api/services/cdr_numbering.py`
  - numbering abstractions and boundary definitions
  - insertion code handling and normalized residue keys

- `src/abby_api/services/cdr_features.py` (optional in Phase 3+)
  - region-level descriptors (counts, composition, burial/contact stats by CDR)

## 4.2 Schema extensions

- `src/abby_api/schemas/structures.py`
  - Add typed CDR annotations in `StructureSummary.metadata` contract via documented keys.

- `src/abby_api/schemas/common.py`
  - Extend provenance with CDR boundary source, scheme, and confidence summary.

- `src/abby_api/schemas/predictions.py`
  - Optional `cdr_summary` block in feature/explainability payloads.

## 4.3 Metadata contract (target)

`summary.metadata["cdr_annotation"]`:

- `available: bool`
- `scheme: "imgt" | "kabat" | "chothia" | "aho" | "motif_fallback"`
- `boundary_source: "numbered" | "motif_fallback" | "hybrid"`
- `chains: {chain_id: {role, confidence, regions}}`
- `regions` includes at minimum:
  - `CDR-H3` initially
  - then `CDR-H1`, `CDR-H2`, `CDR-L1`, `CDR-L2`, `CDR-L3`
- `warnings: []`

---

## 5) Implementation phases, milestones, and checklists

## Phase 0 — Foundations and contracts (P0 / S)

### Milestone M0
Freeze CDR annotation interface and warning/error taxonomy before feature implementation.

### Checklist

- [x] Define CDR annotation glossary and region naming standard.
- [x] Define stable residue key format: `(chain_id, auth_seq_id/label_seq_id, insertion_code)`.
- [x] Define typed warning/error codes:
  - `CDR_CHAIN_ROLE_AMBIGUOUS`
  - `CDR_BOUNDARY_AMBIGUOUS`
  - `CDR_MOTIF_FALLBACK_USED`
  - `CDR_NUMBERING_MISSING`
- [x] Add architecture note linking CompDetRAE to `Dev_Plan_Biopython.md` and checklist roadmap.

### Exit criteria

- [x] Contract reviewed and documented.
- [x] No API breaking changes introduced.

### Implementation status notes (Phase 0)

- Implemented contract scaffolding:
  - `src/abby_api/services/cdr_annotation.py`
  - `src/abby_api/services/cdr_numbering.py`
- Added contract tests:
  - `tests/test_cdr_annotation.py`
- Existing feature-note path now emits `CDR_NUMBERING_MISSING` alongside the prior pending antibody CDR note until Phase 1 boundary extraction is complete.

---

## Phase 1 — CDR-H3 deterministic annotation MVP (P0 / M)

### Milestone M1
Produce stable CDR-H3 annotations with provenance, replacing placeholder semantics.

### Checklist

- [x] Implement heavy-chain candidate detection beyond `H`/`L` naming.
- [x] Implement prioritized boundary pipeline:
  1. numbering-aware boundary resolver (preferred)
  2. motif fallback (`C...WGxG`-style) when numbering absent
- [x] Add confidence scoring levels (`high`/`medium`/`low`) with deterministic rules.
- [x] Persist `CDR-H3` region residue indices in `summary.metadata["cdr_annotation"]`.
- [x] Replace `ANTIBODY_MODE_CDR_DETECTION_PENDING` with nuanced notes:
  - `CDR_H3_ANNOTATED`
  - or fallback/ambiguity notes.
- [x] Thread CDR-H3 summary into prediction provenance.

### Tests

- [x] Positive: clean heavy chain with resolvable CDR-H3.
- [x] Fallback: motif-only extraction path.
- [x] Negative: ambiguous motif or missing anchors.
- [x] Determinism: same input -> same CDR boundaries/hash metadata.

### Exit criteria

- [x] `cdr_bookkeeping_ready_flag` reflects actual annotation readiness, not chain-name heuristic only.
- [x] CDR-H3 metadata appears in structure detail and prediction provenance.

### Implementation status notes (Phase 1)

- Implemented deterministic Phase 1 CDR-H3 pipeline:
  - heavy-chain candidate detection no longer depends solely on `H`/`L` naming,
  - numbering-first resolver with motif fallback,
  - deterministic confidence assignment (`high` / `medium` / `low`).
- Added structured CDR metadata output under `summary.metadata["cdr_annotation"]` including typed warnings and residue-key ranges.
- Replaced placeholder antibody CDR note path with typed annotation notes (`CDR_H3_ANNOTATED`, fallback and ambiguity variants).
- Threaded CDR annotation summary into `PredictionResult.provenance` via typed `cdr_annotation` contract.
- Added/updated tests in `tests/test_cdr_annotation.py` for numbered, fallback, ambiguous, deterministic, and descriptor-flag behaviors.

### API payload snippet (structure + prediction)

Structure detail (`GET /api/v1/structures/{structure_id}`) excerpt:

```json
{
  "summary": {
    "metadata": {
      "cdr_annotation": {
        "available": true,
        "scheme": "kabat",
        "boundary_source": "numbered",
        "boundary_confidence": "high",
        "selected_heavy_chain": "X",
        "chains": {
          "X": {
            "role": "heavy",
            "confidence": "high",
            "regions": {
              "CDR-H3": {
                "start_index": 12,
                "end_index": 20,
                "length": 9,
                "start_residue": {
                  "chain_id": "X",
                  "sequence_id": "95",
                  "insertion_code": ""
                },
                "end_residue": {
                  "chain_id": "X",
                  "sequence_id": "102",
                  "insertion_code": ""
                },
                "residue_keys": [
                  {"chain_id": "X", "sequence_id": "95", "insertion_code": ""}
                ]
              }
            }
          }
        },
        "warnings": []
      }
    }
  }
}
```

Prediction provenance (`GET /api/v1/predictions/{prediction_id}`) excerpt:

```json
{
  "provenance": {
    "descriptor_hash": "...",
    "cdr_annotation": {
      "available": true,
      "scheme": "kabat",
      "boundary_source": "numbered",
      "boundary_confidence": "high",
      "selected_heavy_chain": "X",
      "chains": {
        "X": {
          "role": "heavy",
          "confidence": "high",
          "regions": {
            "CDR-H3": {
              "start_index": 12,
              "end_index": 20,
              "length": 9
            }
          }
        }
      },
      "warnings": []
    }
  }
}
```

---

## Phase 2 — Full CDR set (H1/H2/H3/L1/L2/L3) (P1 / M)

### Milestone M2
Generalize from CDR-H3 to full heavy/light CDR regions.

### Checklist

- [x] Add light-chain role detection (kappa/lambda-friendly, role fallback `light_unknown`).
- [x] Implement full region boundary extraction for H1/H2/H3 and L1/L2/L3.
- [x] Handle insertion codes and discontinuities explicitly.
- [x] Emit region completeness score per chain.
- [x] Persist region maps and residue counts in structured metadata.

### Tests

- [x] Heavy-only antibodies (single-domain edge case).
- [x] Paired VH/VL structures.
- [x] Multi-model input and chain remapping interactions.
- [x] Missing residues / sequence gaps across region boundaries.

### Exit criteria

- [x] Full CDR map available for antibody mode when inputs permit.
- [x] Typed warnings correctly report partial/ambiguous regions.

### Implementation status notes (Phase 2, started)

- Phase 2 now includes full numbered-region extraction across heavy/light chains:
  - `CDR-H1`, `CDR-H2`, `CDR-H3`
  - `CDR-L1`, `CDR-L2`, `CDR-L3`
- Light-chain role assignment emits deterministic role values:
  - `light_kappa`
  - `light_lambda`
  - `light_unknown` (fallback)
- Region payloads remain insertion-code-aware via residue keys:
  - `(chain_id, sequence_id, insertion_code)`
- Discontinuities are reflected via partial-region extraction, reduced `completeness_score`, and typed `CDR_BOUNDARY_AMBIGUOUS` warnings.

---

## Phase 3 — CDR-aware descriptors and explainability (P1 / M)

### Milestone M3
Use CDR annotations to enrich feature summaries without destabilizing baseline behavior.

### Checklist

- [x] Add CDR-region descriptors:
  - region length
  - residue class fractions by region
  - CDR/interface overlap counts
  - optional CDR burial/contact summaries
- [x] Add explainability entries for top CDR-contributed descriptors.
- [x] Preserve deterministic hash behavior with version bump:
  - e.g., `summary_features_v3`.
- [x] Keep old fields intact for backward compatibility.

### Tests

- [x] Descriptor schema regression (old + new fields).
- [x] Explainability includes CDR fields where available.
- [x] Hash determinism for unchanged inputs.

### Implementation status notes (Phase 3, in progress)

- Added CDR-aware descriptor features to prediction feature bundles (`summary_features_v3`) including:
  - per-region lengths (`CDR-H1/H2/H3`, `CDR-L1/L2/L3`),
  - total CDR region/residue counts,
  - partner-scoped CDR residue counts,
  - CDR interface overlap proxy,
  - heavy/light completeness means.
- Existing descriptor fields remain present; CDR descriptors were added additively for compatibility.
- Added descriptor regression coverage in `tests/test_feature_extraction.py`.
- Explainability now prioritizes top non-zero `cdr_*` descriptors when available while remaining capped to a compact top-descriptor list.
- Added deterministic hash coverage for unchanged antibody descriptor inputs and response-level verification that CDR descriptors appear in antibody prediction payloads.

### Additional verification notes (Phase 2)

- Added combined stress interaction coverage in `tests/test_structure_flow.py` for:
  - multi-model input,
  - explicit chain remap,
  - sequence-gap handling,
  within a single antibody-mode upload → validate → predict flow.

### Exit criteria

- [x] CDR-aware descriptors visible in prediction responses.
- [x] Existing non-CDR flows unaffected.

---

## Phase 4 — Validation UX, health, and observability (P1 / S)

### Milestone M4
Make CDR annotation status transparent in API and frontend.

### Checklist

- [x] Add validation warnings/errors surfaced via typed issues.
- [x] Add health capability flags for annotation backend availability.
- [x] Expose concise CDR summary in frontend structure/prediction views.
- [x] Add counters/telemetry hooks:
  - `% numbering-based`
  - `% motif-fallback`
  - `% ambiguous/failed`

### Implementation status notes (Phase 4, started)

- Validation responses now surface dedicated CDR warning issues built from
  `summary.metadata["cdr_annotation"]` instead of relying only on generic summary-level warning text.
- Typed validation issue payloads currently cover:
  - `CDR_CHAIN_ROLE_AMBIGUOUS`
  - `CDR_BOUNDARY_AMBIGUOUS`
  - `CDR_MOTIF_FALLBACK_USED`
  - `CDR_NUMBERING_MISSING`
- Each typed issue carries structured details for downstream UX work, including:
  - `selected_heavy_chain`
  - `scheme`
  - `boundary_source`
  - `boundary_confidence`
  - per-chain CDR metadata snapshot
- Added integration coverage in `tests/test_structure_flow.py` for:
  - motif-fallback validation warnings,
  - partial/ambiguous boundary validation warnings.
- `/health` now exposes `capabilities.cdr_annotation` flags so clients can detect whether
  the deterministic CDR annotation backend is available, including support for:
  - numbered-boundary extraction,
  - motif fallback,
  - typed validation issue surfacing.
- Added health contract coverage in `tests/test_health.py` and updated the public API
  contract documentation in `OpenAPI_Abby_v1.yaml`.
- Frontend structure and prediction views now render a concise CDR summary card that shows:
  - annotation availability,
  - confidence and boundary source,
  - selected heavy chain,
  - chain-level region/completeness summary,
  - typed CDR warnings when present.
- `/health` now exposes in-process CDR telemetry counters and percentages for antibody-mode
  summaries, including:
  - `% numbering-based`
  - `% motif-fallback`
  - `% ambiguous/failed`
  with raw counts and total antibody summary attempts for downstream scraping or future metrics export.

### Exit criteria

- [x] Users can tell exactly why CDR annotation succeeded/failed.

---

## Phase 5 — Optional confidence baseline and drift checks (P2 / M)

### Milestone M5
Add lightweight statistical QA model inspired by classical logistic workflows.

### Checklist

- [x] Build optional boundary-confidence baseline (logistic/multinomial).
- [x] Feature set includes positional, motif, and composition signals.
- [x] Report calibration and ROC/AUC metrics.
- [x] Integrate only as QA guardrail (not mandatory inference path).

### Implementation status notes (Phase 5, started)

- Added the first lightweight QA slice for boundary-confidence/drift monitoring:
  - deterministic `quality_baseline` payload attached to CDR annotation metadata and prediction provenance,
  - heuristic score/class output (`high` / `medium` / `low`),
  - drift flags and machine-readable reason codes for fallback, ambiguity, and partial coverage.
- Upgraded the QA baseline contract from heuristic-only semantics to an explicit
  logistic/multinomial baseline profile:
  - `model_name=logistic_multinomial_v1`,
  - `model_family=multinomial_logistic_baseline`,
  - deterministic fixed-weight logistic scoring over engineered CDR signals.
- Promoted the heuristic baseline to an explicit QA model contract:
  - versioned model/contract identifiers,
  - explicit feature schema version,
  - non-blocking intended-use declaration,
  - supported prediction-mode metadata for downstream compatibility checks.
- Started calibration scaffolding as a non-runtime utility path:
  - equal-width reliability binning utilities,
  - ECE/MCE/Brier calculation,
  - optional AUC-ROC estimation when both classes are present,
  - explicit calibration scaffold metadata in the QA model contract.
- Added a tiny offline calibration runner for validation artifacts:
  - scans `validation_report.json` artifacts,
  - extracts `quality_baseline` score/observed label samples,
  - emits `cdr_quality_calibration_report.json` and `cdr_quality_calibration_bins.csv`,
  - auto-runs this export as a best-effort step at the end of the ANDD validation harness.
- The baseline is explicitly non-blocking and does not alter core annotation decisions.
- Current heuristic features include:
  - boundary source,
  - heavy-region completeness,
  - selected heavy-chain region count,
  - heavy candidate score margin,
  - motif-match count,
  - warning count / typed warning penalties.
- Added positional/composition feature signals for the baseline feature vector (`cdr_boundary_quality_features_v2`):
  - normalized CDR-H3 start position,
  - normalized CDR-H3 length,
  - CDR-H3 aromatic fraction,
  - CDR-H3 charged fraction,
  in addition to existing motif/source/completeness features.
- Drift-warning automation now emits typed warning code `CDR_BASELINE_DRIFT_FLAGGED`
  when the QA baseline indicates confidence drift conditions.

### Exit criteria

- [x] Automated drift warnings for annotation confidence drops.

---

## Phase 6 — Structural mutation stress harness for CDR loops (P2 / M)

### Milestone M6
Introduce robust mutation-parser style validation harness for CDR-local stress tests.

### Checklist

- [x] Add safe mutation spec parser for CDR-local perturbation tests.
- [x] Add residue index/range guards and clear error messages.
- [x] Batch-run stress tests and summarize pass/fail/fallback outcomes.
- [x] Keep this harness optional and off default user path.

### Implementation status notes (Phase 6, started)

- Added parser/harness scaffolding in `src/abby_api/services/cdr_stress_harness.py`:
  - point substitution spec parser (`CHAIN:SEQ[ICODE]:FROM>TO`),
  - range substitution spec parser (`CHAIN:START-END:TO`),
  - typed format/range errors for safe fail-fast behavior.
- Added explicit residue index/range guards:
  - positive index enforcement,
  - descending-range rejection,
  - bounded max-range span checks.
- Added parser-only batch runner scaffold with deterministic rollups:
  - total/parsed/failed counts,
  - per-spec status and machine-readable error text.
- Wired an optional CLI/report artifact path while keeping default flow unchanged:
  - `run_andd_validation_harness(..., cdr_stress_specs=[...])` now emits
    `reports/cdr_mutation_stress_report.json` only when specs are provided,
  - both `src/abby_api/validation_harness.py` and `scripts/run_andd_validation.py`
    expose repeatable `--cdr-stress-spec` flags.
- Added initial perturbation-resilience assertions in the stress artifact payload:
  - `nonzero_parse_success`,
  - `failure_rate_within_limit`,
  - `spec_chains_present_in_structures` (structure-aware chain coverage check),
  to begin measuring resilience trajectory toward full Phase 6 exit criteria.
- Added first mutation→annotation integration probe in
  `run_cdr_mutation_annotation_probe(...)` with regression coverage ensuring that
  a valid heavy-chain CDR-H3 point mutation still yields typed CDR annotation
  output and deterministic repeated annotation results.
- Hardened local perturbation resilience in the mutation→annotation probe:
  - malformed mutation specs are handled without crashing and emit typed issue codes,
  - local range perturbations (`CHAIN:START-END:TO`) are now applied safely,
  - mixed successful/failed perturbation batches preserve deterministic annotation
    output with explicit per-spec failure reasons.
- Harness remains intentionally parser-only and not wired into default prediction routes,
  preserving optional/off-default behavior for v1.

### Exit criteria

- [ ] CDR annotation resilient to local perturbation scenarios.

---

## 6) Data strategy and licensing checks

### Checklist

- [ ] Use OAS/paired-unpaired resources only under compatible licenses and attribution terms.
- [ ] Track source metadata in provenance:
  - dataset source
  - version/DOI
  - preprocessing method
- [ ] Add dataset schema validator for sequence-level annotation training/QA artifacts.

### Notes

- OAS provides large, annotated repertoires and filtering by attributes.
- p-IgGen Zenodo snapshot can support reproducible training/evaluation splits.

---

## 7) Testing and quality gates

For each phase touching backend logic:

- [ ] `pytest -q tests/test_structure_flow.py`
- [ ] `pytest -q tests/test_feature_extraction.py`
- [ ] `pytest -q tests/test_batch_jobs.py` (if feature payload changes)
- [ ] `pytest -q`
- [ ] `ruff check .`

If API schema/frontend payload changes:

- [ ] `frontend` dependency install with deterministic mode
- [ ] `npm run build`

Additional new tests to add:

- [ ] `tests/test_cdr_annotation.py` (unit/contract)
- [ ] `tests/test_cdr_descriptor_regression.py`
- [ ] dataset/numbering edge-case fixtures under `validation_dataset/ANDD_pdb/` extensions

---

## 8) Milestone timeline (suggested)

- **Sprint 1:** M0 + M1 (CDR-H3 MVP live)
- **Sprint 2:** M2 (full CDR regions)
- **Sprint 3:** M3 + M4 (descriptors + UX/observability)
- **Sprint 4+:** M5/M6 optional hardening

---

## 9) Definition of done (CompDetRAE)

CompDetRAE is considered complete for v1.1 when:

- [ ] CDR-H3 and full CDR region annotation works deterministically on supported antibody inputs.
- [ ] Boundary source and confidence are explicit in provenance.
- [ ] Fallback/ambiguity behavior is typed, test-covered, and user-visible.
- [ ] CDR-aware descriptors are integrated without regressions.
- [ ] Roadmap/checklist docs are synchronized.

---

## 10) Immediate execution slice (next concrete step)

1. Implement **Phase 0 contract + Phase 1 CDR-H3 MVP** in a single focused PR.
2. Add `tests/test_cdr_annotation.py` covering numbered + motif fallback + ambiguous cases.
3. Update `Dev_Plan_Implementation_Checklist.md` CDR item from `[-]` to either:
   - still `[-]` with explicit sub-checklist, or
   - `[x]` only when full Phase 1 exit criteria are met.

---

## Appendix A) RepSeq interoperability profile for CompDetRAE

This appendix captures how repertoire-sequencing guidance (RepSeq ecosystem concepts, IMGT resources, and AIRR standards framing) maps to Abby’s **v1.1 CDR structural bookkeeping** roadmap.

### A.1 Scope classification

#### Use now in v1.1 (high relevance)

- CDR anchor/boundary discipline for deterministic CDR extraction logic.
- IMGT-aligned numbering and region vocabulary for cross-tool consistency.
- Uncertainty-aware annotation semantics (confidence + ambiguity states).
- AIRR-style provenance rigor (tool/version/processing metadata).

#### Use later / optional extensions (medium relevance)

- AIRR-compliant import/export adapters for repertoire-heavy datasets.
- Sequence preprocessing adapters inspired by pRESTO/Change-O style QC pipelines.
- Cohort-level clonotype/repertoire analytics as separate, post-v1.1 modules.

#### Out of scope for v1.1 bookkeeping (low relevance)

- Epidemiology-scale diversity analytics and clinical cohort dashboards.
- Antigen-specific repertoire matching as a primary boundary detector.
- Mandatory dependence on full AIRR-seq assembly pipelines in default Abby flow.

### A.2 Contract additions (provenance + metadata)

Add the following fields to CDR metadata/provenance contracts (names may be normalized to existing schema style):

- `numbering_scheme`: `imgt | kabat | chothia | aho | motif_fallback`
- `boundary_source`: `numbered | motif_fallback | hybrid`
- `boundary_confidence`: `high | medium | low`
- `boundary_evidence`: list of machine-readable evidence tags, e.g.:
  - `numbering_interval_match`
  - `conserved_anchor_match`
  - `insertion_code_normalized`
  - `ambiguous_chain_role`
- `annotation_toolchain`:
  - `engine_name`
  - `engine_version`
  - `parameters_hash`
  - `reference_data_version` (if external numbering reference used)
- `interop_profile`: `abby_structural_v1_1` (explicitly indicates structural-first profile)

### A.3 Optional AIRR mapping (non-blocking for v1.1)

Define an optional adapter map from Abby CDR annotations to AIRR-compatible fields for exchange workflows.

Checklist:

- [ ] Add design note mapping Abby `cdr_annotation` concepts to AIRR-style annotation objects.
- [ ] Mark adapter path as optional and disabled in default prediction flow.
- [ ] Keep mmCIF-first structural extraction path authoritative when both are present.

### A.4 Verification implications

Add explicit tests to ensure RepSeq-informed metadata does not change deterministic behavior.

Checklist:

- [ ] Boundary determinism test: identical input => identical CDR boundary output and provenance hash.
- [ ] Ambiguity test: unresolved chain role sets typed warning and lowers confidence without crashing.
- [ ] Fallback test: motif fallback is recorded and never overrides numbering-derived regions.
- [ ] Schema test: required provenance fields are present when `cdr_annotation.available=true`.
- [ ] Compatibility test: legacy consumers continue to work when new fields are present.

### A.5 Non-goals guardrail

To prevent roadmap drift, this appendix does **not** authorize:

- replacing structure-driven boundary extraction with repertoire-only inference,
- requiring AIRR-seq ingestion for baseline Abby usage,
- introducing mandatory simulation dependency for CDR annotation completion.
