export interface Project {
  project_id: string;
  name: string;
  owner: string;
  created_at: string;
}

export type PredictionMode = 'ppi_general' | 'antibody_antigen' | 'aptamer_target';

export interface ChainMapping {
  partner_1: string[];
  partner_2: string[];
}

export interface StructureInput {
  structure_id: string;
  format: 'pdb' | 'cif' | 'mmcif';
  source: 'upload' | 'pdb_id' | 'derived';
  filename: string;
  sha256: string;
  chains?: ChainMapping | null;
  mode: PredictionMode;
}

export interface CDRRegion {
  start_index: number;
  end_index: number;
  length: number;
}

export interface CDRAnnotatedChain {
  role?: string | null;
  confidence?: 'high' | 'medium' | 'low' | null;
  scheme?: string | null;
  completeness_score?: number;
  regions?: Record<string, CDRRegion>;
  residue_count?: number;
}

export type AntibodyFormat =
  | 'paired_antibody'
  | 'vhh_single_domain'
  | 'unknown_antibody_format';

export type CDRRegionApplicability = 'applicable' | 'not_applicable' | 'unknown';

export interface CDRQualityBaseline {
  available: boolean;
  model_name: string;
  model_contract?: {
    model_id: string;
    model_version: string;
    contract_version: string;
    model_family: string;
    intended_use: string;
    non_blocking: boolean;
    feature_schema_version: string;
    supported_prediction_modes: string[];
    output_schema_version: string;
    calibration_scaffold_version?: string | null;
    calibration_target_label?: string | null;
    calibration_metrics_supported?: string[];
  } | null;
  predicted_confidence_class: 'high' | 'medium' | 'low';
  primary_boundary_confidence: 'high' | 'medium' | 'low';
  score: number;
  drift_flag: boolean;
  drift_reason_codes: string[];
  feature_vector: Record<string, number>;
}

export interface CDRAnnotationToolchain {
  engine_name: string;
  engine_version: string;
  parameters_hash: string;
  reference_data_version?: string | null;
}

export interface CDRAnnotationSummary {
  available: boolean;
  antibody_format: AntibodyFormat;
  scheme?: string | null;
  numbering_scheme?: 'imgt' | 'kabat' | 'chothia' | 'aho' | 'motif_fallback' | null;
  boundary_source?: string | null;
  boundary_confidence: 'high' | 'medium' | 'low';
  boundary_evidence?: string[];
  annotation_toolchain?: CDRAnnotationToolchain | null;
  interop_profile?: 'abby_structural_v1_1' | null;
  selected_heavy_chain?: string | null;
  chains: Record<string, CDRAnnotatedChain>;
  region_applicability: Record<string, CDRRegionApplicability>;
  warnings: string[];
  quality_baseline?: CDRQualityBaseline | null;
}

export interface DatasetSourceProvenance {
  dataset_name: string;
  dataset_role: 'training' | 'evaluation' | 'qa' | 'validation' | 'calibration';
  source_family?: string | null;
  source_label: string;
  license: string;
  license_spdx?: string | null;
  license_compatible: boolean;
  attribution_required: boolean;
  attribution_text?: string | null;
  version?: string | null;
  doi?: string | null;
  preprocessing_method?: string | null;
  notes: string[];
}

export type NucleicAcidChainType = 'dna' | 'rna' | 'mixed' | 'protein' | 'unknown';

export interface ModifiedNucleotide {
  chain_id: string;
  residue_name: string;
  sequence_id: number;
  polymer_type: 'dna' | 'rna';
}

export interface NucleotideAtomNamingIssue {
  chain_id: string;
  residue_name: string;
  sequence_id: number;
  observed_atom_name: string;
  expected_atom_name: string;
  category: 'legacy_star_prime_notation';
}

export interface NucleotideResidueNamingIssue {
  chain_id: string;
  observed_residue_name: string;
  sequence_id: number;
  expected_residue_name: string;
  polymer_type: 'dna' | 'rna';
  category: 'legacy_rna_prefix';
}

export interface CounterionRecord {
  chain_id: string;
  residue_name: 'NA' | 'MG';
  sequence_id: number;
  nominal_charge: 1 | 2;
}

export interface CounterionInventory {
  available: boolean;
  total_ion_count: number;
  ion_counts: Record<string, number>;
  nominal_charge_total: number;
  ions: CounterionRecord[];
}

export type IonizationPreflightReason =
  | 'COUNTERION_ROLE_UNVERIFIED'
  | 'ION_CONCENTRATION_UNKNOWN'
  | 'NEUTRALIZATION_NOT_ASSESSED';

export interface IonizationPreflight {
  status: 'review_required';
  counterions_present: boolean;
  concentration_known: boolean;
  neutralization_assessed: boolean;
  reason_codes: IonizationPreflightReason[];
}

export interface NucleicAcidProfile {
  available: boolean;
  chain_types: Record<string, NucleicAcidChainType>;
  nucleic_acid_chains: string[];
  canonical_nucleotide_counts: Record<string, Record<string, number>>;
  modified_nucleotides: ModifiedNucleotide[];
  atom_naming_issues: NucleotideAtomNamingIssue[];
  residue_naming_issues: NucleotideResidueNamingIssue[];
  counterion_inventory: CounterionInventory;
  ionization_preflight: IonizationPreflight;
}

export interface StructureSummaryMetadata extends Record<string, unknown> {
  cdr_annotation?: CDRAnnotationSummary;
  nucleic_acid_profile?: NucleicAcidProfile;
}

export interface StructureSummary {
  parser_name: string;
  model_count: number;
  available_chains: string[];
  residue_counts: Record<string, number>;
  warnings: string[];
  warning_details: StructureValidationIssue[];
  metadata: StructureSummaryMetadata;
}

export interface StructureValidationIssue {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface StructureValidationRequest {
  structure_id: string;
  mode: PredictionMode;
  chains: ChainMapping;
}

export interface StructureValidationResult {
  valid: boolean;
  normalized_format: 'pdb' | 'mmcif';
  inferred_roles: Record<string, string>;
  available_chains: string[];
  model_count: number;
  chain_groups?: ChainMapping | null;
  partner_residue_counts: Record<string, number>;
  warnings: string[];
  warning_details: StructureValidationIssue[];
  errors: string[];
  error_details: StructureValidationIssue[];
  md_handoff: Record<string, unknown>;
}

export interface StructureDetail extends StructureInput {
  validation?: StructureValidationResult | null;
  summary?: StructureSummary | null;
}

export interface PredictionRequest {
  project_id: string;
  mode: PredictionMode;
  structure_id: string;
  options?: {
    return_all_models?: boolean;
    include_explainability?: boolean;
    temperature_kelvin?: number;
    contact_distance_cutoff_angstrom?: number;
  };
  metadata?: Record<string, string>;
}

export interface PredictionQueuedResponse {
  prediction_id: string;
  status: 'queued';
}

export interface ArtifactReference {
  artifact_type: string;
  artifact_key?: string | null;
  artifact_url?: string | null;
  external_url?: string | null;
  format?: string | null;
}

export interface AIRRCDRExportRequest {
  schema_release?: '2.0.0';
  chain_amino_acid_sequences?: Record<string, string>;
  chain_loci?: Record<string, 'IGH' | 'IGI' | 'IGK' | 'IGL'>;
}

export interface AIRRCDRExportResponse {
  prediction_id: string;
  status: 'exported';
  schema_release: '2.0.0';
  compliance: 'partial';
  record_count: number;
  export_hash: string;
  artifact: ArtifactReference;
}

export interface PredictionOptions {
  return_all_models?: boolean;
  include_explainability?: boolean;
  temperature_kelvin?: number;
  contact_distance_cutoff_angstrom?: number;
}

export interface PredictionResult {
  prediction_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  mode: PredictionMode;
  consensus?: {
    log_k: number;
    delta_g_kcal_mol: number;
    pi90: { lower: number; upper: number };
    confidence: 'high' | 'medium' | 'low';
    ood_flag: boolean;
  } | null;
  best_model?: {
    model_id: string;
    log_k: number;
    delta_g_kcal_mol?: number | null;
    r_validation?: number | null;
  } | null;
  all_models: Array<{
    model_id: string;
    log_k: number;
    delta_g_kcal_mol?: number | null;
    r_validation?: number | null;
  }>;
  explainability?: {
    top_descriptors: Array<{ name: string; contribution: number }>;
  } | null;
  provenance?: {
    model_bundle_version: string;
    preprocess_version: string;
    descriptor_hash: string;
    contact_distance_cutoff_angstrom: number;
    created_at: string;
    dataset_sources?: DatasetSourceProvenance[];
    cdr_annotation?: CDRAnnotationSummary | null;
    nucleic_acid_profile?: NucleicAcidProfile | null;
    artifacts?: {
      airr_cdr_export?: ArtifactReference | null;
      [artifactName: string]: ArtifactReference | null | undefined;
    } | null;
  } | null;
}

export interface BatchJobRequest {
  project_id: string;
  mode: PredictionMode;
  structure_ids: string[];
  options?: PredictionOptions;
}

export interface BatchCounts {
  queued: number;
  running: number;
  completed: number;
  failed: number;
}

export interface BatchJob {
  job_id: string;
  project_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  counts: BatchCounts;
  created_at: string;
  updated_at: string;
}

export interface BatchJobQueuedResponse {
  job_id: string;
  status: 'queued';
}

export interface BatchResultsPage {
  page: number;
  page_size: number;
  total: number;
  items: PredictionResult[];
}

export interface ExportResponse {
  format: 'csv' | 'json';
  download_url: string;
}

export interface ProjectJobsResponse {
  jobs: BatchJob[];
}
