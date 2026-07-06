import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { getStructure } from '../lib/api-client';

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
}

export function StructurePage() {
  const { structureId } = useParams();
  const structureIsUuid = isUuid(structureId);
  const structureQuery = useQuery({
    queryKey: ['structure', structureId],
    queryFn: () => getStructure(structureId as string),
    enabled: structureIsUuid,
    retry: false,
  });

  const detail = structureQuery.data;

  return (
    <div className="page-stack">
      <section className="card">
        <h2>Structure validation detail</h2>
        <p className="muted">
          Live structure detail from Abby plus the parser/validation logic planned in
          `services/structures.py` and `services/structure_parsing.py`.
        </p>
      </section>

      <section className="grid two-col">
        <section className="card">
          <h3>Normalized structure summary</h3>
          <ul className="bullet-list compact">
            <li>Input: {detail?.filename ?? 'Demo structure stub'}</li>
            <li>Parser: {detail?.summary?.parser_name ?? 'MMCIFParser (planned default)'}</li>
            <li>Available chains: {detail?.summary?.available_chains.join(', ') || 'A, B (stub)'}</li>
            <li>Model count: {detail?.summary?.model_count ?? 1}</li>
            <li>Residue counts: {detail?.summary ? JSON.stringify(detail.summary.residue_counts) : '{"A": 1, "B": 1}'}</li>
          </ul>
        </section>
        <section className="card">
          <h3>Validation diagnostics</h3>
          {detail?.validation ? (
            <>
              <p className={detail.validation.valid ? 'status-success' : 'status-error'}>
                {detail.validation.valid ? 'Validation passed' : 'Validation failed'}
              </p>
              <ul className="bullet-list compact">
                {detail.validation.warnings.map((warning) => (
                  <li key={warning}><code>{warning}</code></li>
                ))}
                {detail.validation.errors.map((error) => (
                  <li key={error}><code>{error}</code></li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted">
              {structureIsUuid
                ? 'Run validation from the project page to populate this section.'
                : 'Static demo route: upload a real structure to see backend validation diagnostics.'}
            </p>
          )}
        </section>
      </section>
    </div>
  );
}
