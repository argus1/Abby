import { config } from './config';
import type {
  BatchJob,
  BatchJobQueuedResponse,
  BatchJobRequest,
  BatchResultsPage,
  ExportResponse,
  PredictionQueuedResponse,
  PredictionRequest,
  PredictionResult,
  Project,
  ProjectJobsResponse,
  StructureDetail,
  StructureInput,
  StructureValidationRequest,
  StructureValidationResult,
} from '../types/api';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    ...init,
    headers: {
      'X-API-Key': config.apiKey,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `API request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function fetchHealth(): Promise<{
  status: string;
  version: string;
  timestamp: string;
  dependencies: Array<{
    name: string;
    available: boolean;
    required: boolean;
    detail?: string | null;
  }>;
  capabilities?: {
    cdr_annotation: {
      backend_available: boolean;
      numbering_support_available: boolean;
      motif_fallback_available: boolean;
      typed_validation_issues_available: boolean;
      telemetry?: {
        total_antibody_summaries: number;
        numbering_based_count: number;
        numbering_based_percent: number;
        motif_fallback_count: number;
        motif_fallback_percent: number;
        ambiguous_or_failed_count: number;
        ambiguous_or_failed_percent: number;
      } | null;
      detail?: string | null;
    };
  } | null;
}> {
  return apiFetch('/health');
}

export async function createProject(name: string): Promise<Project> {
  return apiFetch<Project>('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function getProject(projectId: string): Promise<Project> {
  return apiFetch<Project>(`/projects/${projectId}`);
}

export async function uploadStructure(
  file: File,
  mode: 'ppi_general' | 'antibody_antigen',
  projectId?: string,
): Promise<StructureInput> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('mode', mode);
  if (projectId) {
    formData.append('project_id', projectId);
  }

  return apiFetch<StructureInput>('/structures:upload', {
    method: 'POST',
    body: formData,
  });
}

export async function validateStructure(
  payload: StructureValidationRequest,
): Promise<StructureValidationResult> {
  return apiFetch<StructureValidationResult>('/structures:validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getStructure(structureId: string): Promise<StructureDetail> {
  return apiFetch<StructureDetail>(`/structures/${structureId}`);
}

export async function createPrediction(
  payload: PredictionRequest,
): Promise<PredictionQueuedResponse> {
  return apiFetch<PredictionQueuedResponse>('/predictions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getPrediction(predictionId: string): Promise<PredictionResult> {
  return apiFetch<PredictionResult>(`/predictions/${predictionId}`);
}

export async function createBatchJob(payload: BatchJobRequest): Promise<BatchJobQueuedResponse> {
  return apiFetch<BatchJobQueuedResponse>('/batch-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getBatchJob(jobId: string): Promise<BatchJob> {
  return apiFetch<BatchJob>(`/batch-jobs/${jobId}`);
}

export async function getProjectJobs(projectId: string): Promise<ProjectJobsResponse> {
  return apiFetch<ProjectJobsResponse>(`/projects/${projectId}/jobs`);
}

export async function getBatchResults(
  jobId: string,
  page = 1,
  pageSize = 100,
): Promise<BatchResultsPage> {
  return apiFetch<BatchResultsPage>(`/batch-jobs/${jobId}/results?page=${page}&page_size=${pageSize}`);
}

export async function getBatchExport(jobId: string, format: 'csv' | 'json'): Promise<ExportResponse> {
  return apiFetch<ExportResponse>(`/batch-jobs/${jobId}/export?format=${format}`);
}
