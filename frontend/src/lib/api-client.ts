import { config } from './config';
import type {
  PredictionQueuedResponse,
  PredictionRequest,
  PredictionResult,
  Project,
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

export async function fetchHealth(): Promise<{ status: string; version: string; timestamp: string }> {
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
