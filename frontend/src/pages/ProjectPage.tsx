import { useMutation, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ServiceLayerCard } from '../components/ServiceLayerCard';
import { WorkflowStepper } from '../components/WorkflowStepper';
import {
  createBatchJob,
  createPrediction,
  createProject,
  getProject,
  uploadStructure,
  validateStructure,
} from '../lib/api-client';
import { serviceLayerModules, stubPrediction, workflowSteps } from '../lib/stub-data';

function parseChains(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
}

export function ProjectPage() {
  const navigate = useNavigate();
  const { projectId } = useParams();
  const projectIsUuid = isUuid(projectId);

  const [projectName, setProjectName] = useState('Abby Demo Project');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [mode, setMode] = useState<'ppi_general' | 'antibody_antigen'>('antibody_antigen');
  const [partner1, setPartner1] = useState(stubPrediction.partner1.join(', '));
  const [partner2, setPartner2] = useState(stubPrediction.partner2.join(', '));
  const [activeStructureId, setActiveStructureId] = useState<string | null>(null);
  const [batchStructureIds, setBatchStructureIds] = useState('');

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId as string),
    enabled: projectIsUuid,
    retry: false,
  });

  const createProjectMutation = useMutation({
    mutationFn: () => createProject(projectName),
    onSuccess: (project) => navigate(`/projects/${project.project_id}`),
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedFile || !projectId || !projectIsUuid) {
        throw new Error('Select a file and create a backend project first.');
      }
      return uploadStructure(selectedFile, mode, projectId);
    },
    onSuccess: (structure) => setActiveStructureId(structure.structure_id),
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      const structureId = activeStructureId ?? uploadMutation.data?.structure_id;
      if (!structureId) {
        throw new Error('Upload a structure before validation.');
      }
      return validateStructure({
        structure_id: structureId,
        mode,
        chains: {
          partner_1: parseChains(partner1),
          partner_2: parseChains(partner2),
        },
      });
    },
  });

  const predictionMutation = useMutation({
    mutationFn: async () => {
      const structureId = activeStructureId ?? uploadMutation.data?.structure_id;
      if (!projectId || !projectIsUuid || !structureId) {
        throw new Error('Create a backend project and upload a structure before predicting.');
      }
      return createPrediction({
        project_id: projectId,
        mode,
        structure_id: structureId,
        options: { include_explainability: true, return_all_models: true },
        metadata: { candidate_id: 'frontend-demo' },
      });
    },
    onSuccess: (prediction) => navigate(`/predictions/${prediction.prediction_id}`),
  });

  const batchMutation = useMutation({
    mutationFn: async () => {
      if (!projectId || !projectIsUuid) {
        throw new Error('Create a backend project before queuing a batch job.');
      }
      const parsed = batchStructureIds
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      const structureIds = parsed.length > 0 ? parsed : activeStructureId ? [activeStructureId] : [];
      if (structureIds.length === 0) {
        throw new Error('Provide at least one structure ID or upload a structure first.');
      }
      return createBatchJob({
        project_id: projectId,
        mode,
        structure_ids: structureIds,
        options: { include_explainability: true, return_all_models: true },
      });
    },
    onSuccess: (job) => navigate(`/projects/${projectId}/batch-jobs/${job.job_id}`),
  });

  const currentProjectName = useMemo(() => {
    if (projectQuery.data?.name) {
      return projectQuery.data.name;
    }
    return stubPrediction.projectName;
  }, [projectQuery.data?.name]);

  return (
    <div className="page-stack">
      <section className="card">
        <h2>{currentProjectName}</h2>
        <p className="muted">
          This page mixes real backend calls with service-layer stubs, so Abby can exercise the
          upload → validate → predict flow while structure analytics mature underneath.
        </p>
        {!projectIsUuid && (
          <div className="inline-actions">
            <input
              className="inline-input"
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
            />
            <button className="button" onClick={() => createProjectMutation.mutate()}>
              {createProjectMutation.isPending ? 'Creating...' : 'Create backend project'}
            </button>
          </div>
        )}
      </section>

      <WorkflowStepper steps={workflowSteps} />

      <section className="card grid two-col">
        <div>
          <h3>Structure upload + validation</h3>
          <label className="field">
            <span>Structure file</span>
            <input
              type="file"
              accept=".pdb,.cif,.mmcif"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label className="field">
            <span>Prediction mode</span>
            <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
              <option value="antibody_antigen">antibody_antigen</option>
              <option value="ppi_general">ppi_general</option>
            </select>
          </label>
          <label className="field">
            <span>Partner 1 chains</span>
            <input type="text" value={partner1} onChange={(event) => setPartner1(event.target.value)} />
          </label>
          <label className="field">
            <span>Partner 2 chains</span>
            <input type="text" value={partner2} onChange={(event) => setPartner2(event.target.value)} />
          </label>
          <div className="inline-actions">
            <button className="button" onClick={() => uploadMutation.mutate()}>
              {uploadMutation.isPending ? 'Uploading...' : 'Upload structure'}
            </button>
            <button className="button secondary" onClick={() => validateMutation.mutate()}>
              {validateMutation.isPending ? 'Validating...' : 'Validate mapping'}
            </button>
            <button className="button" onClick={() => predictionMutation.mutate()}>
              {predictionMutation.isPending ? 'Submitting...' : 'Submit prediction'}
            </button>
          </div>
          {uploadMutation.data && (
            <p className="status-success">
              Uploaded <strong>{uploadMutation.data.filename}</strong> as structure{' '}
              <code>{uploadMutation.data.structure_id}</code>
            </p>
          )}
          {(uploadMutation.error || validateMutation.error || predictionMutation.error) && (
            <p className="status-error">
              {(uploadMutation.error as Error | null)?.message ||
                (validateMutation.error as Error | null)?.message ||
                (predictionMutation.error as Error | null)?.message}
            </p>
          )}
        </div>
        <div>
          <h3>Planned service-layer actions</h3>
          <ul className="bullet-list compact">
            <li>Parser selection for `MMCIFParser` vs `PDBParser`</li>
            <li>Disjoint partner validation and chain grouping normalization</li>
            <li>Gap, multi-model, and unsupported residue warnings</li>
            <li>Preparation of normalized structure metadata for downstream services</li>
          </ul>
          {validateMutation.data && (
            <div className="status-panel">
              <h4>Validation result</h4>
              <p className="muted">Available chains: {validateMutation.data.available_chains.join(', ') || 'none'}</p>
              <p className="muted">Model count: {validateMutation.data.model_count}</p>
              <p className="muted">
                Partner residue counts: {JSON.stringify(validateMutation.data.partner_residue_counts)}
              </p>
              <p className={validateMutation.data.valid ? 'status-success' : 'status-error'}>
                {validateMutation.data.valid ? 'Validation passed' : 'Validation failed'}
              </p>
              {validateMutation.data.warnings.length > 0 && (
                <p className="status-warning">Warnings: {validateMutation.data.warnings.join(', ')}</p>
              )}
              {validateMutation.data.errors.length > 0 && (
                <p className="status-error">Errors: {validateMutation.data.errors.join(', ')}</p>
              )}
            </div>
          )}
        </div>
      </section>

      {activeStructureId && (
        <section className="card">
          <div className="inline-actions">
            <Link className="button secondary" to={`/projects/${projectId}/structures/${activeStructureId}`}>
              Open structure detail
            </Link>
          </div>
        </section>
      )}

      <section className="grid two-col">
        {serviceLayerModules.map((module) => (
          <ServiceLayerCard key={module.title} module={module} />
        ))}
      </section>

      <section className="card">
        <h3>Next stub actions</h3>
        <label className="field">
          <span>Batch structure IDs (comma-separated, optional)</span>
          <input
            type="text"
            placeholder={activeStructureId ?? 'use uploaded structure automatically'}
            value={batchStructureIds}
            onChange={(event) => setBatchStructureIds(event.target.value)}
          />
        </label>
        <div className="inline-actions">
          <button className="button secondary" onClick={() => predictionMutation.mutate()}>
            Submit prediction with current structure
          </button>
          <button className="button" onClick={() => batchMutation.mutate()}>
            {batchMutation.isPending ? 'Queueing batch...' : 'Queue batch workflow'}
          </button>
          <Link className="button secondary" to={`/projects/${projectId ?? 'demo-project'}/batch-jobs/demo-job`}>
            Open demo batch route
          </Link>
        </div>
        {batchMutation.data && (
          <p className="status-success">
            Queued batch job <code>{batchMutation.data.job_id}</code>. Opening live status page...
          </p>
        )}
        {batchMutation.error && (
          <p className="status-error">{(batchMutation.error as Error).message}</p>
        )}
      </section>
    </div>
  );
}
