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