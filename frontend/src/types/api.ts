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

export interface StructureSummary {
  parser_name: string;
  model_count: number;
  available_chains: string[];
  residue_counts: Record<string, number>;
  warnings: string[];
  warning_details: StructureValidationIssue[];
  metadata: Record<string, unknown>;
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
