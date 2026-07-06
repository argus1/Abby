export function BatchJobPage() {
  return (
    <div className="page-stack">
      <section className="card">
        <h2>Batch campaign stub</h2>
        <p className="muted">
          This view is designed for the async job model in Abby: queue submission, progress
          polling, result ranking, and export generation.
        </p>
      </section>

      <section className="grid three-col">
        <section className="card metric-card">
          <span className="muted">Queued</span>
          <strong>1000</strong>
        </section>
        <section className="card metric-card">
          <span className="muted">Running</span>
          <strong>120</strong>
        </section>
        <section className="card metric-card">
          <span className="muted">Completed</span>
          <strong>740</strong>
        </section>
      </section>

      <section className="card">
        <h3>Planned worker-backed stages</h3>
        <ul className="bullet-list compact">
          <li>Validation workers confirm partner mapping</li>
          <li>Descriptor workers compute contact and RSA features</li>
          <li>Baseline model workers score deterministic outputs</li>
          <li>Export workers produce CSV/JSON and scientist artifacts</li>
        </ul>
      </section>
    </div>
  );
}
