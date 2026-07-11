export function SettingsPage() {
  return (
    <div className="page-stack">
      <section className="card">
        <h2>Frontend settings</h2>
        <p className="muted">
          Settings for local API URL, API key storage, and future feature flags.
        </p>
      </section>
      <section className="card">
        <label className="field">
          <span>API base URL</span>
          <input type="text" value={import.meta.env.VITE_ABBY_API_BASE_URL ?? 'http://localhost:8000/api/v1'} readOnly />
        </label>
        <label className="field">
          <span>Authentication</span>
          <input type="text" value="API key header (managed externally for now)" readOnly />
        </label>
      </section>
    </div>
  );
}
