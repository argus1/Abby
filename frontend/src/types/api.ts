export interface Project {
  project_id: string;
  name: string;
  owner: string;
  created_at: string;
}

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
  mode: 'ppi_general' | 'antibody_antigen';
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

export interface CDRAnnotationSummary {
  available: boolean;
  scheme?: string | null;
  boundary_source?: string | null;
  boundary_confidence: 'high' | 'medium' | 'low';
  selected_heavy_chain?: string | null;
  chains: Record<string, CDRAnnotatedChain>;
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

export interface StructureSummaryMetadata extends Record<string, unknown> {
  cdr_annotation?: CDRAnnotationSummary;
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
  mode: 'ppi_general' | 'antibody_antigen';
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
  mode: 'ppi_general' | 'antibody_antigen';
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

export interface PredictionOptions {
  return_all_models?: boolean;
  include_explainability?: boolean;
  temperature_kelvin?: number;
  contact_distance_cutoff_angstrom?: number;
}

export interface PredictionResult {
  prediction_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  mode: 'ppi_general' | 'antibody_antigen';
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
  } | null;
}

export interface BatchJobRequest {
  project_id: string;
  mode: 'ppi_general' | 'antibody_antigen';
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
