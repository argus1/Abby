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