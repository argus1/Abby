export function ComparePage() {
  return (
    <div className="page-stack">
      <section className="card">
        <h2>Comparison stub</h2>
        <p className="muted">
          Planned side-by-side comparison view for baseline and future model outputs using the
          same deterministic descriptor bundle.
        </p>
      </section>

      <section className="grid two-col">
        <section className="card">
          <h3>Prediction A</h3>
          <ul className="bullet-list compact">
            <li>ΔG baseline: stubbed</li>
            <li>log(K): stubbed</li>
            <li>Top contact bins: charged-polar, apolar-apolar</li>
          </ul>
        </section>
        <section className="card">
          <h3>Prediction B</h3>
          <ul className="bullet-list compact">
            <li>ΔG baseline: stubbed</li>
            <li>log(K): stubbed</li>
            <li>Top surface bins: apolar surface, charged surface</li>
          </ul>
        </section>
      </section>

      <section className="card">
        <h3>Planned comparison logic</h3>
        <ul className="bullet-list compact">
          <li>Descriptor delta summaries across the same feature families</li>
          <li>Baseline vs future ensemble output comparison</li>
          <li>Exportable shortlist snapshots for scientist review</li>
        </ul>
      </section>
    </div>
  );
}