# Abby Service-Layer Reuse Plan

This document translates the earlier overlap analysis between Abby and [Prodigy](https://github.com/haddocking/prodigy) into a concrete implementation plan for Abby's backend service layer.

It is intended to complement the existing Abby planning documents:

* [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md) for product behavior and user-visible outputs
* [`Backend_Architecture_Abby.md`](./Backend_Architecture_Abby.md) for service boundaries and deployment responsibilities
* [`Dev_Plan.md`](./Dev_Plan.md) for end-to-end system direction
* [`Dev_Plan_Biopython.md`](./Dev_Plan_Biopython.md) for BioPython-driven parsing and feature extraction
* [`OpenAPI_Abby_v1.yaml`](./OpenAPI_Abby_v1.yaml) for API contract expectations

The goal is **not** to turn Abby into a clone of Prodigy. The goal is to borrow the most useful structural-analysis ideas and rebuild them inside Abby's API-first, async, provenance-oriented architecture.

## 1. What Abby should borrow from Prodigy

Prodigy is most useful to Abby as a reference implementation for the **deterministic structural feature pipeline** that sits between file ingestion and model inference.

The strongest reuse candidates are:

1. **Structure parsing and validation patterns**
   * PDB/mmCIF parser selection
   * cleanup of hydrogen atoms, solvent, and unsupported records
   * chain-presence validation for user selections
   * multi-model consistency checks
   * gap and discontinuity warnings
   * dataset-backed regression checks using `validation_dataset/ANDD_pdb/` so parser and validation changes stay anchored to real local fixtures
   * PDB→mmCIF conversion checks for the validation dataset before the structure is handed to downstream services or exports

2. **Chain selection semantics**
   * grouping multiple chains into one binding partner
   * validating that selected groups are disjoint
   * constraining contact calculation to partner-vs-partner interactions

3. **Intermolecular contact detection**
   * residue-residue contact discovery via BioPython neighbor search
   * configurable contact cutoff
   * deterministic contact list generation for downstream reuse

4. **Residue-class contact binning**
   * charged / polar / apolar contact categories
   * hydrophobic / hydrophilic contact categories
   * interface composition summaries suitable for explainability

5. **Surface accessibility and NIS-style composition features**
   * per-residue relative solvent accessibility
   * classification of accessible residues into surface-composition buckets
   * reusable descriptor generation from SASA / RSA data

6. **Affinity unit conversion helpers**
   * converting predicted $\Delta G$ to $K_d$
   * temperature-aware output derivations

7. **Scientist-friendly exports**
   * contact lists
   * interface highlighting artifacts such as PyMOL selection scripts
   * concise, provenance-linked prediction summaries

## 2. What Abby should not borrow as-is

The following Prodigy elements are useful as inspiration, but should not be adopted directly as Abby architecture:

* **CLI-first execution flow** — Abby is service-oriented, not terminal-oriented.
* **stdout-centric reporting** — Abby should emit typed schemas and persisted artifacts.
* **hard-coded single-model worldview** — Abby's product spec expects multiple model families, consensus, and uncertainty.
* **direct process-pool orchestration in the predictor layer** — Abby already separates API handling from worker execution.
* **tight coupling between parsing, feature extraction, scoring, and formatting** — Abby should keep these concerns in separate services.

## 3. Service-layer target design for Abby

Abby should reimplement the borrowable Prodigy logic as internal service-layer components with clear handoffs.

```text
Upload / API Request
    |
    v
Structure Ingestion Service
    |
    v
Structure Validation + Normalization Service
    |
    v
Interface Feature Extraction Service
    |
    +--> Contact Features
    +--> Surface Accessibility Features
    +--> Chain/Partner Metadata
    |
    v
Prediction Service
    |
    +--> Baseline Linear Model(s)
    +--> Future ML / Ensemble Models
    |
    v
Consensus + Explainability Service
    |
    v
Result Persistence + Export Artifacts
```

This decomposition preserves the useful scientific logic while keeping Abby aligned with its backend architecture.

## 4. Recommended file-level implementation map

The current Abby codebase already has the right high-level folders, so the reuse plan should fit into the existing package layout.

### 4.1 `src/abby_api/services/structures.py`

This file should become the home for **structure ingestion, validation coordination, and chain mapping checks**.

Use `validation_dataset/ANDD_pdb/` as the canonical local regression corpus for chain mapping, mmCIF conversion, validation output, and export behavior.

Recommended responsibilities:

* detect input format from filename and, later, content sniffing
* dispatch to `PDBParser` or `MMCIFParser`
* validate presence of requested partner chains
* validate that `partner_1` and `partner_2` are both non-empty and disjoint
* normalize chain grouping semantics for antibody heavy/light chains
* emit warnings for:
  * missing chain IDs
  * multiple models
  * gaps / fragmented peptides
  * unsupported residues
  * mmCIF/PDB inconsistencies

Recommended additions:

* `parse_structure_file(...)`
* `validate_partner_mapping(...)`
* `normalize_chain_groups(...)`
* `summarize_structure(...)`

### 4.2 `src/abby_api/services/predictions.py`

This file should remain the orchestration layer, but it should stop being a placeholder and start calling internal feature-generation utilities.

Recommended responsibilities:

* load a normalized structure representation
* call feature extraction routines
* run one or more baseline predictors
* convert model outputs into Abby's result schema
* record provenance:
  * cutoff values
  * preprocessing version
  * model version
  * descriptor hash

Recommended additions:

* `build_descriptor_bundle(...)`
* `run_baseline_affinity_models(...)`
* `derive_thermodynamic_outputs(...)`
* `assemble_prediction_result(...)`

### 4.3 `src/abby_api/services/system.py`

Use this layer to expose internal capability metadata when helpful.

Possible future responsibilities:

* reveal model bundle version
* reveal preprocessing version
* reveal enabled descriptor families
* health check availability of optional structure-analysis dependencies such as `freesasa`

### 4.4 New internal module: `src/abby_api/services/feature_extraction.py`

This should be added as the main reusable feature-generation unit.

Recommended responsibilities:

* intermolecular contact discovery
* contact bin aggregation
* surface accessibility feature generation
* interface composition summaries
* explainability descriptor packaging

Recommended functions:

* `calculate_inter_partner_contacts(...)`
* `classify_contact_bins(...)`
* `calculate_relative_accessibility(...)`
* `classify_surface_composition(...)`
* `make_explainability_summary(...)`

### 4.5 New internal module: `src/abby_api/services/baseline_models.py`

This module should contain deterministic baseline scoring logic inspired by Prodigy-style linear models.

Recommended responsibilities:

* implement Abby baseline formulas cleanly and transparently
* isolate coefficient definitions from orchestration code
* support versioning of baseline model families

Recommended functions:

* `score_ic_nis_baseline(...)`
* `score_surface_only_baseline(...)`
* `delta_g_to_kd(...)`
* `kd_to_delta_g(...)` (optional for future reverse conversions)

### 4.6 New internal module: `src/abby_api/services/structure_parsing.py`

If `services/structures.py` begins to grow too large, extract parser-specific logic into a dedicated utility module.

Recommended responsibilities:

* parser selection
* model cleanup
* atom/residue normalization
* optional mmCIF relational dictionary extraction

This module is especially useful if Abby later needs to preserve mmCIF-only connectivity information such as disulfides or glycan links.

### 4.7 New internal module: `src/abby_api/services/exports.py`

This module should package scientist-facing artifacts.

Recommended responsibilities:

* write contact list artifact
* create PyMOL selection script
* serialize descriptor bundle snapshot
* generate CSV/JSON export payloads

## 5. Proposed implementation phases

### Phase 1 — Make Abby's structure service scientifically useful

Objective:
Turn the current lightweight validation placeholder into a real parser-and-validator layer.

Work items:

* add BioPython dependency if not already present in the active implementation branch
* implement parser selection for PDB and mmCIF
* validate chain groups and partner mappings
* create normalized internal structure summary
* return warnings and errors in Abby schema form instead of plain strings where possible

Success criteria:

* Abby can ingest a real PDB or mmCIF file and produce validated chain metadata
* antibody heavy/light chain grouping is represented explicitly
* malformed chain mappings fail deterministically

### Phase 2 — Add contact and surface feature extraction

Objective:
Recreate the most valuable deterministic structural descriptors from the overlap analysis.

Work items:

* compute inter-partner residue contacts with configurable cutoff
* classify contacts into composition bins
* integrate relative solvent accessibility calculation
* generate NIS-style composition percentages
* persist descriptor hashes for provenance

Success criteria:

* Abby can produce a stable descriptor bundle from the same structure input
* descriptor outputs are suitable for both explainability and baseline prediction
* repeated runs on the same normalized input yield identical descriptor hashes

### Phase 3 — Add baseline affinity scoring

Objective:
Provide a scientifically grounded baseline predictor before introducing richer model families.

Work items:

* implement a deterministic linear baseline using contact and surface descriptors
* derive $\Delta G$, $K_d$, and log-scale outputs consistently
* record model version and descriptor version in provenance
* expose per-model output through Abby result schemas

Success criteria:

* Abby produces a real, non-placeholder prediction from computed descriptors
* results include provenance and derived thermodynamic values
* baseline model outputs are benchmarkable against known examples

### Phase 4 — Add explainability and export artifacts

Objective:
Turn descriptors into user-facing scientific value.

Work items:

* map descriptor bins into explainability summaries
* emit top-contributing descriptor list
* generate contact-list and PyMOL-style artifacts
* wire exports into prediction result retrieval and batch result download

Success criteria:

* Abby results are interpretable rather than scalar-only
* exported artifacts support scientist workflows and notebook analysis

### Phase 5 — Add consensus and model-family expansion

Objective:
Move beyond a single baseline model without discarding the deterministic service layer.

Work items:

* keep deterministic feature generation fixed and versioned
* add random forest / neural / mixed models on top of the same descriptor bundle
* compute consensus output and calibrated intervals
* add out-of-distribution checks

Success criteria:

* baseline and advanced models consume the same feature bundle
* Abby can compare per-model and consensus results cleanly

## 6. Data-model implications for Abby schemas

The reuse plan suggests a few schema-level enrichments.

### Structures

`StructureValidationResult` should eventually support:

* normalized chain groups
* number of models
* residue counts per partner
* warnings as typed codes, not only free-text strings
* structure-level issues such as:
  * `MISSING_CHAIN_ID`
  * `MULTI_MODEL_INPUT`
  * `UNSUPPORTED_RESIDUE`
  * `CHAIN_GROUP_OVERLAP`

### Predictions

`PredictionResult` should eventually support:

* descriptor family version
* distance cutoff and accessibility threshold in provenance
* baseline feature summaries such as contact bins and NIS percentages
* artifact references for contact lists and visualization scripts

### Explainability

The current explainability section can be grounded using descriptors such as:

* charged-charged contact count
* charged-polar contact count
* apolar-apolar contact count
* apolar surface fraction
* charged surface fraction
* interface residue count

## 7. Dependency recommendations

To support this plan, Abby should likely add or confirm the following scientific dependencies:

* `biopython` — parser, structure traversal, neighbor search
* `freesasa` — relative accessibility / surface calculations
* optional later:
  * `numpy`
  * `scikit-learn`
  * `pandas`
  * `MDAnalysis`

If `freesasa` is not available in every runtime environment, Abby should:

* detect its availability at startup or task runtime
* fail gracefully with actionable error messages
* optionally mark accessibility-based features as unavailable rather than crashing unrelated endpoints

## 8. Testing plan

Abby should adopt the spirit of Prodigy's test strategy, but mapped to API service boundaries.

Recommended test layers:

1. **Unit tests**
   * parser selection
   * chain group validation
   * contact bin classification
   * thermodynamic conversion helpers

2. **Fixture-based structure tests**
   * known PDB example
   * known mmCIF example
   * antibody-antigen chain grouping case
   * multi-model consistency case

3. **Service integration tests**
   * upload -> validate -> predict flow
   * prediction artifacts generated correctly
   * batch workflow preserves provenance and result determinism

4. **Regression tests**
   * frozen descriptor bundles for known structures
   * stable baseline output against curated examples

## 9. Recommended near-term code changes

The most efficient next implementation slice is:

1. strengthen `services/structures.py`
2. add `services/feature_extraction.py`
3. add `services/baseline_models.py`
4. refactor `services/predictions.py` to call real feature and model logic
5. add tests covering one real structure fixture end to end

This slice would turn Abby from a backend scaffold into a scientifically meaningful prototype while preserving the flexibility to add richer models later.

## 10. Licensing and reuse note

Prodigy is distributed under the Apache 2.0 license. That makes code reuse possible in principle, but Abby should still prefer **clean integration of ideas and service patterns** over copying implementation details blindly.

Recommended approach:

* reuse the **conceptual pipeline** directly
* reimplement helper logic in Abby's coding style and schema conventions
* preserve attribution and license obligations if any source code is copied or adapted
* keep Abby-specific abstractions, naming, and result schemas primary

## 11. Final recommendation

Abby should use Prodigy as a **service-layer reference model** for deterministic structure analytics, not as a full product template.

The best path forward is:

* borrow the structural science layer
* keep Abby's API/job/provenance architecture
* treat linear contact/surface scoring as a baseline model family
* build consensus, uncertainty, and richer model orchestration on top of that stable feature substrate

That gives Abby a faster route to a credible v1 while preserving room for more advanced modeling later.