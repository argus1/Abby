import type { ServiceLayerModule } from '../types/ui';

export function ServiceLayerCard({ module }: { module: ServiceLayerModule }) {
  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h3>{module.title}</h3>
          <p className="muted">{module.service}</p>
        </div>
        <span className={`badge badge-${module.status}`}>{module.status}</span>
      </div>
      <ul className="bullet-list">
        {module.bullets.map((bullet) => (
          <li key={bullet}>{bullet}</li>
        ))}
      </ul>
    </section>
  );
}
