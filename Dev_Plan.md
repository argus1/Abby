# Abby System Development Plan

This document is the high-level system planning companion to [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md) and [`Dev_Plan_Biopython.md`](./Dev_Plan_Biopython.md). It focuses on the end-to-end architecture of Abby across structure generation, molecular simulation, and affinity prediction.

To develop a robust antibody affinity prediction tool that integrates sequence analysis, structural folding, molecular dynamics (MD), and machine learning (ML), you must establish a seamless data pipeline that prioritizes chemical detail and structural accuracy.

For antibody scope, Abby must support both conventional paired-chain antibodies (`VH/VL`) and **VHH nanobodies** (single-domain heavy-chain antibodies) under the same mmCIF-first integrity rules.

## Relationship to the Abby document set

Use the Abby core planning and design documents together:

* [`V1_Product_Spec_Abby.md`](./V1_Product_Spec_Abby.md) defines product scope, API-facing behavior, and user workflows.
* [`Dev_Plan.md`](./Dev_Plan.md) defines the end-to-end technical system strategy.
* [`Dev_Plan_Biopython.md`](./Dev_Plan_Biopython.md) defines the structure parsing, normalization, and feature-extraction implementation path.
* [`OpenAPI_Abby_v1.yaml`](./OpenAPI_Abby_v1.yaml) defines the external API contract.
* [`Backend_Architecture_Abby.md`](./Backend_Architecture_Abby.md) defines backend service boundaries and deployment design.

### **1\. Sequential Structural Folding & All-Atom Modeling**

The foundation of your tool must be a high-fidelity folding algorithm that can handle the specific complexities of antibody-antigen complexes, such as disulfide bonds and non-standard modifications.

* **AlphaFold 3 / Boltz-1:** Leverage these modern predictors to generate initial 3D coordinates from the antibody sequence. Unlike older models, these can treat ligands and covalent linkages as native elements, which is critical for modeling the antibody-antigen interface accurately.  
* **Rosetta (RosettaLigand/CM):** Use Rosetta for physical modeling to predict structural stability changes ($\\Delta\\Delta G$) and identify potential steric clashes within the binding pocket.  
* **Format Integrity:** You must use the **PDBx/mmCIF** format throughout this stage. Legacy PDB files strip away explicit connectivity data (like \_struct\_conn), which would cause subsequent MD and ML steps to fail in recognizing critical covalent bonds and branched structures like glycosylation.

### **2\. Molecular Dynamics (MD) for Thermodynamic Sampling**

Static structures are insufficient for affinity prediction because binding is a dynamic process influenced by solvent interactions and conformational flexibility.

* **GROMACS / AMBER:** Use these engines to perform energy minimizations and explicit-solvent simulations.  
* **Repository execution baseline:** for Abby development in this repo, use the mmCIF-compatible GROMACS fork [`argus1/Gromacs-CIF`](https://github.com/argus1/Gromacs-CIF). This runtime is already installed on the local machine.
* **Parameterization:** Utilize tools like Antechamber or LigParGen to generate customized force field parameters for any non-standard residues or linkers.  
* **Key Metrics:** From the MD trajectories, extract:  
  * **SASA (Solvent Accessible Surface Area):** To track changes in hydrophobic exposure.  
  * **Radius of Gyration ($R\_g$):** To monitor structural expansion or distortion.  
  * **Binding Kinetics:** These simulations help refine the structural model before the final quantitative prediction.

### **2A. Phased GROMACS Adoption**

To keep Abby aligned with the v1 product scope, GROMACS should be introduced in stages rather than as a hard dependency of the core upload/predict workflow.

In this environment, the required mmCIF-compatible `Gromacs-CIF` build is already present locally; roadmap phases therefore focus on orchestration, provenance capture, and optional workflow exposure rather than base engine installation.

* **Phase 1:** make the backend MD-ready by preserving connectivity, chain mapping, and provenance metadata during structure normalization.
* **Phase 2:** support optional async MD workers that can run GROMACS jobs for users who explicitly request simulation-backed descriptors.
* **Phase 3:** feed trajectory-derived summaries into the existing feature bundle and model orchestration layer, with clear versioning of the simulation protocol.
* **Out-of-scope for v1:** full end-to-end simulation orchestration from the primary user flow should remain optional until the product spec is updated.

### **3\. AI/ML Quantitative Affinity Prediction**

The final stage uses the sampled structural data to predict the quantitative binding affinity (e.g., $K\_D$).

* **Graph Neural Networks (GNNs):** Implement frameworks like **DeepFRI** or **ProteinMPNN** that can read 3D coordinate files (in PDBx/mmCIF format). These models can recalculate binding affinity changes based on the precise structural nodes provided by your MD results.  
* **Surface Property Analysis:** Tools like **PlayMolecule** can be integrated to analyze surface pKa and electrostatic potentials, which are major drivers of antibody-antigen interaction.

### **Critical Pipeline Considerations**

* **Steric Hindrance:** Ensure your model specifically monitors the Complementarity-Determining Regions (CDRs). Any structural distortion or bulky modification near these regions significantly drops affinity. For VHH nanobodies, treat long/atypical `CDR-H3` geometry as first-class rather than as an anomaly.  
* **Validation Data:** While modern therapeutic antibodies nearly always have Surface Plasmon Resonance (SPR) data available for training, research antibodies often lack this. Your ML model should ideally be trained on SPR-validated datasets to ensure it predicts true kinetic constants ($k\_{on}, k\_{off}$) rather than just qualitative binding.  
* **Scale Immunity:** Using PDBx/mmCIF ensures your tool can handle large antibody-antigen complexes without the atom-numbering overflows or parsing crashes common with legacy PDB files.

### VHH nanobody support requirements (v1/v1.1)

To make VHH support explicit and deterministic across ingest → validation → prediction:

* **Antibody format typing:** classify structures as `paired_antibody`, `vhh_single_domain`, or `unknown_antibody_format` using sequence/structure evidence, not only chain IDs.
* **Heavy-only legality:** do not emit missing-light-chain errors for VHH inputs; treat heavy-only as valid when supported by chain role confidence.
* **CDR region expectations:** for VHH mode, require heavy-chain CDR bookkeeping (`CDR-H1/H2/H3`) and mark light-chain regions as `not_applicable` instead of `missing`.
* **Provenance contract:** persist `antibody_format`, boundary source, numbering scheme, and confidence so downstream scoring and audits can separate VHH from paired-antibody behavior.
* **Descriptor parity:** expose the same stable descriptor/provenance envelope for VHH predictions, with explicit flags when light-chain-dependent features are skipped.

### CDR annotation interoperability boundary (v1.1)

For CDR-aware structural bookkeeping, Abby v1.1 should follow the execution path defined in `Dev_Plan_CompDetRAE.md`, including Appendix A (RepSeq interoperability profile).

* **Use now:** deterministic structural CDR boundaries, explicit numbering/provenance, and typed ambiguity handling.
* **Use later/optional:** AIRR-compliant import/export adapters and repertoire-scale analytics.
* **Keep out of v1.1 core flow:** mandatory AIRR-seq assembly dependencies or repertoire-only boundary inference replacing structure-driven extraction.
* **VHH profile rule:** treat heavy-only single-domain antibody inputs as first-class in this same boundary contract; do not require light-chain region resolution to report `cdr_annotation.available=true`.
* **Current execution status:** CompDetRAE Phase 0 (contract/taxonomy foundations) is implemented; next delivery slice is Phase 1 deterministic CDR-H3 boundary extraction and provenance threading.

### Aptamer support extension track (v1.1+)

To expand Abby beyond protein-protein and antibody-antigen workflows, add aptamer support as a **v1.1+ extension track** with strict contract boundaries and no disruption to default v1 behavior.

* **Scope intent:** support DNA/RNA aptamer-target affinity workflows under the same mmCIF-first integrity and provenance rules.
* **Mode taxonomy extension:** add an aptamer-capable prediction mode (for example `aptamer_target`) only when API/schema updates are delivered in lockstep.
* **Primary ingest requirement:** preserve nucleic-acid connectivity and modified-nucleotide metadata during parsing/normalization, analogous to `_struct_conn` handling for protein chemistry.
* **Validation profile:** add nucleic-acid-aware checks (chain typing, modified residue handling, and typed warnings for unsupported chemistries) without weakening existing protein/antibody validation contracts.
* **Descriptor profile:** introduce aptamer-oriented structural descriptors (for example, nucleic-acid SASA partitions, flexibility summaries, and ion-contact summaries) under explicit provenance/versioning.
* **MD boundary:** keep simulation optional in user-facing flow; when simulation-backed descriptors are used, persist force field, solvent model, ion settings, protocol stages, and random seed in simulation provenance.
* **Dataset expectation:** add a canonical local aptamer regression corpus and run conversion/validation checks in parallel with `validation_dataset/ANDD_pdb/` to avoid domain skew.
* **Out-of-scope for this extension slice:** mandatory de novo aptamer folding orchestration in the default prediction path.

### **Dataset-backed validation workflow**

Treat `validation_dataset/ANDD_pdb/` as the canonical local regression corpus for Abby planning, implementation, and verification.

* **Primary corpus:** `validation_dataset/ANDD_pdb/` is the reference set for validating structure ingestion, normalization, validation diagnostics, and batch export behavior.
* **mmCIF conversion workflow:** keep the validation corpus available in `PDBx/mmCIF` form and verify PDB→mmCIF conversion before any validation, prediction, or export step.
* **Regression coverage:** when parser, validation, batch, or export logic changes, rerun the relevant checks against the dataset so the documented workflow stays grounded in real inputs.
* **Roadmap linkage:** keep dataset-backed validation expectations synchronized across `Dev_Plan.md`, `Dev_Plan_Biopython.md`, and `Dev_Plan_Implementation_Checklist.md` whenever new benchmark files are added.

## Relationship to implementation and API design

This document should inform the service decomposition and workflow design in Abby's backend architecture and API definitions. In particular, it drives:

* structure-processing service boundaries
* model orchestration and asynchronous job execution
* storage needs for structures, descriptors, predictions, and provenance
* future integration with simulation and assay-planning workflows

Sources:

* [Abby v1 Product Specification](./V1_Product_Spec_Abby.md)  
* [Abby Technical Implementation Plan (BioPython)](./Dev_Plan_Biopython.md)  
* [Are there software tools that allow prediction of physical properties of bioconjugated proteins?](./prediction_properties_bioconjugated_proteins.md)  
* [does PDB or PDBx/mmCIF support disulfide bonds and sidechain glycosylation?](./PDB_PDBx_mmCIF_disulfide_bonds_%26_sidechain_glycosylation.md)  
* [does drug conjugation change an antibody's binding affinity?](./ADC_binding_affinity.md)  
* [Surface plasmon resonance antibody characterization notes](./antibodies_SPR.md)  
* [how does schema and failure modes compare between PDB and PDBx/mmCIF?](./schema_%26_failure_modes_PDB_vs_PDBx_mmCIF_.md)
* [aptamer molecular dynamics notes](./aptamers_molecular_dynamics.md)
