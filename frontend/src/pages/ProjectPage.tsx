import { useMutation, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ServiceLayerCard } from '../components/ServiceLayerCard';
import { WorkflowStepper } from '../components/WorkflowStepper';
import {
  createBatchJob,
  createPrediction,
  createProject,
  exportPredictionCDRAIRR,
  getProject,
  uploadStructure,
  validateStructure,
} from '../lib/api-client';
import { serviceLayerModules, stubPrediction, workflowSteps } from '../lib/stub-data';
import type { PredictionMode } from '../types/api';

function parseChains(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
}

const LAST_PREDICTION_ID_STORAGE_KEY = 'abby:lastPredictionId';

export function ProjectPage() {
  const navigate = useNavigate();
  const { projectId } = useParams();
  const projectIsUuid = isUuid(projectId);

  const [projectName, setProjectName] = useState('Abby Demo Project');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [mode, setMode] = useState<PredictionMode>('antibody_antigen');
  const [contactDistanceCutoff, setContactDistanceCutoff] = useState('5.5');
  const [partner1, setPartner1] = useState(stubPrediction.partner1.join(', '));
  const [partner2, setPartner2] = useState(stubPrediction.partner2.join(', '));
  const [activeStructureId, setActiveStructureId] = useState<string | null>(null);
  const [batchStructureIds, setBatchStructureIds] = useState('');
  const [exportPredictionId, setExportPredictionId] = useState(() => {
    if (typeof window === 'undefined') {
      return '';
    }
    return window.localStorage.getItem(LAST_PREDICTION_ID_STORAGE_KEY) ?? '';
  });

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
      const cutoff = Number(contactDistanceCutoff);
      if (!Number.isFinite(cutoff) || cutoff <= 0) {
        throw new Error('Enter a valid contact distance cutoff greater than zero.');
      }
      return createPrediction({
        project_id: projectId,
        mode,
        structure_id: structureId,
        options: {
          include_explainability: true,
          return_all_models: true,
          contact_distance_cutoff_angstrom: cutoff,
        },
        metadata: { candidate_id: 'frontend-demo' },
      });
    },
    onSuccess: (prediction) => {
      setExportPredictionId(prediction.prediction_id);
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(LAST_PREDICTION_ID_STORAGE_KEY, prediction.prediction_id);
      }
      navigate(`/predictions/${prediction.prediction_id}`);
    },
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
      const cutoff = Number(contactDistanceCutoff);
      if (!Number.isFinite(cutoff) || cutoff <= 0) {
        throw new Error('Enter a valid contact distance cutoff greater than zero.');
      }
      return createBatchJob({
        project_id: projectId,
        mode,
        structure_ids: structureIds,
        options: {
          include_explainability: true,
          return_all_models: true,
          contact_distance_cutoff_angstrom: cutoff,
        },
      });
    },
    onSuccess: (job) => navigate(`/projects/${projectId}/batch-jobs/${job.job_id}`),
  });

  const airrExportMutation = useMutation({
    mutationFn: async () => {
      if (!projectId || !projectIsUuid) {
        throw new Error('Create a backend project before exporting AIRR results.');
      }
      const predictionId = exportPredictionId.trim();
      if (!isUuid(predictionId)) {
        throw new Error('Enter a valid prediction ID before exporting AIRR results.');
      }
      return exportPredictionCDRAIRR(predictionId, {});
    },
  });

  const currentProjectName = useMemo(() => {
    if (projectQuery.data?.name) {
      return projectQuery.data.name;
    }
    return stubPrediction.projectName;
  }, [projectQuery.data?.name]);

  const latestPredictionId =
    predictionMutation.data?.prediction_id ||
    (typeof window !== 'undefined'
      ? window.localStorage.getItem(LAST_PREDICTION_ID_STORAGE_KEY) ?? ''
      : '');

  return (
    <div className="page-stack">
      <section className="card">
        <h2>{currentProjectName}</h2>
        <p className="muted">
          This page runs the live backend workflow end-to-end (upload → validate → predict), while
          the service cards summarize implementation boundaries and roadmap context.
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
              <option value="aptamer_target">aptamer_target</option>
            </select>
          </label>
          <label className="field">
            <span>Contact distance cutoff (Å)</span>
            <input
              type="number"
              min="0.1"
              max="20"
              step="0.1"
              value={contactDistanceCutoff}
              onChange={(event) => setContactDistanceCutoff(event.target.value)}
            />
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
          <h3>Service-layer actions</h3>
          <ul className="bullet-list compact">
            <li>Parser selection for `MMCIFParser` vs `PDBParser`</li>
            <li>Disjoint partner validation and chain grouping normalization</li>
            <li>Gap, multi-model, and unsupported residue warnings</li>
            <li>Preparation of normalized structure metadata for downstream services</li>
            <li>Contact cutoff provenance threaded into predictions and batch jobs</li>
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
        <h3>Next actions</h3>
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

      <section className="card">
        <h3>AIRR transport export</h3>
        <p className="muted">
          Generate an explicit AIRR v2.0.0 export for an existing prediction and get a signed
          download link.
        </p>
        <label className="field">
          <span>Prediction ID</span>
          <input
            type="text"
            placeholder="paste prediction UUID"
            value={exportPredictionId}
            onChange={(event) => setExportPredictionId(event.target.value)}
          />
        </label>
        <div className="inline-actions">
          <button
            className="button secondary"
            onClick={() => setExportPredictionId(latestPredictionId)}
            disabled={!isUuid(latestPredictionId)}
            title={
              isUuid(latestPredictionId)
                ? `Use latest prediction ID: ${latestPredictionId}`
                : 'No recent prediction ID available yet'
            }
          >
            Use latest prediction ID
          </button>
          <button className="button" onClick={() => airrExportMutation.mutate()}>
            {airrExportMutation.isPending ? 'Exporting AIRR...' : 'Export AIRR Results'}
          </button>
        </div>
        {!isUuid(latestPredictionId) && (
          <p className="muted">No recent prediction ID found yet. Submit a prediction first.</p>
        )}
        {airrExportMutation.data && (
          <div className="status-panel">
            <p className="status-success">
              AIRR export ready for prediction <code>{airrExportMutation.data.prediction_id}</code>.
            </p>
            <p className="muted">
              Records: {airrExportMutation.data.record_count} · Hash:{' '}
              <code>{airrExportMutation.data.export_hash}</code>
            </p>
            {airrExportMutation.data.artifact.artifact_url ? (
              <p>
                Signed download:{' '}
                <a href={airrExportMutation.data.artifact.artifact_url} target="_blank" rel="noreferrer">
                  {airrExportMutation.data.artifact.artifact_url}
                </a>
              </p>
            ) : (
              <p className="status-warning">No signed download URL was returned for this export.</p>
            )}
          </div>
        )}
        {airrExportMutation.error && (
          <p className="status-error">{(airrExportMutation.error as Error).message}</p>
        )}
      </section>
    </div>
  );
}
