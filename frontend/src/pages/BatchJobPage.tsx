import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { getBatchExport, getBatchJob, getBatchResults, getProjectJobs } from '../lib/api-client';

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
}

export function BatchJobPage() {
  const navigate = useNavigate();
  const { projectId, jobId } = useParams();
  const projectIsUuid = isUuid(projectId);
  const jobIsUuid = isUuid(jobId);
  const [autoOpenEnabled, setAutoOpenEnabled] = useState(false);
  const [autoOpenedPredictionId, setAutoOpenedPredictionId] = useState<string | null>(null);

  const projectJobsQuery = useQuery({
    queryKey: ['project-jobs', projectId],
    queryFn: () => getProjectJobs(projectId as string),
    enabled: projectIsUuid,
    retry: false,
    refetchInterval: 5000,
  });

  const jobQuery = useQuery({
    queryKey: ['batch-job', jobId],
    queryFn: () => getBatchJob(jobId as string),
    enabled: jobIsUuid,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'completed' || status === 'failed' ? false : 2000;
    },
  });

  const resultsQuery = useQuery({
    queryKey: ['batch-results', jobId],
    queryFn: () => getBatchResults(jobId as string, 1, 25),
    enabled: jobIsUuid && jobQuery.data?.status === 'completed',
    retry: false,
  });

  const csvExportQuery = useQuery({
    queryKey: ['batch-export', jobId, 'csv'],
    queryFn: () => getBatchExport(jobId as string, 'csv'),
    enabled: jobIsUuid,
    retry: false,
  });

  const jsonExportQuery = useQuery({
    queryKey: ['batch-export', jobId, 'json'],
    queryFn: () => getBatchExport(jobId as string, 'json'),
    enabled: jobIsUuid,
    retry: false,
  });

  const liveJob = jobQuery.data;
  const status = liveJob?.status ?? (jobIsUuid ? 'queued' : 'completed');
  const statusClass =
    status === 'completed' ? 'status-success' : status === 'failed' ? 'status-error' : 'status-warning';
  const firstCompletedPredictionId = resultsQuery.data?.items[0]?.prediction_id;

  useEffect(() => {
    if (!autoOpenEnabled || !firstCompletedPredictionId) {
      return;
    }
    if (autoOpenedPredictionId === firstCompletedPredictionId) {
      return;
    }
    setAutoOpenedPredictionId(firstCompletedPredictionId);
    navigate(`/predictions/${firstCompletedPredictionId}`);
  }, [
    autoOpenEnabled,
    autoOpenedPredictionId,
    firstCompletedPredictionId,
    navigate,
  ]);

  const totalKnown = useMemo(() => {
    if (!liveJob) {
      return 0;
    }
    return liveJob.counts.queued + liveJob.counts.running + liveJob.counts.completed + liveJob.counts.failed;
  }, [liveJob]);

  const resultCutoffSummary = useMemo(() => {
    const cutoffs = new Set(
      (resultsQuery.data?.items ?? [])
        .map((item) => item.provenance?.contact_distance_cutoff_angstrom)
        .filter((value): value is number => typeof value === 'number'),
    );
    return Array.from(cutoffs).sort((left, right) => left - right);
  }, [resultsQuery.data?.items]);

  return (
    <div className="page-stack">
      <section className="card">
        <h2>Batch workflow status</h2>
        <p className="muted">
          Async queue monitor for Abby batch campaigns with live polling for queued/running jobs.
        </p>
        <div className="status-row">
          <span className={`status-pill ${status}`}>Status: {status}</span>
          {jobIsUuid && status !== 'completed' && status !== 'failed' && (
            <span className="muted small">Polling every 2s…</span>
          )}
          {jobQuery.isFetching && <span className="muted small">Refreshing job state…</span>}
        </div>
        {!jobIsUuid && (
          <p className="status-warning">
            Demo route detected. Queue a real batch job from a project page to view live polling.
          </p>
        )}
        {jobQuery.error && <p className="status-error">{(jobQuery.error as Error).message}</p>}
      </section>

      <section className="grid three-col">
        <section className="card metric-card">
          <span className="muted">Queued</span>
          <strong>{liveJob?.counts.queued ?? 0}</strong>
        </section>
        <section className="card metric-card">
          <span className="muted">Running</span>
          <strong>{liveJob?.counts.running ?? 0}</strong>
        </section>
        <section className="card metric-card">
          <span className="muted">Completed</span>
          <strong>{liveJob?.counts.completed ?? 0}</strong>
        </section>
      </section>

      <section className="card">
        <h3>Job health</h3>
        <p className={statusClass}>
          {status === 'queued' && 'Job is queued. Workers will begin processing shortly.'}
          {status === 'running' && 'Job is running. Counts update as predictions complete.'}
          {status === 'completed' && 'Job is complete. Results and exports are available.'}
          {status === 'failed' && 'Job failed. Review failed count and worker logs.'}
        </p>
        <p className="muted">Tracked items: {totalKnown}</p>
      </section>

      <section className="card">
        <h3>Project jobs</h3>
        {projectJobsQuery.data?.jobs?.length ? (
          <ul className="bullet-list compact">
            {projectJobsQuery.data.jobs.slice(0, 8).map((job) => (
              <li key={job.job_id}>
                <code>{job.job_id}</code> — {job.status} (q:{job.counts.queued} r:{job.counts.running} c:{job.counts.completed} f:{job.counts.failed})
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No project jobs found yet.</p>
        )}
      </section>

      <section className="card">
        <h3>Results and exports</h3>
        <p className="muted">Results fetched when job is completed; export links are generated from API endpoints.</p>
        <div className="inline-actions">
          <button
            className={autoOpenEnabled ? 'button secondary' : 'button'}
            onClick={() => setAutoOpenEnabled((current) => !current)}
          >
            {autoOpenEnabled ? 'Disable auto-open' : 'Auto-open first completed result'}
          </button>
          {firstCompletedPredictionId && (
            <button
              className="button secondary"
              onClick={() => navigate(`/predictions/${firstCompletedPredictionId}`)}
            >
              Open first result now
            </button>
          )}
        </div>
        {autoOpenEnabled && !firstCompletedPredictionId && (
          <p className="muted small">Auto-open armed. Waiting for first completed result…</p>
        )}
        <ul className="bullet-list compact">
          <li>Result items loaded: {resultsQuery.data?.items.length ?? 0}</li>
          <li>
            Contact cutoff(s):{' '}
            {resultCutoffSummary.length
              ? resultCutoffSummary.map((value) => `${value.toFixed(2)} Å`).join(', ')
              : 'not available yet'}
          </li>
          <li>
            CSV export:{' '}
            {csvExportQuery.data ? (
              <a href={csvExportQuery.data.download_url} target="_blank" rel="noreferrer">
                {csvExportQuery.data.download_url}
              </a>
            ) : (
              'not ready'
            )}
          </li>
          <li>
            JSON export:{' '}
            {jsonExportQuery.data ? (
              <a href={jsonExportQuery.data.download_url} target="_blank" rel="noreferrer">
                {jsonExportQuery.data.download_url}
              </a>
            ) : (
              'not ready'
            )}
          </li>
        </ul>

        {resultsQuery.data?.items?.length ? (
          <div>
            <h4>Completed prediction preview</h4>
            <ul className="bullet-list compact">
              {resultsQuery.data.items.slice(0, 5).map((item) => (
                <li key={item.prediction_id}>
                  <code>{item.prediction_id}</code> — ΔG {item.consensus?.delta_g_kcal_mol ?? 'n/a'} · log(K){' '}
                  {item.consensus?.log_k ?? 'n/a'} · cutoff{' '}
                  {item.provenance?.contact_distance_cutoff_angstrom?.toFixed(2) ?? 'n/a'} Å
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}
