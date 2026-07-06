import { Outlet, NavLink } from 'react-router-dom';

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>Abby</h1>
        <p className="sidebar-copy">Affinity prediction workflow with service-layer feature stubs.</p>
        <nav>
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/projects/demo-project">Project</NavLink>
          <NavLink to="/predictions/demo-prediction">Prediction</NavLink>
          <NavLink to="/projects/demo-project/batch-jobs/demo-job">Batch Job</NavLink>
          <NavLink to="/compare/demo-left/demo-right">Compare</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
