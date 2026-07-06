import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { ServiceLayerCard } from '../components/ServiceLayerCard';
import { getPrediction } from '../lib/api-client';
import { serviceLayerModules, stubPrediction } from '../lib/stub-data';

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
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

  return (
    <div className="page-stack">
      <section className="card">
        <h2>Prediction result</h2>
        <p className="muted">
          This page shows live Abby prediction payloads while preserving the planned deterministic
          feature extraction, baseline scoring, and export story from the service-layer plan.
        </p>
      </section>

      <section className="grid three-col">
        <section className="card metric-card">
          <span className="muted">ΔG output</span>
          <strong>{prediction?.consensus?.delta_g_kcal_mol ?? 'stubbed baseline'}</strong>
        </section>
        <section className="card metric-card">
          <span className="muted">log(K)</span>
          <strong>{prediction?.consensus?.log_k ?? 'stubbed baseline'}</strong>
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
            {!prediction?.explainability && stubPrediction.plannedOutputs.contacts.map((item) => (
              <li key={item}>{item}</li>
            ))}
            {!prediction?.explainability && stubPrediction.plannedOutputs.surface.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h3>Export artifact stubs</h3>
          <ul className="bullet-list compact">
            {stubPrediction.plannedOutputs.exports.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <div className="inline-actions">
            <button className="button">Download contact list (stub)</button>
            <button className="button secondary">Generate PyMOL script (stub)</button>
          </div>
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
        </section>
      )}
    </div>
  );
}
