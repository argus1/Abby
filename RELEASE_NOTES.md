# Release Notes

## 2026-07-11

- Added dataset-backed validation guidance across the planning docs, including PDB→mmCIF conversion checks for `validation_dataset/ANDD_pdb/`.
- Documented the CIF-modified `Gromacs-CIF` workflow as the preferred mmCIF-aware topology-generation path.
- Added health visibility for optional scientific/runtime dependencies in `/health` and surfaced it in the dashboard.
- Finished the Phase 2C frontend alignment cleanup so the UI copy reflects the live backend more accurately.

### Notes

- The CIF-capable GROMACS workflow is exposed on the CLI as `gmx`, including related commands such as `gmx pdb2gmx`.
- For Abby workflows that start from mmCIF, the preferred path is to convert the validation dataset to `PDBx/mmCIF` and then hand it to `Gromacs-CIF` for topology generation.
