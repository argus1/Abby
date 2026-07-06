export function WorkflowStepper({ steps }: { steps: Array<{ id: string; label: string; state: string }> }) {
  return (
    <div className="stepper">
      {steps.map((step, index) => (
        <div key={step.id} className="step">
          <div className={`step-index step-${step.state}`}>{index + 1}</div>
          <div>
            <div className="step-label">{step.label}</div>
            <div className="muted small">{step.state}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
