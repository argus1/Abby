import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { getPrediction } from '../lib/api-client';

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
}

export function ComparePage() {
  const { leftPredictionId, rightPredictionId } = useParams();
  const leftIsUuid = isUuid(leftPredictionId);
  const rightIsUuid = isUuid(rightPredictionId);

  const leftQuery = useQuery({
    queryKey: ['compare-prediction', 'left', leftPredictionId],
    queryFn: () => getPrediction(leftPredictionId as string),
    enabled: leftIsUuid,
    retry: false,
  });

  const rightQuery = useQuery({
    queryKey: ['compare-prediction', 'right', rightPredictionId],
    queryFn: () => getPrediction(rightPredictionId as string),
    enabled: rightIsUuid,
    retry: false,
  });

  const leftPrediction = leftQuery.data;
  const rightPrediction = rightQuery.data;
  const leftDescriptors = leftPrediction?.explainability?.top_descriptors ?? [];
  const rightDescriptors = rightPrediction?.explainability?.top_descriptors ?? [];

  return (
    <div className="page-stack">
      <section className="card">
        <h2>Prediction comparison</h2>
        <p className="muted">
          Side-by-side comparison view for Abby predictions using the same deterministic descriptor
          bundle and explicit provenance, including the configured contact cutoff.
        </p>
        {leftQuery.error && <p className="status-error">{(leftQuery.error as Error).message}</p>}
        {rightQuery.error && <p className="status-error">{(rightQuery.error as Error).message}</p>}
      </section>

      <section className="grid two-col">
        <section className="card">
          <h3>Prediction A</h3>
          <ul className="bullet-list compact">
            <li>Prediction ID: {leftPredictionId ?? 'stubbed'}</li>
            <li>ΔG baseline: {leftPrediction?.consensus?.delta_g_kcal_mol ?? 'stubbed'}</li>
            <li>log(K): {leftPrediction?.consensus?.log_k ?? 'stubbed'}</li>
            <li>
              Contact cutoff:{' '}
              {leftPrediction?.provenance?.contact_distance_cutoff_angstrom !== undefined
                ? `${leftPrediction.provenance.contact_distance_cutoff_angstrom.toFixed(2)} Å`
                : 'stubbed'}
            </li>
            <li>
              Top descriptors:{' '}
              {leftDescriptors.length
                ? leftDescriptors.map((item) => item.name).join(', ')
                : 'charged-polar, apolar-apolar'}
            </li>
          </ul>
        </section>
        <section className="card">
          <h3>Prediction B</h3>
          <ul className="bullet-list compact">
            <li>Prediction ID: {rightPredictionId ?? 'stubbed'}</li>
            <li>ΔG baseline: {rightPrediction?.consensus?.delta_g_kcal_mol ?? 'stubbed'}</li>
            <li>log(K): {rightPrediction?.consensus?.log_k ?? 'stubbed'}</li>
            <li>
              Contact cutoff:{' '}
              {rightPrediction?.provenance?.contact_distance_cutoff_angstrom !== undefined
                ? `${rightPrediction.provenance.contact_distance_cutoff_angstrom.toFixed(2)} Å`
                : 'stubbed'}
            </li>
            <li>
              Top descriptors:{' '}
              {rightDescriptors.length
                ? rightDescriptors.map((item) => item.name).join(', ')
                : 'apolar surface, charged surface'}
            </li>
          </ul>
        </section>
      </section>

      <section className="card">
        <h3>Comparison summary</h3>
        <ul className="bullet-list compact">
          <li>
            Contact cutoff delta:{' '}
            {leftPrediction?.provenance?.contact_distance_cutoff_angstrom !== undefined &&
            rightPrediction?.provenance?.contact_distance_cutoff_angstrom !== undefined
              ? `${Math.abs(
                  leftPrediction.provenance.contact_distance_cutoff_angstrom -
                    rightPrediction.provenance.contact_distance_cutoff_angstrom,
                ).toFixed(2)} Å`
              : 'available when both predictions are loaded'}
          </li>
          <li>
            Descriptor hash pair:{' '}
            {leftPrediction?.provenance?.descriptor_hash && rightPrediction?.provenance?.descriptor_hash
              ? `${leftPrediction.provenance.descriptor_hash.slice(0, 8)}… vs ${rightPrediction.provenance.descriptor_hash.slice(0, 8)}…`
              : 'descriptor-backed comparison pending'}
          </li>
          <li>Exportable shortlist snapshots for scientist review</li>
        </ul>
      </section>
    </div>
  );
}