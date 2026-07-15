# Abby

A structure-aware affinity decision platform for antibody and protein engineering — fast, interpretable, and experiment-linked.

## Validation harness

Run the ANDD validation harness against the full local corpus with the default output location:

```bash
python -m abby_api.validation_harness --simulation-policy skip
```

Use the small smoke wrapper when you want a filtered pass over a few antibody-antigen ANDD structures:

```bash
python scripts/run_andd_validation.py --smoke --smoke-limit 12
```

By default, harness outputs are written under `data/validation_runs/andd/`.

## Release notes

See [`RELEASE_NOTES.md`](./RELEASE_NOTES.md) for the latest workflow updates, validation guidance, and backend/frontend alignment notes.

![Intact ImmunoGlobulin](IgG.gif)

1IGT
