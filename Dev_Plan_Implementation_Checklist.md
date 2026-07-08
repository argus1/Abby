# Abby Execution Roadmap Checklist

This document is a complementary execution roadmap for [`Dev_Plan.md`](./Dev_Plan.md) and [`Dev_Plan_Biopython.md`](./Dev_Plan_Biopython.md).

It keeps the **checklist format as the progress metric**, but reorganizes the plan into sequenced delivery phases so the team can use it both as an audit and as an implementation roadmap.

Audit baseline: **2026-07-07**

## Status legend

- `[x]` Completed in the current codebase
- `[-]` Partially implemented / scaffolded / visible but incomplete
- `[ ]` Not started

## Planning legend

- `P0` = critical path / do next
- `P1` = high priority / near-term
- `P2` = useful follow-on
- `P3` = strategic / later
- `S` = small effort
- `M` = medium effort
- `L` = large effort
- Combined format uses `Priority / Effort`, for example `P1 / M`

## How to use this roadmap

- Treat each phase as an execution slice.
- Do work top-down unless a dependency explicitly allows parallelism.
- Keep checklist status current as implementation lands.
- Prefer moving items from `[ ]` to `[-]` only when code exists behind a stable contract.
- Move items to `[x]` only when implementation and verification both exist.

---

## Phase 0 — Current baseline and audit snapshot

### Already in place
| Status | Priority / Effort | Item | Evidence |
| --- | --- | --- | --- |
| `[x]` | `P0 / S` | Project creation flow exists | `src/abby_api/services/projects.py`, `frontend/src/pages/ProjectPage.tsx` |
| `[x]` | `P0 / M` | Structure upload, parsing, summary generation, and validation exist | `src/abby_api/services/structures.py`, `src/abby_api/services/structure_parsing.py` |
| `[x]` | `P0 / S` | Typed validation diagnostics exist | `src/abby_api/schemas/structures.py` |
| `[x]` | `P0 / M` | Contact-based descriptor extraction exists | `src/abby_api/services/feature_extraction.py` |
| `[x]` | `P0 / M` | True SASA path exists when BioPython is available | `calculate_solvent_accessibility()` in `src/abby_api/services/feature_extraction.py` |
| `[x]` | `P0 / S` | Deterministic baseline scoring exists | `src/abby_api/services/baseline_models.py` |
| `[x]` | `P0 / S` | Provenance-backed prediction responses exist | `src/abby_api/services/predictions.py`, `src/abby_api/schemas/common.py` |
| `[x]` | `P1 / S` | Frontend prediction, comparison, and batch visibility for cutoff provenance exists | `frontend/src/pages/PredictionPage.tsx`, `frontend/src/pages/ComparePage.tsx`, `frontend/src/pages/BatchJobPage.tsx` |

### Baseline gaps blocking later phases
| Status | Priority / Effort | Item | Evidence |
| --- | --- | --- | --- |
| `[-]` | `P0 / M` | Basic `mmCIF` ingestion exists with initial relational chemistry preservation | parser dispatch plus `MMCIF2Dict` / `_struct_conn` extraction now implemented; broader chemistry coverage remains to expand |
| `[-]` | `P0 / M` | Worker entry points exist, but no real async execution backend exists | `src/abby_api/workers/tasks.py` |
| `[-]` | `P0 / M` | Batch routes exist, but batch result production/export is still stubbed | `src/abby_api/services/batch_jobs.py` |

---

## Phase 1 — Finish the structural ingestion foundation

**Goal:** make Abby structurally trustworthy for `mmCIF`-first workflows and MD handoff preparation.

**Why this phase comes first:** everything downstream depends on preserving the right structure semantics instead of flattening them away. Chemistry is fussy; if we lose it here, later models are just confidently wrong.

### 1A. mmCIF chemistry preservation
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[x]` | `P0 / M` | Add `MMCIF2Dict` parsing alongside existing `MMCIFParser` support | `src/abby_api/services/structure_parsing.py`; depends on BioPython availability |
| `[x]` | `P0 / M` | Extract `_struct_conn` records for disulfides and other covalent links | `src/abby_api/services/structure_parsing.py` |
| `[x]` | `P0 / M` | Preserve glycan/disulfide connectivity in normalized structure metadata | `src/abby_api/services/structure_parsing.py`, `src/abby_api/services/structures.py` |
| `[x]` | `P1 / M` | Return connectivity findings in structure detail responses | `src/abby_api/api/routes/structures.py`, `src/abby_api/services/structures.py` |
| `[x]` | `P0 / S` | Add tests covering `mmCIF` connectivity preservation | `tests/test_structure_flow.py` |

### 1B. Validation and normalization hardening
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[-]` | `P0 / S` | Add gap / fragmented-peptide detection | Planned but not implemented |
| `[ ]` | `P1 / M` | Add MD-handoff-oriented chain normalization or canonical chain remapping | Current chain grouping is not yet MD-tool aware |
| `[ ]` | `P1 / M` | Add `pdb2gmx`-oriented cleanup warnings or preflight checks | Unsupported residue naming, chain artifact issues, missing topology-critical atoms |
| `[ ]` | `P2 / S` | Expose richer warning details in the structure frontend | `frontend/src/pages/StructurePage.tsx` |

### Phase 1 exit criteria
| Status | Priority / Effort | Exit criterion |
| --- | --- | --- |
| `[x]` | `P0 / M` | A representative `mmCIF` file can be uploaded and inspected without losing disulfide/glycan linkage information |
| `[x]` | `P0 / M` | Structure detail responses include preserved connectivity metadata |
| `[-]` | `P0 / S` | Validation test coverage includes `mmCIF`-specific cases and gap detection |

---

## Phase 2 — Complete the operational prediction workflow

**Goal:** finish the backend workflows that users already expect from the UI.

**Why this phase comes second:** the frontend is already hinting at a fuller system; this phase reduces the gap between visible product behavior and actual backend execution.

### 2A. Batch execution
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P0 / M` | Convert batch jobs from queued placeholders into real prediction fan-out | `src/abby_api/services/batch_jobs.py`, `src/abby_api/workers/tasks.py` |
| `[ ]` | `P0 / S` | Attach prediction IDs and statuses to batch items | Batch schemas/services/repository memory store |
| `[ ]` | `P0 / M` | Populate `get_results()` with real completed prediction outputs | `src/abby_api/services/batch_jobs.py` |
| `[-]` | `P0 / M` | Batch export route exists, but must generate real artifacts | Current state: synthetic download URL only |
| `[ ]` | `P0 / M` | Persist export bundles to object storage and return stable download metadata | `src/abby_api/storage/object_store.py`, `src/abby_api/services/batch_jobs.py` |
| `[ ]` | `P1 / S` | Add backend tests covering end-to-end batch execution and export generation | `tests/` |

### 2B. Worker/runtime reality
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[-]` | `P0 / S` | Placeholder worker entry points exist | `src/abby_api/workers/tasks.py` |
| `[ ]` | `P0 / L` | Bind worker tasks to a real async backend | Celery/RQ/Arq/etc. still to be chosen/implemented |
| `[ ]` | `P1 / M` | Add status transitions and failure capture for long-running tasks | Batch/prediction services and schemas |
| `[ ]` | `P2 / S` | Add health visibility for optional scientific/runtime dependencies | `src/abby_api/services/system.py` |

### 2C. Frontend alignment cleanup
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[-]` | `P1 / S` | Batch page is wired for richer data than backend currently supplies | `frontend/src/pages/BatchJobPage.tsx` |
| `[ ]` | `P1 / S` | Remove or rewrite outdated “planned/stubbed” frontend copy where backend support now exists | `frontend/src/lib/stub-data.ts` |
| `[ ]` | `P2 / S` | Optionally expose `contact_distance_cutoff_angstrom` as a project-page input | `frontend/src/pages/ProjectPage.tsx` |

### Phase 2 exit criteria
| Status | Priority / Effort | Exit criterion |
| --- | --- | --- |
| `[ ]` | `P0 / M` | A submitted batch job produces real prediction results |
| `[ ]` | `P0 / M` | Batch exports produce real persisted artifacts |
| `[ ]` | `P0 / M` | Worker-backed tasks report queued/running/completed/failed accurately |
| `[ ]` | `P1 / S` | Frontend workflow copy matches actual backend capability |

---

## Phase 3 — Expand structural descriptors beyond the current baseline

**Goal:** improve model inputs using the next most practical Biopython-derived features.

**Why this phase comes third:** these features strengthen prediction quality without yet forcing full simulation orchestration.

### 3A. Next descriptor tranche
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P1 / M` | Add residue depth extraction via `Bio.PDB.ResidueDepth` | `src/abby_api/services/feature_extraction.py` |
| `[ ]` | `P1 / M` | Add interface-burial features derived from residue depth | Descriptor bundle schema and explainability summary |
| `[ ]` | `P2 / M` | Add radius-of-gyration or other compact MD-adjacent structural summary only if computable from static structure inputs | Avoid overpromising simulation-derived descriptors before Phase 4 |
| `[ ]` | `P1 / S` | Add tests for new descriptor determinism and provenance threading | `tests/test_structure_flow.py`, `tests/test_baseline_models.py` |

### 3B. Domain-specific structural feature ideas
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P2 / M` | Add CDR-aware structural bookkeeping if antibody-specific mode needs it | No CDR extraction exists today |
| `[ ]` | `P2 / M` | Add electrostatics / surface pKa integration hooks for future PlayMolecule-style enrichment | Contract/hook only is sufficient in this phase if implementation is deferred |

### Phase 3 exit criteria
| Status | Priority / Effort | Exit criterion |
| --- | --- | --- |
| `[ ]` | `P1 / M` | Prediction descriptors include at least one new non-contact, non-SASA structural feature family |
| `[ ]` | `P1 / S` | New descriptor fields are included in explainability and provenance-sensitive tests |

---

## Phase 4 — Define the MD-ready contract before full simulation execution

**Goal:** build the metadata and artifact interfaces needed for future simulation support without making GROMACS a hard dependency of the core app.

**Why this phase comes before simulation execution:** clean handoff contracts are cheaper to define now than to reverse-engineer after a simulation worker appears.

### 4A. MD handoff schema and artifact design
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[-]` | `P1 / S` | Some provenance exists today, but not simulation provenance | Model bundle version, preprocess version, descriptor hash, contact cutoff |
| `[ ]` | `P1 / M` | Add topology-handoff metadata schema | Suggested fields: normalized chain map, preserved connectivity, non-standard residues, preprocessing warnings |
| `[ ]` | `P1 / M` | Add simulation provenance schema placeholders | Suggested fields: force field, water model, ionization, minimization protocol, seed, engine version |
| `[ ]` | `P1 / M` | Add artifact contracts for normalized structures, topology references, and imported trajectory summaries | Storage layer + prediction/batch artifact registry |

### 4B. External simulation import path
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P1 / M` | Support importing externally generated GROMACS outputs and summaries | Align with v1/v1.1 boundary in `Dev_Plan_Biopython.md` |
| `[ ]` | `P1 / M` | Add parsing/storage for trajectory-summary artifacts without requiring local simulation execution | Import path only |
| `[ ]` | `P1 / S` | Add tests for imported simulation artifact provenance | Verification for imported artifacts |

### Phase 4 exit criteria
| Status | Priority / Effort | Exit criterion |
| --- | --- | --- |
| `[ ]` | `P1 / M` | Abby can store MD-ready handoff metadata for a validated structure |
| `[ ]` | `P1 / M` | Abby can import external simulation summary artifacts under a stable schema |

---

## Phase 5 — Optional simulation backend execution

**Goal:** enable simulation-backed descriptors through an isolated optional runtime.

**Why this phase is later:** simulation is expensive, dependency-heavy, and should not destabilize the core upload/predict path.

### 5A. Simulation worker enablement
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P2 / L` | Introduce a dedicated simulation worker runtime/profile | Isolated optional runtime |
| `[ ]` | `P2 / L` | Implement optional GROMACS execution path | Keep off critical path for default prediction flow |
| `[ ]` | `P2 / L` | Add parameterization workflow hooks for non-standard residues/linkers | AMBER/Antechamber/LigParGen-style support |
| `[ ]` | `P2 / M` | Capture run-time simulation provenance and store outputs in object storage | Provenance + artifact persistence |

### 5B. Trajectory-aware aggregation
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P2 / L` | Integrate `MDAnalysis` for trajectory traversal and aggregation | Trajectory-aware processing |
| `[ ]` | `P2 / M` | Derive averaged or ensemble structural summaries from trajectory frames | Simulation summary generation |
| `[ ]` | `P2 / M` | Thread simulation-derived summaries into descriptor generation | Descriptor enrichment |

### Phase 5 exit criteria
| Status | Priority / Effort | Exit criterion |
| --- | --- | --- |
| `[ ]` | `P2 / L` | A user can request an optional simulation-backed workflow without affecting default prediction behavior |
| `[ ]` | `P2 / M` | Simulation outputs are reproducible through persisted provenance and stored artifacts |

---

## Phase 6 — Advanced model expansion

**Goal:** move beyond deterministic baselines into learned structural modeling.

**Why this phase is last:** better learned models need the strongest possible structure, provenance, and artifact foundations underneath them.

### 6A. Learned structural modeling hooks
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P3 / L` | Define graph construction for structure-derived learned models | Learned-structure input contract |
| `[ ]` | `P3 / L` | Add GNN integration path for DeepFRI / ProteinMPNN-style workflows | Model integration layer |
| `[ ]` | `P3 / L` | Add training/evaluation/calibration pipeline contracts for SPR-grounded model work | Training/evaluation infrastructure |

### 6B. Upstream structure-generation integrations
| Status | Priority / Effort | Item | Target area / notes |
| --- | --- | --- | --- |
| `[ ]` | `P3 / L` | Add AlphaFold 3 / Boltz-1 ingestion/orchestration contract | External structure-generation contract |
| `[ ]` | `P3 / L` | Add Rosetta integration contract for physical refinement / clash / `ΔΔG` workflows | Physical refinement integration |

### Phase 6 exit criteria
| Status | Priority / Effort | Exit criterion |
| --- | --- | --- |
| `[ ]` | `P3 / L` | Abby supports at least one non-baseline learned structural inference path under explicit provenance |
| `[ ]` | `P3 / M` | External structure-generation or refinement tools can feed Abby through stable contracts |

---

## Cross-cutting verification checklist

These should be advanced throughout the roadmap rather than left until the end.

- `[x]` Health/API smoke tests exist
  - Evidence: `tests/test_health.py`
- `[x]` Structure upload/validate/predict integration tests exist
  - Evidence: `tests/test_structure_flow.py`
- `[x]` Deterministic descriptor hash behavior is tested
  - Evidence: existing structure flow tests
- `[x]` Configurable contact cutoff behavior is tested
  - Evidence: existing structure flow tests

| Status | Priority / Effort | Verification item |
| --- | --- | --- |
| `[ ]` | `P0 / S` | Add `mmCIF` integration tests with relational connectivity assertions |
| `[ ]` | `P0 / S` | Add batch execution tests with real results and exports |
| `[ ]` | `P1 / S` | Add residue-depth / new-descriptor verification tests as Phase 3 lands |
| `[ ]` | `P1 / S` | Add imported-simulation artifact tests as Phase 4 lands |
| `[ ]` | `P2 / M` | Add simulation worker / trajectory tests as Phase 5 lands |
| `[ ]` | `P3 / M` | Add learned-model provenance and regression tests as Phase 6 lands |

---

## Recommended immediate order of attack

If you want the highest leverage next steps, this is the shortest sensible path:

| Status | Priority / Effort | Next step |
| --- | --- | --- |
| `[x]` | `P0 / M` | Implement `MMCIF2Dict` + `_struct_conn` preservation |
| `[ ]` | `P0 / S` | Add gap detection and MD-oriented validation preflight checks |
| `[ ]` | `P0 / M` | Make batch jobs execute real predictions and emit real exports |
| `[ ]` | `P1 / M` | Add residue-depth descriptors |
| `[ ]` | `P1 / M` | Define MD handoff + simulation provenance schema |

---

## Concise program readout

### Strong today
| Status | Priority / Effort | Capability |
| --- | --- | --- |
| `[x]` | `P0 / S` | Single-structure prediction workflow |
| `[x]` | `P0 / S` | Contact and SASA descriptors |
| `[x]` | `P0 / S` | Baseline scoring and provenance |
| `[x]` | `P1 / S` | Frontend visibility for prediction and cutoff auditing |

### Needs finishing next
| Status | Priority / Effort | Capability gap |
| --- | --- | --- |
| `[-]` | `P0 / M` | `mmCIF` chemistry preservation |
| `[-]` | `P0 / M` | Batch execution and export realism |
| `[-]` | `P0 / L` | Worker-backed async orchestration |
| `[-]` | `P1 / S` | Frontend/backend capability alignment |

### Strategic later work
| Status | Priority / Effort | Strategic item |
| --- | --- | --- |
| `[ ]` | `P1 / M` | MD-ready handoff and import contracts |
| `[ ]` | `P2 / L` | Optional GROMACS / MDAnalysis execution |
| `[ ]` | `P3 / L` | Learned structural model expansion |
