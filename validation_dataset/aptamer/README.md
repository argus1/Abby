# Canonical aptamer regression fixtures

This directory contains Abby's minimal, synthetic aptamer conversion and connectivity corpus. The fixtures are regression inputs, not experimental structures and not training data.

## Fixture pair

- `dna_aptamer_target.pdb` — three-residue DNA chain `D` (`DA`, `DC`, `DG`) and two-residue protein target chain `T` (`ALA`, `GLY`). It exercises production PDB→mmCIF conversion and nucleotide-profile parity.
- `dna_aptamer_target.mmcif` — the same chain and residue composition with two explicit phosphodiester `_struct_conn` records linking `DA 1 O3' → DC 2 P` and `DC 2 O3' → DG 3 P`.
- `rna_aptamer_malformed_naming.mmcif` — a parseable RNA-target fixture containing legacy atom name `O5*` and RNA-prefixed residue alias `RA`; validation must report typed compatibility warnings without rejecting the structure.
- `dna_aptamer_na_mg_counterions.mmcif` — a minimal DNA-target fixture with one `NA` and one `MG` coordinate. It exercises typed counterion inventory and the non-blocking ionization-preflight boundary.

## Connectivity boundary

`Bio.PDB.MMCIFIO` preserves parsed atoms, residue names, and chains when converting PDB to mmCIF, but it does not synthesize `_struct_conn` records. Abby therefore treats explicit connectivity in source mmCIF as authoritative and does not fabricate phosphodiester links during conversion.

Regression coverage lives in `tests/test_aptamer_conversion_fixtures.py`.

## Ionization boundary

Abby inventories recognized `NA` and `MG` coordinates with their nominal ionic charges. Their presence does not establish solution concentration, whole-system charge balance, neutralization adequacy, or whether an ion is structural versus solution-phase. Aptamer validation therefore requests an explicit simulation ionization review without blocking structure validation.
