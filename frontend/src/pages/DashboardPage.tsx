import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';

import { ServiceLayerCard } from '../components/ServiceLayerCard';
import { createProject, fetchHealth } from '../lib/api-client';
import { serviceLayerModules, workflowSteps } from '../lib/stub-data';
import { WorkflowStepper } from '../components/WorkflowStepper';

export function DashboardPage() {
  const navigate = useNavigate();
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth, retry: false });
  const cdrCapability = health.data?.capabilities?.cdr_annotation;
  const cdrTelemetry = cdrCapability?.telemetry;
  const createProjectMutation = useMutation({
    mutationFn: () => createProject('Abby Demo Project'),
    onSuccess: (project) => {
      navigate(`/projects/${project.project_id}`);
    },
  });

  return (
    <div className="page-stack">
      <section className="hero card">
        <div>
          <h2>Abby end-to-end frontend</h2>
          <p>
            This UI is wired to the Docker-based Abby stack and exposes the service-layer workflow
            steps that are currently supported by the backend.
          </p>
        </div>
        <div className="health-panel">
          <div className="muted">API health</div>
          <strong>{health.data?.status ?? 'offline / not yet connected'}</strong>
          <div className="muted small">{health.data?.version ?? 'backend unavailable'}</div>
          {health.data?.dependencies?.length ? (
            <div className="muted small">
              <div>Runtime dependencies:</div>
              <ul className="bullet-list compact">
                {health.data.dependencies.map((dependency) => (
                  <li key={dependency.name}>
                    {dependency.name}: {dependency.available ? 'available' : 'missing'}
                    {dependency.required ? ' (required)' : ''}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {cdrCapability ? (
            <div className="muted small health-subpanel">
              <div>CDR annotation runtime:</div>
              <ul className="bullet-list compact">
                <li>Backend: {cdrCapability.backend_available ? 'available' : 'unavailable'}</li>
                <li>
                  Typed validation issues:{' '}
                  {cdrCapability.typed_validation_issues_available ? 'available' : 'unavailable'}
                </li>
                {cdrTelemetry ? (
                  <>
                    <li>
                      Numbering-based: {cdrTelemetry.numbering_based_percent}% ({cdrTelemetry.numbering_based_count}/
                      {cdrTelemetry.total_antibody_summaries})
                    </li>
                    <li>
                      Motif fallback: {cdrTelemetry.motif_fallback_percent}% ({cdrTelemetry.motif_fallback_count}/
                      {cdrTelemetry.total_antibody_summaries})
                    </li>
                    <li>
                      Ambiguous/failed: {cdrTelemetry.ambiguous_or_failed_percent}% ({cdrTelemetry.ambiguous_or_failed_count}/
                      {cdrTelemetry.total_antibody_summaries})
                    </li>
                  </>
                ) : null}
              </ul>
            </div>
          ) : null}
        </div>
      </section>

      <WorkflowStepper steps={workflowSteps} />

      <section className="grid two-col">
        {serviceLayerModules.map((module) => (
          <ServiceLayerCard key={module.title} module={module} />
        ))}
      </section>

      <section className="card">
        <h3>Start with the workflow</h3>
        <p className="muted">
          Use the project view to walk through real upload, chain validation, prediction
          submission, and export workflows.
        </p>
        <div className="inline-actions">
          <button className="button" onClick={() => createProjectMutation.mutate()}>
            {createProjectMutation.isPending ? 'Creating project...' : 'Create backend project'}
          </button>
          <Link className="button secondary" to="/projects/demo-project">
            Open static demo route
          </Link>
        </div>
      </section>
    </div>
  );
}
