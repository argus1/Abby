# Abby validation plan for ANDD PDB assets

## Goal
Validate Abby end-to-end against the local ANDD corpus by:

1. taking every structure in `validation_dataset/ANDD_pdb/All_structures/*.pdb`,
2. converting each PDB into mmCIF,
3. running the converted structure through the Abby prediction pipeline, including the optional `Gromacs-CIF` handoff path where applicable,
4. and comparing Abby’s predicted values against the ground-truth binding affinities stored in `validation_dataset/ANDD_pdb/Antibody and Nanobody Design Dataset (ANDD)_v2.xlsx`.

This plan is intended to produce a repeatable validation harness for structure ingestion, preprocessing, prediction, and evaluation.

## Validation principles
- Treat `validation_dataset/ANDD_pdb/` as the canonical local regression corpus.
- Preserve structure fidelity during conversion, especially chain mapping and `_struct_conn` connectivity.
- Keep the default Abby prediction flow intact; use `Gromacs-CIF` as the mmCIF-aware simulation/topology path when the validation step needs MD-ready handoff.
- Record every intermediate artifact so results are reproducible and auditable.

## Inputs
- **Structures:** `validation_dataset/ANDD_pdb/All_structures/*.pdb`
- **Ground truth:** `validation_dataset/ANDD_pdb/Antibody and Nanobody Design Dataset (ANDD)_v2.xlsx`
- **Conversion target:** per-structure `.mmcif` files
- **Pipeline target:** Abby prediction pipeline with `Gromacs-CIF` compatibility

## Proposed workflow

### 1. Inventory the dataset
- Enumerate every `.pdb` file under `validation_dataset/ANDD_pdb/All_structures/`.
- Build a manifest containing:
  - structure filename
  - structure identifier used by the dataset
  - source path
  - converted mmCIF output path
  - validation status
- Load the spreadsheet and identify the columns that contain:
  - structure identifiers
  - experimental or ground-truth binding affinity values
  - any auxiliary metadata needed to join predictions to labels

### 2. Convert PDB to mmCIF
- Convert each PDB file to mmCIF before any downstream Abby processing.
- Prefer the repo’s mmCIF-safe conversion path and verify that the converted file is syntactically valid.
- After conversion, confirm for each structure:
  - atom/residue counts are sensible
  - chain identifiers are preserved or intentionally normalized
  - connectivity information is not lost
  - the converted file can be parsed by Abby’s ingestion layer

### 3. Run Abby preprocessing and prediction
For each converted mmCIF file:
- ingest the structure through Abby’s structure-validation path
- generate any required normalized structure or feature artifacts
- invoke the prediction pipeline
- if the pipeline requires topology or simulation-ready handoff, route the structure through the `Gromacs-CIF` path instead of vanilla GROMACS
- persist the prediction output together with provenance for the input structure and conversion step

### 4. Extract prediction values
- Collect the Abby prediction output for each structure.
- Standardize the output into a table with at least:
  - structure identifier
  - predicted binding-affinity value or score
  - prediction provenance/version
  - conversion status
  - pipeline status
- If Abby produces multiple related scores, define one primary validation target and keep the others as secondary diagnostics.

### 5. Join predictions to ground truth
- Match prediction rows to the ANDD workbook by structure identifier.
- Drop or quarantine any structure that cannot be matched unambiguously.
- Maintain a failure log for:
  - missing spreadsheet entries
  - duplicate IDs
  - conversion failures
  - pipeline failures
  - structures with unusable labels

### 6. Compare Abby outputs to ground truth
Evaluate Abby predictions against the experimental binding affinity values using both error and ranking metrics.

Recommended metrics:
- Pearson correlation
- Spearman correlation
- mean absolute error
- root mean squared error
- optional calibration plots or residual analysis if score scaling is stable

Also inspect:
- whether the model preserves ranking of strong vs weak binders
- whether specific structure families systematically underperform
- whether conversion or topology handoff failures correlate with prediction quality

### 7. Summarize results
Produce a validation report containing:
- number of PDB files discovered
- number successfully converted to mmCIF
- number successfully processed through Abby
- number successfully matched to ground truth
- aggregate metric values
- list of failed or excluded structures with reasons
- any reproducibility notes about the conversion and `Gromacs-CIF` path

## Acceptance criteria
This validation pass is successful if:
- every eligible PDB in `All_structures/*.pdb` is converted to mmCIF or explicitly explained if excluded
- Abby can ingest the converted mmCIF files without silent structural loss
- `Gromacs-CIF` can be used wherever mmCIF-aware topology generation is required
- predictions can be aligned to the ANDD workbook labels
- comparison metrics can be produced from the joined prediction/ground-truth table
- all exceptions are logged with actionable reasons

## Recommended implementation notes
- Keep the conversion step separate from prediction so failures are easy to isolate.
- Store converted mmCIF files in a dedicated validation output directory.
- Use stable structure IDs from the ANDD workbook rather than filenames alone when joining to labels.
- Prefer deterministic batching so repeated validation runs are comparable.
- Keep the plan compatible with future automated regression tests.

## Suggested output artifacts
- `validation_manifest.csv`
- converted mmCIF files per structure
- Abby prediction outputs per structure
- joined prediction-vs-label table
- final metrics summary
- failure log

## Follow-up work
If this plan is adopted, the next practical step is to turn it into an executable validation harness and add regression tests that assert:
- PDB → mmCIF conversion succeeds for the ANDD corpus
- Abby predictions are emitted for each successfully processed structure
- the prediction/label join uses the ANDD workbook consistently
- the comparison report is reproducible across runs
