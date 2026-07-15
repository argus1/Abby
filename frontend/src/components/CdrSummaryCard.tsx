import type { CDRAnnotationSummary } from '../types/api';

function humanizeBoundarySource(value: string | null | undefined): string {
  if (!value) {
    return 'unavailable';
  }
  return value.replace(/_/g, ' ');
}

function summarizeChainRegions(annotation: CDRAnnotationSummary): string {
  const chainEntries = Object.entries(annotation.chains ?? {});
  if (chainEntries.length === 0) {
    return 'No chain-level CDR bookkeeping was returned.';
  }

  return chainEntries
    .map(([chainId, chain]) => {
      const role = chain.role ?? 'unknown';
      const regionCount = Object.keys(chain.regions ?? {}).length;
      const completeness = Math.round((chain.completeness_score ?? 0) * 100);
      return `${chainId} (${role}): ${regionCount} region${regionCount === 1 ? '' : 's'}, ${completeness}% complete`;
    })
    .join(' • ');
}

export function CdrSummaryCard({
  title,
  annotation,
  emptyLabel,
}: {
  title: string;
  annotation?: CDRAnnotationSummary | null;
  emptyLabel: string;
}) {
  const chainEntries = Object.entries(annotation?.chains ?? {});
  const warningCount = annotation?.warnings?.length ?? 0;
  const qualityBaseline = annotation?.quality_baseline;
  const qualityContract = qualityBaseline?.model_contract;

  return (
    <section className="card">
      <h3>{title}</h3>
      {annotation ? (
        <div className="cdr-summary-stack">
          <div className="status-row">
            <span className={`status-pill ${annotation.available ? 'completed' : 'failed'}`}>
              {annotation.available ? 'CDR annotation available' : 'CDR annotation unavailable'}
            </span>
            <span className={`status-pill cdr-confidence ${annotation.boundary_confidence}`}>
              Confidence: {annotation.boundary_confidence}
            </span>
          </div>

          <ul className="bullet-list compact">
            <li>Boundary source: {humanizeBoundarySource(annotation.boundary_source)}</li>
            <li>Scheme: {annotation.scheme ?? 'not assigned'}</li>
            <li>Selected heavy chain: {annotation.selected_heavy_chain ?? 'not identified'}</li>
            <li>Annotated chains: {chainEntries.length}</li>
            <li>Typed warnings: {warningCount}</li>
          </ul>

          <div className="cdr-summary-panel">
            <div className="muted small">Chain summary</div>
            <p>{summarizeChainRegions(annotation)}</p>
          </div>

          {qualityBaseline ? (
            <div className="cdr-summary-panel">
              <div className="muted small">QA baseline</div>
              <div className="status-row">
                <span
                  className={`status-pill cdr-confidence ${qualityBaseline.predicted_confidence_class}`}
                >
                  Baseline: {qualityBaseline.predicted_confidence_class}
                </span>
                <span className={`status-pill ${qualityBaseline.drift_flag ? 'failed' : 'completed'}`}>
                  {qualityBaseline.drift_flag ? 'Drift flagged' : 'No drift flag'}
                </span>
              </div>
              <ul className="bullet-list compact">
                <li>Baseline model: {qualityBaseline.model_name}</li>
                <li>
                  Contract: {qualityContract?.contract_version ?? 'unversioned'}
                </li>
                <li>
                  Model ID/version: {qualityContract ? `${qualityContract.model_id}@${qualityContract.model_version}` : 'unspecified'}
                </li>
                <li>Score: {qualityBaseline.score.toFixed(2)}</li>
                <li>Primary confidence: {qualityBaseline.primary_boundary_confidence}</li>
              </ul>
              {qualityBaseline.drift_reason_codes.length > 0 ? (
                <ul className="bullet-list compact">
                  {qualityBaseline.drift_reason_codes.map((reason) => (
                    <li key={reason}>
                      <code>{reason}</code>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {warningCount > 0 ? (
            <div className="cdr-summary-panel">
              <div className="muted small">Typed CDR warnings</div>
              <ul className="bullet-list compact">
                {annotation.warnings.map((warning) => (
                  <li key={warning}>
                    <code>{warning}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="muted">No typed CDR warnings were reported.</p>
          )}
        </div>
      ) : (
        <p className="muted">{emptyLabel}</p>
      )}
    </section>
  );
}