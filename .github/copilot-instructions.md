# Abby Copilot Instructions (Overnight Cloud Agent Workflow)

This file defines how autonomous coding agents should operate in the Abby repository during unattended/overnight runs.

Primary planning references:

- `Dev_Plan.md` (system strategy)
- `Dev_Plan_Biopython.md` (structure + feature implementation path)
- `Dev_Plan_Implementation_Checklist.md` (phase-ordered execution roadmap)

## Mission and scope

The project is **mmCIF-first** and **structure-integrity-first**.

Agents should prioritize work that improves or preserves:

1. PDBx/mmCIF parsing fidelity (especially `_struct_conn` preservation)
2. Deterministic structure validation and feature extraction behavior
3. Provenance and artifact contracts for predictions/batches
4. Optional (not mandatory) simulation-readiness boundaries

For Abby v1, keep GROMACS integration optional in user-facing flow, but preserve MD-ready handoff metadata.

## Environment baseline (must treat as true unless explicitly changed)

- The repo uses **mmCIF-compatible GROMACS** via [`argus1/Gromacs-CIF`](https://github.com/argus1/Gromacs-CIF).
- `Gromacs-CIF` is already installed on the local machine used for this repo.
- Focus overnight work on orchestration, validation, provenance, and contracts (not base GROMACS installation).

## Canonical data and regression corpus

Use `validation_dataset/ANDD_pdb/` as the canonical local regression corpus for ingestion, conversion, validation, and export checks.

When changing parsing/validation/feature/batch logic:

- Re-run relevant tests against this corpus.
- Ensure PDB→mmCIF conversion assumptions remain valid.
- Preserve chain mapping + connectivity semantics.

## Priority policy for unattended runs

When selecting work, follow this order:

1. **P0/P1 unfinished items** in `Dev_Plan_Implementation_Checklist.md`
2. Dependencies that unblock those items
3. Test coverage gaps tied to changed code
4. Documentation alignment across the three dev plans

Avoid jumping to Phase 5/6 work unless explicitly requested.

## Current unfinished checklist targets (must be treated as active)

From the current roadmap snapshot, the highest-value unfinished/partial items are:

- `P1 / S`: complete simulation provenance parity (move `Some provenance exists today, but not simulation provenance` from `[-]` to `[x]` with verification evidence)
- `P2 / M`: complete CDR-aware structural bookkeeping (`[-]` item in Phase 3B)
- `P3 / L`: all Phase 6 model-expansion items (graph contracts, GNN integration path, training/eval contracts)
- `P3 / M`: learned-model provenance + regression tests in cross-cutting verification

If no explicit task is provided, pick the smallest safe slice from the list above and finish it with tests.

## Overnight execution slices (recommended)

Use small, verifiable slices that can be completed safely in sequence:

1. Pick one checklist item (or one tightly coupled pair).
2. Implement minimal code changes.
3. Add/adjust tests for changed behavior.
4. Run backend test subset first; expand only if needed.
5. Update docs/checklist status if behavior materially changed.
6. Produce a concise handoff summary (see required output section).

## Required quality gates before finishing a run

At minimum, agents should run the checks relevant to files changed.

### Backend

- `pytest -q`

If only targeted areas changed, run focused tests first, then broaden as needed:

- `pytest -q tests/test_structure_flow.py`
- `pytest -q tests/test_batch_jobs.py`
- `pytest -q tests/test_worker_backend.py`
- `pytest -q tests/test_health.py`

### Lint (Python)

- `ruff check .`

### Frontend (when frontend files are modified)

From `frontend/`:

- `npm run build`

Additionally, run frontend build when any of these backend/shared files change:

- `src/abby_api/schemas/**`
- `src/abby_api/api/routes/**`
- `OpenAPI_Abby_v1.yaml`
- `frontend/src/types/api.ts`

Do not claim completion if relevant checks are failing.

## Frontend CI reliability policy (mandatory)

To reduce overnight false-success runs that later fail in CI:

1. Install frontend dependencies with deterministic lockfile mode: `npm ci --no-audit --no-fund`.
2. Run `npm run build` before final handoff whenever frontend or shared API contracts are touched.
3. If build fails due to type drift between backend schemas and frontend request/response types, update frontend types in the same run.
4. Do not stop after backend tests pass if frontend checks are still pending.

Treat frontend type/build failures as release-blocking for unattended runs.

## Dependency bootstrap policy for cloud agent environments

At the start of each unattended run, bootstrap dependencies before coding:

- Backend: `python -m pip install --upgrade pip` then `pip install -e ".[dev]"`
- Frontend: `cd frontend && npm ci --no-audit --no-fund`
- Optional scientific packages (best effort): `pip install gemmi mdanalysis freesasa`

If optional packages fail to install, continue with graceful-degradation paths and document the missing dependency in the handoff report.

## Self-healing CI loop (automated)

This repository includes an automated self-healing loop:

- Workflow: `.github/workflows/self-healing-ci.yml`
- Script: `.github/scripts/self_heal_ci.sh`

Behavior:

1. Trigger on failed `CI` workflow runs.
2. Bootstrap dependencies.
3. Execute lint/tests/frontend build.
4. If checks fail, apply safe auto-fixes and retry.
5. Stop after **2 remediation attempts** and fail fast if still broken.

Agents should preserve this retry cap to avoid infinite loops and token waste.

## Safety boundaries for self-healing runs

- Never bypass failing checks by weakening CI workflow gates.
- Keep `.github/workflows/` edits minimal and intentional.
- Do not disable required tests/lint as a workaround.
- Prefer code fixes over configuration relaxations.

### CI integrity guardrails (non-negotiable)

Unless explicitly requested by a human reviewer in the task, do **not** change:

- `.github/workflows/*`
- `.github/scripts/self_heal_ci.sh`
- `pyproject.toml` lint/test gates
- `frontend/package.json` build scripts

Forbidden examples:

- Disabling or skipping tests/lint/build steps
- Lowering lint strictness to force a pass
- Replacing build/test commands with no-op commands
- Editing CI paths/triggers only to avoid execution

If CI fails, fix product code or tests; do not weaken the verification contract.

## Implementation guardrails

- Keep edits minimal and scoped to the selected checklist item.
- Preserve existing public API contracts unless the task explicitly changes them.
- Do not silently weaken validation behavior for mmCIF connectivity.
- Keep deterministic/provenance fields stable unless schema updates are intentional.
- If schema changes are made, update tests and affected docs in the same run.
- Do not introduce mandatory runtime dependence on simulation execution for v1 default flow.

## Pipeline-specific guidance

### Structure ingest/validation path

Prefer changes that maintain or improve:

- `MMCIFParser` + `MMCIF2Dict` behavior
- `_struct_conn` extraction and retention
- chain normalization + MD-handoff warnings

### Prediction and batch pipeline

Preserve:

- real batch fan-out behavior
- export artifact generation and object-store persistence
- status lifecycle semantics (`queued → running → completed/failed`)

### MD readiness boundary

For v1/v1.1 planning alignment:

- BioPython: parsing/normalization/connectivity
- GROMACS (`Gromacs-CIF`): optional topology/simulation backend
- MDAnalysis: trajectory traversal/aggregation when enabled

## Documentation synchronization rules

If behavior changes, ensure consistency across:

- `Dev_Plan.md`
- `Dev_Plan_Biopython.md`
- `Dev_Plan_Implementation_Checklist.md`

And update any additional docs that would otherwise drift (for example architecture/API notes).

## Required overnight handoff output

At the end of each unattended run, provide a concise report containing:

1. **Objective attempted** (checklist item + phase)
2. **Files changed**
3. **Behavioral impact**
4. **Tests/checks run** and pass/fail results
5. **Open risks/blockers**
6. **Suggested next slice** (single concrete next step)

If blocked, include exact blocker details and the smallest unblocking action.

## Out-of-scope defaults for overnight agents

Unless explicitly requested, do not:

- start major Phase 6 model-expansion efforts
- introduce broad refactors unrelated to a selected checklist slice
- replace established mmCIF-first assumptions with legacy PDB-first shortcuts

---

Use this file as operational policy for autonomous coding sessions in Abby.
