import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';

import { ServiceLayerCard } from '../components/ServiceLayerCard';
import { createProject, fetchHealth } from '../lib/api-client';
import { serviceLayerModules, workflowSteps } from '../lib/stub-data';
import { WorkflowStepper } from '../components/WorkflowStepper';

export function DashboardPage() {
  const navigate = useNavigate();
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth, retry: false });
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
          <h2>Abby end-to-end frontend stub</h2>
          <p>
            This UI is scaffolded to match the Docker-based Abby stack and expose the planned
            service-layer logic as visible workflow steps.
          </p>
        </div>
        <div className="health-panel">
          <div className="muted">API health</div>
          <strong>{health.data?.status ?? 'offline / not yet connected'}</strong>
          <div className="muted small">{health.data?.version ?? 'backend unavailable'}</div>
        </div>
      </section>

      <WorkflowStepper steps={workflowSteps} />

      <section className="grid two-col">
        {serviceLayerModules.map((module) => (
          <ServiceLayerCard key={module.title} module={module} />
        ))}
      </section>

      <section className="card">
        <h3>Start with the stub workflow</h3>
        <p className="muted">
          Use the project view to walk through real upload, chain validation, prediction
          submission, and service-layer-aware frontend stubs.
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
