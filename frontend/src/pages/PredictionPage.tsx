import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { CdrSummaryCard } from '../components/CdrSummaryCard';
import { ServiceLayerCard } from '../components/ServiceLayerCard';
import { getPrediction } from '../lib/api-client';
import { serviceLayerModules, stubPrediction } from '../lib/stub-data';

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
}

function readPredictionDriftReasons(prediction: ReturnType<typeof getPrediction> extends Promise<infer T> ? T | undefined : never): string[] {
  const reasons = prediction?.provenance?.cdr_annotation?.quality_baseline?.drift_reason_codes;
  if (!Array.isArray(reasons)) {
    return [];
  }
  return reasons.map((item) => String(item));
}

export function PredictionPage() {
  const { predictionId } = useParams();
  const predictionIsUuid = isUuid(predictionId);
  const predictionQuery = useQuery({
    queryKey: ['prediction', predictionId],
    queryFn: () => getPrediction(predictionId as string),
    enabled: predictionIsUuid,
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === 'completed' ? false : 1500),
  });

  const prediction = predictionQuery.data;
  const baselineDriftReasons = readPredictionDriftReasons(prediction);
  const status = prediction?.status ?? (predictionIsUuid ? 'queued' : 'completed');
  const isPolling = predictionIsUuid && status !== 'completed' && status !== 'failed';
  const statusClass =
    status === 'completed' ? 'status-success' : status === 'failed' ? 'status-error' : 'status-warning';

  return (
    <div className="page-stack">
      <section className="card">
        <h2>Prediction result</h2>
        <p className="muted">
          This page shows live Abby prediction payloads while preserving deterministic feature
          extraction, baseline scoring, and export provenance from the service-layer workflow.
        </p>
        <div className="status-row">
          <span className={`status-pill ${status}`}>Status: {status}</span>
          {isPolling && <span className="muted small">Polling every 1.5s for completion…</span>}
          {predictionQuery.isFetching && <span className="muted small">Refreshing…</span>}
        </div>
        {predictionQuery.error && (
          <p className="status-error">{(predictionQuery.error as Error).message}</p>
        )}
      </section>

      <section className="card">
        <h3>Execution status</h3>
        <p className={statusClass}>
          {status === 'queued' && 'Prediction is queued and waiting for worker execution.'}
          {status === 'running' && 'Prediction is running. Intermediate updates will appear automatically.'}
          {status === 'completed' && 'Prediction completed. Scores, descriptors, and provenance are ready.'}
          {status === 'failed' && 'Prediction failed. Check logs/validation context and retry.'}
        </p>
      </section>

      <section className="grid three-col">
        <section className="card metric-card">
          <span className="muted">ΔG output</span>
          <strong>{prediction?.consensus?.delta_g_kcal_mol ?? 'loading baseline'}</strong>
        </section>
        <section className="card metric-card">
          <span className="muted">log(K)</span>
          <strong>{prediction?.consensus?.log_k ?? 'loading baseline'}</strong>
        </section>
        <section className="card metric-card">
          <span className="muted">Explainability</span>
          <strong>
            {prediction?.explainability?.top_descriptors.length ?? (predictionIsUuid ? 0 : 'descriptor-backed')} 
            {predictionIsUuid ? ' descriptors' : ''}
          </strong>
        </section>
      </section>

      <section className="grid two-col">
        <section className="card">
          <h3>Descriptor / explainability view</h3>
          <ul className="bullet-list compact">
            {(prediction?.explainability?.top_descriptors ?? []).map((item) => (
              <li key={item.name}>{item.name}: {item.contribution}</li>
            ))}
            {!prediction?.explainability && stubPrediction.exampleOutputs.contacts.map((item) => (
              <li key={item}>{item}</li>
            ))}
            {!prediction?.explainability && stubPrediction.exampleOutputs.surface.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h3>Export artifacts</h3>
          <ul className="bullet-list compact">
            {stubPrediction.exampleOutputs.exports.map((item) => (
              <li key={item}>{item}</li>
            ))}
            {stubPrediction.exampleOutputs.exportNotes?.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <div className="inline-actions">
            <button className="button">Download contact list</button>
            <button className="button secondary">Generate PyMOL script</button>
          </div>
        </section>
      </section>

      <section className="grid two-col">
        <CdrSummaryCard
          title="CDR provenance summary"
          annotation={prediction?.provenance?.cdr_annotation}
          emptyLabel="This prediction does not currently include CDR provenance."
        />
        <section className="card">
          <h3>Provenance highlights</h3>
          {prediction?.provenance ? (
            <>
              <ul className="bullet-list compact">
                <li>Model bundle: {prediction.provenance.model_bundle_version}</li>
                <li>Preprocess version: {prediction.provenance.preprocess_version}</li>
                <li>Descriptor hash: {prediction.provenance.descriptor_hash}</li>
                <li>
                  Contact cutoff: {prediction.provenance.contact_distance_cutoff_angstrom.toFixed(2)} Å
                </li>
              </ul>

              <h4>CDR QA baseline drift</h4>
              {baselineDriftReasons.length > 0 ? (
                <ul className="bullet-list compact">
                  {baselineDriftReasons.map((reason) => (
                    <li key={reason}>
                      <code>{reason}</code>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No CDR baseline drift reasons were reported.</p>
              )}
            </>
          ) : (
            <p className="muted">Prediction provenance is not available yet.</p>
          )}
        </section>
      </section>

      <section className="grid two-col">
        {serviceLayerModules.slice(1).map((module) => (
          <ServiceLayerCard key={module.title} module={module} />
        ))}
      </section>

      {prediction?.provenance && (
        <section className="card">
          <h3>Provenance</h3>
          <p className="muted">Model bundle: {prediction.provenance.model_bundle_version}</p>
          <p className="muted">Preprocess version: {prediction.provenance.preprocess_version}</p>
          <p className="muted">Descriptor hash: {prediction.provenance.descriptor_hash}</p>
          <p className="muted">
            Contact cutoff: {prediction.provenance.contact_distance_cutoff_angstrom.toFixed(2)} Å
          </p>
        </section>
      )}

      {prediction?.provenance && (
        <section className="card">
          <h3>Export bundle notes</h3>
          <p className="muted">
            Downloaded CSV/JSON and descriptor bundle exports retain the configured contact cutoff
            so results can be audited without opening raw JSON.
          </p>
          <ul className="bullet-list compact">
            <li>
              Contact cutoff used: {prediction.provenance.contact_distance_cutoff_angstrom.toFixed(2)} Å
            </li>
            <li>Descriptor hash: {prediction.provenance.descriptor_hash}</li>
            <li>Model bundle: {prediction.provenance.model_bundle_version}</li>
          </ul>
        </section>
      )}
    </div>
  );
}
