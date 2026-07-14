# Abby Technical Implementation Plan (BioPython)

This document is the technical implementation companion to the Abby product definition in [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md). It focuses on the structure-processing and feature-extraction workflow needed to support Abby's affinity prediction pipeline for protein-protein and antibody-antigen complexes.

To detail a Python-based workflow using BioPython for Abby, you must focus on maintaining data integrity between the high-fidelity folding outputs and the downstream molecular dynamics (MD) and machine learning (ML) engines.

The primary technical hurdle in this pipeline is the transition from **AlphaFold 3/Boltz-1** (which outputs PDBx/mmCIF files) to **GROMACS/AMBER** (which often require specific atom naming or residue definitions). Using BioPython's `Bio.PDB` module, you can automate the parsing of these complex relational structures to ensure that critical features like disulfide bonds and glycosylation are not lost.

## Implementation priorities aligned to Abby v1

This implementation plan primarily supports the following Abby v1 capabilities:

* **Native PDBx/mmCIF ingestion** for modern predicted and experimental complexes
* **Structure normalization and validation** before affinity inference
* **Feature extraction** for interpretable affinity prediction and downstream ML
* **Compatibility with batch workflows** for researcher-facing campaigns

### **1\. Unified PDBx/mmCIF Parsing Workflow**

Because legacy PDB formats fail to handle large complexes or complex connectivity like branched glycans, your workflow should center on the MMCIFParser to preserve the \_struct\_conn relational data.  
```python
from Bio.PDB import MMCIFParser, MMCIF2Dict

# 1. Initialize the Parser
parser = MMCIFParser(QUIET=True)
structure_id = "antibody_complex"
filename = "af3_output.cif"

# 2. Extract Structure and Relational Dictionary
# The dictionary is essential for accessing the _struct_conn loop directly
structure = parser.get_structure(structure_id, filename)
mmcif_dict = MMCIF2Dict.MMCIF2Dict(filename)

# 3. Identify Critical Connectivity (Disulfides & Glycans)
# This prevents MD engines from treating these as floating ligands
if '_struct_conn.conn_type_id' in mmcif_dict:
    connections = mmcif_dict['_struct_conn.conn_type_id']
    for i, conn_type in enumerate(connections):
        if conn_type == 'disulf':
            print(f"Verified Disulfide: {mmcif_dict['_struct_conn.ptnr1_label_seq_id'][i]}")
```

### **2\. Preparing Structures for Molecular Dynamics (GROMACS)**

Before running MD simulations, you must ensure your antibody chains are properly identified and stripped of any artifacts that might crash the GROMACS topology generator (pdb2gmx).

* **Repository execution baseline:** Abby uses the mmCIF-compatible GROMACS fork [`argus1/Gromacs-CIF`](https://github.com/argus1/Gromacs-CIF), and this build is already installed on the local development machine.

* **Chain Segregation:** Antibodies require distinct chain IDs for heavy and light chains. BioPython allows you to programmatically rename chains if the folding algorithm outputs them generically (e.g., Chain A, B, C).  
* **Non-Standard Residues:** Use BioPython to identify and parameterize any non-standard residues or bioconjugates identified by AlphaFold 3\.

### **3\. Feature Extraction for ML Training**

Once your MD simulation is complete, you can use BioPython to extract the precise structural features needed for your Graph Neural Network (GNN) to predict $K\_D$.

| Feature Type | BioPython Extraction Method | Relevance to Affinity |
| :---- | :---- | :---- |
| **Interatomic Distance** | atom1 \- atom2 (operator overloading) | Measures CDR-antigen proximity. |
| **SASA** | Bio.PDB.SASA.ShrakeRupley | Quantifies hydrophobic exposure. |
| **Residue Depth** | Bio.PDB.ResidueDepth | Identifies buried residues at the interface. |

### **4\. Integration with GNNs (ProteinMPNN/DeepFRI)**

To feed your MD trajectories into a machine learning model, you can use BioPython to convert the refined 3D coordinates into a graph structure where residues are nodes and their spatial interactions are edges.

**Critical Gap:** While BioPython is excellent for structure manipulation, it does not natively handle the large trajectory files (`.xtc` or `.dcd`) produced by GROMACS. You should pair BioPython with **MDAnalysis** to loop through MD frames and extract the averaged structural coordinates for your final ML affinity prediction.

### **4A. Dataset-backed validation harness**

Treat `validation_dataset/ANDD_pdb/` as the canonical local regression corpus for BioPython-driven parsing and validation work.

* **Canonical fixtures:** `validation_dataset/ANDD_pdb/` contains representative local artifacts that exercise structure loading, validation, and export paths without relying on remote data.
* **mmCIF conversion checks:** use the same corpus to verify PDB→mmCIF conversion results, including chain mapping, connectivity preservation, and parser compatibility before the structure is handed downstream.
* **Validation targets:** use these files to confirm that chain normalization, connectivity preservation, and validation summaries stay stable as parsing code evolves.
* **Cross-document alignment:** when the validation corpus changes, update the system plan and implementation checklist so the documented roadmap stays aligned with the regression set.

### **5. GROMACS Integration Boundary**

GROMACS should be treated as an **optional simulation backend** rather than a mandatory part of Abby's core v1 upload-and-predict path, and the CIF-modified `Gromacs-CIF` build should be the preferred backend when mmCIF structures need to flow directly into topology generation.

For this repository's current environment, `Gromacs-CIF` is already installed locally and should be treated as the default GROMACS runtime for mmCIF-oriented development and validation.

* **v1 scope:** support MD-ready preprocessing, topology handoff metadata, and import of externally generated GROMACS outputs.
* **v1 conversion path:** convert validation-dataset structures to `PDBx/mmCIF` first, then hand the mmCIF files to `Gromacs-CIF` for topology generation and optional simulation preparation.
* **v1.1 scope:** add an async worker path that can launch GROMACS jobs, capture run provenance, and store derived trajectory summaries.
* **Implementation detail:** keep BioPython responsible for parsing, chain normalization, and connectivity preservation; keep GROMACS responsible for minimization/simulation; keep MDAnalysis responsible for trajectory traversal and aggregation.
* **Provenance requirements:** record force field, water model, ion settings, equilibration protocol, and random seed alongside any MD-derived features.
* **Artifact contract:** persist the normalized structure, topology references, trajectory summary, and feature snapshot separately so downstream ML can re-use them without rerunning simulation.

### 6. CDR annotation + RepSeq interoperability boundary (v1.1)

For antibody-specific CDR bookkeeping implementation details, use `Dev_Plan_CompDetRAE.md` as the canonical execution plan.

* **Implementation-now focus:** structure-first CDR region extraction, numbering/provenance fields, and deterministic fallback behavior.
* **Optional interoperability:** AIRR-oriented schema/adapter mapping may be added as a non-blocking extension.
* **Guardrail:** do not introduce mandatory repertoire-pipeline preprocessing in the default BioPython parsing/normalization path.
* **Current execution status:** CompDetRAE Phase 0 contract scaffolding is now implemented in `src/abby_api/services/cdr_annotation.py` and `src/abby_api/services/cdr_numbering.py`; proceed with Phase 1 boundary extraction against this fixed contract.

## Relationship to product scope

For Abby v1, this document should be treated as the implementation path for the ingestion, preprocessing, and feature-engineering layers described in [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md). In particular, it supports:

* structure upload validation
* chain mapping and normalization
* descriptor generation for inference
* future extension to batch and compare workflows

Sources:

* [Abby v1 Product Specification](./V1_Product_Spec_Abby.md)  
* [does PDB or PDBx/mmCIF support disulfide bonds and sidechain glycosylation?](./PDB_PDBx_mmCIF_disulfide_bonds_%26_sidechain_glycosylation.md)  
* [how does schema and failure modes compare between PDB and PDBx/mmCIF?](./schema_%26_failure_modes_PDB_vs_PDBx_mmCIF_.md)  
* [Are there software tools that allow prediction of physical properties of bioconjugated proteins?](./prediction_properties_bioconjugated_proteins.md)  
* [does drug conjugation change an antibody's binding affinity?](./ADC_binding_affinity.md)  