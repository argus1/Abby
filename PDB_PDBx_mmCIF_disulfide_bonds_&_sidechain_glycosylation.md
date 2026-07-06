**Both formats support disulfide bonds and sidechain glycosylation**, but they handle them very differently. While the legacy PDB format treats these linkages as basic text headers, PDBx/mmCIF uses a rich, relational database schema that fully models complex, branched chemistry. \[1, 2\]

## ---

**1\. Disulfide Bonds**

Disulfide bonds are covalent linkages between the sulfur atoms (SG) of two cysteine residues. \[3, 4, 5\]

* **Legacy PDB Support:** Handled via the **SSBOND** metadata record at the top of the file. It explicitly lists the chain identifiers, residue sequence numbers, and symmetry operations for the two linked cysteines.  
* **PDBx/mmCIF Support:** Standardized under the **\_struct\_conn** data category. It handles disulfides as specific relational linkages. \[6, 7, 8\]

## **Code/Data Representation Comparison:**

**Legacy PDB:**

`SSBOND   1 CYS A    6    CYS A  127                          1555 1555  2.03`

**PDBx/mmCIF:**

`loop_`  
`_struct_conn.id`  
`_struct_conn.conn_type_id`  
`_struct_conn.ptnr1_label_asym_id`  
`_struct_conn.ptnr1_label_seq_id`  
`_struct_conn.ptnr1_label_atom_id`  
`_struct_conn.ptnr2_label_asym_id`  
`_struct_conn.ptnr2_label_seq_id`  
`_struct_conn.ptnr2_label_atom_id`  
`disulf1 disulf A 6 SG A 127 SG`

## ---

**2\. Sidechain Glycosylation**

Glycosylation (attaching carbohydrate glycan chains to amino acid sidechains like Asn, Ser, or Thr) introduces a major challenge: sugars form non-linear, highly branched trees rather than linear chains. \[9, 10, 11, 12, 13\]

## **Legacy PDB (Weak Support)**

* **How it works:** PDB treats glycosylation poorly. It lists the modified amino acid (e.g., ASN) in the sequence, and then defines each individual sugar molecule as an isolated, standalone heteroatom ligand (HETATM). \[7, 14\]  
* **The Linkage:** To connect the sugar to the protein, it relies on a **LINK** record. \[1\]  
* **Failure Mode:** Legacy PDB cannot natively group a complex, branched 12-sugar glycan tree together. Standard molecular software often reads them as random, independent molecules floating near the protein, requiring custom scripts to rebuild the tree topology. \[7, 14\]

## **PDBx/mmCIF (Native, Comprehensive Support)**

* **How it works:** PDBx/mmCIF features a dedicated **Carbohydrate Extension** schema specifically engineered to handle complex branched glycans. \[14\]  
* **The Linkage:** Instead of just drawing a generic link line, it tracks the exact chemical topology using specialized categories:  
  * \_pdbx\_entity\_branch\_link: Defines exactly how individual monosaccharides link to form a branched chain.  
  * \_struct\_conn.pdbx\_role: Explicitly tags the specific biological role of the bond, with allowed values like N-glycosylation, O-glycosylation, or C-mannosylation. \[14, 15\]  
* **Result:** Modern visualization engines (like Mol\*) read this data to automatically render standard 3D [Symbol Nomenclature for Glycans (SNFG)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10292674/) shapes (like blue squares for GlcNAc or green spheres for Mannose). This information is completely lost in legacy PDB files. \[14, 16, 17, 18\]

## ---

**Summary Checklist**

| Covalent Feature \[1, 6, 14, 15, 19\] | Legacy PDB Mechanism | PDBx/mmCIF Mechanism |
| :---- | :---- | :---- |
| **Disulfide Bonds** | SSBOND lines (Fixed columns) | \_struct\_conn loop (Relational) |
| **Glycan Trees** | Flat list of HETATM ligands | \_pdbx\_entity\_branch categories |
| **Glycosylation Link** | LINK lines (No chemical context) | \_struct\_conn \+ Explicit type tagging |

Are you trying to **model/simulate** a glycosylated structure (e.g., using amber/CHARMM force fields) or are you **extracting connectivity data** programmatically? Let me know, and I can point you toward the right parsing tools.

\[1\] [https://pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC8171069/)  
\[2\] [https://journals.iucr.org](https://journals.iucr.org/d/issues/2002/06/01/an0594/index.html)  
\[3\] [https://journals.sagepub.com](https://journals.sagepub.com/doi/10.1089/ars.2012.4807)  
\[4\] [https://www.sciencedirect.com](https://www.sciencedirect.com/science/article/pii/S0049384825000696)  
\[5\] [https://www.sciencedirect.com](https://www.sciencedirect.com/science/article/pii/S0965174899001137)  
\[6\] [https://mmcif.wwpdb.org](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v40.dic/Categories/struct_conn.html)  
\[7\] [https://www.rcsb.org](https://www.rcsb.org/news/feature/60abe1a3301dc46fd700221d)  
\[8\] [https://charmm-gui.org](https://charmm-gui.org/lecture/pdb/1)  
\[9\] [https://pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC10292674/)  
\[10\] [https://github.com](https://github.com/pdbxmmcifwg/carbohydrate-extension/blob/master/Carbohydrates.md)  
\[11\] [https://pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC7115964/)  
\[12\] [https://pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC4335810/)  
\[13\] [https://patents.google.com](https://patents.google.com/patent/WO2023169559A1/en)  
\[14\] [https://pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC10292674/)  
\[15\] [https://journals.iucr.org](https://journals.iucr.org/d/issues/2024/09/00/pea5001/)  
\[16\] [https://mmcif.wwpdb.org](https://mmcif.wwpdb.org/docs/software-resources.html)  
\[17\] [https://pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC11390885/)  
\[18\] [https://pmc.ncbi.nlm.nih.gov](https://pmc.ncbi.nlm.nih.gov/articles/PMC8457362/)  
\[19\] [https://upload.wikimedia.org](https://upload.wikimedia.org/wikipedia/commons/6/62/Identification_of_allosteric_disulfides_from_labile_bonds_in_X-ray_structures.pdf)