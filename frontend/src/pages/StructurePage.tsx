import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import { getStructure } from '../lib/api-client';
import type { StructureValidationIssue } from '../types/api';

function isUuid(value: string | undefined): boolean {
  return Boolean(value?.match(/^[0-9a-fA-F-]{36}$/));
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function DiagnosticList({
  title,
  issues,
  emptyLabel,
}: {
  title: string;
  issues: StructureValidationIssue[] | undefined;
  emptyLabel: string;
}) {
  return (
    <div>
      <h4>{title}</h4>
      {issues && issues.length > 0 ? (
        <ul className="bullet-list compact">
          {issues.map((issue, index) => (
            <li key={`${issue.code}-${index}`}>
              <p>
                <code>{issue.code}</code> — {issue.message}
              </p>
              <details>
                <summary>Details</summary>
                <pre>{prettyJson(issue.details)}</pre>
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{emptyLabel}</p>
      )}
    </div>
  );
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
          Live structure detail from Abby plus the parser and validation logic in
          `services/structures.py` and `services/structure_parsing.py`.
        </p>
      </section>

      <section className="grid two-col">
        <section className="card">
          <h3>Normalized structure summary</h3>
          <ul className="bullet-list compact">
            <li>Input: {detail?.filename ?? 'Demo structure'}</li>
            <li>Parser: {detail?.summary?.parser_name ?? 'MMCIFParser (backend default)'}</li>
            <li>Available chains: {detail?.summary?.available_chains.join(', ') || 'A, B (demo)'}</li>
            <li>Model count: {detail?.summary?.model_count ?? 1}</li>
            <li>Residue counts: {detail?.summary ? JSON.stringify(detail.summary.residue_counts) : '{"A": 1, "B": 1}'}</li>
          </ul>
        </section>
        <section className="card">
          <h3>Validation diagnostics</h3>
          {detail?.validation ? (
            <>
              <h4>Summary</h4>
              <ul className="bullet-list compact">
                <li>
                  Status:{' '}
                  <span className={detail.validation.valid ? 'status-success' : 'status-error'}>
                    {detail.validation.valid ? 'passed' : 'failed'}
                  </span>
                </li>
                <li>Warnings: {detail.validation.warnings.length}</li>
                <li>Errors: {detail.validation.errors.length}</li>
                <li>
                  MD handoff remap required:{' '}
                  {detail.validation.md_handoff?.renaming_required === true ? 'yes' : 'no'}
                </li>
                <li>
                  MD handoff ready:{' '}
                  {detail.validation.md_handoff?.ready_for_md_handoff === true ? 'yes' : 'no'}
                </li>
              </ul>

              <p className={detail.validation.valid ? 'status-success' : 'status-error'}>
                {detail.validation.valid ? 'Validation passed' : 'Validation failed'}
              </p>

              <h4>Warning/Error codes</h4>
              <ul className="bullet-list compact">
                {detail.validation.warnings.length > 0 ? (
                  detail.validation.warnings.map((warning) => (
                    <li key={`warning-${warning}`}><code>{warning}</code></li>
                  ))
                ) : (
                  <li className="muted">No warning codes.</li>
                )}
                {detail.validation.errors.length > 0 ? (
                  detail.validation.errors.map((error) => (
                    <li key={`error-${error}`}><code>{error}</code></li>
                  ))
                ) : (
                  <li className="muted">No error codes.</li>
                )}
              </ul>

              <DiagnosticList
                title="Validation warning details"
                issues={detail.validation.warning_details}
                emptyLabel="No validation warning details."
              />
              <DiagnosticList
                title="Validation error details"
                issues={detail.validation.error_details}
                emptyLabel="No validation error details."
              />

              <h4>MD handoff plan</h4>
              {detail.validation.md_handoff && Object.keys(detail.validation.md_handoff).length > 0 ? (
                <details>
                  <summary>Show canonical chain mapping and preflight signals</summary>
                  <pre>{prettyJson(detail.validation.md_handoff)}</pre>
                </details>
              ) : (
                <p className="muted">No MD handoff guidance was generated for this validation result.</p>
              )}
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

      <section className="card">
        <h3>Parser warnings and metadata</h3>
        {detail?.summary ? (
          <>
            <DiagnosticList
              title="Summary warning details"
              issues={detail.summary.warning_details}
              emptyLabel="No parser warning details."
            />
            <details>
              <summary>Summary metadata (including connectivity / MD preflight)</summary>
              <pre>{prettyJson(detail.summary.metadata)}</pre>
            </details>
          </>
        ) : (
          <p className="muted">No parser summary is currently available.</p>
        )}
      </section>
    </div>
  );
}
