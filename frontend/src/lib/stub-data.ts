import type { ServiceLayerModule } from '../types/ui';

export const serviceLayerModules: ServiceLayerModule[] = [
  {
    title: 'Structure parsing and validation',
    service: 'services/structures.py',
    status: 'available',
    bullets: [
      'Parser selection for PDB/mmCIF',
      'Disjoint partner validation',
      'Multi-model and gap warnings',
      'Heavy/light antibody chain grouping',
    ],
  },
  {
    title: 'Feature extraction',
    service: 'services/feature_extraction.py',
    status: 'available',
    bullets: [
      'Inter-partner contact detection',
      'Charged/polar/apolar contact bins',
      'RSA and NIS-style composition features',
      'Explainability descriptor packaging',
    ],
  },
  {
    title: 'Baseline models',
    service: 'services/baseline_models.py',
    status: 'available',
    bullets: [
      'Deterministic baseline scoring',
      'ΔG ↔ Kd conversion helpers',
      'Versioned coefficient sets',
      'Provenance-linked model output',
    ],
  },
  {
    title: 'Exports and scientist artifacts',
    service: 'services/exports.py',
    status: 'available',
    bullets: [
      'Contact list download',
      'PyMOL selection script artifact',
      'Descriptor bundle snapshots',
      'CSV/JSON result exports',
    ],
  },
];

export const workflowSteps = [
  { id: 'upload', label: 'Upload structure', state: 'available' },
  { id: 'validate', label: 'Validate chains', state: 'available' },
  { id: 'features', label: 'Extract interface features', state: 'available' },
  { id: 'baseline', label: 'Run baseline affinity model', state: 'available' },
  { id: 'result', label: 'Review prediction + exports', state: 'available' },
];

export const stubPrediction = {
  projectName: 'HER2 Optimization Round 3',
  structureName: 'af3_candidate_017.cif',
  partner1: ['H', 'L'],
  partner2: ['A'],
  exampleOutputs: {
    contacts: ['charged-polar contacts', 'apolar-apolar contacts', 'interface residue count'],
    surface: ['relative solvent accessibility', 'surface composition buckets'],
    baseline: ['ΔG baseline', 'log(K) baseline', 'Kd derivation'],
    exports: ['contact list CSV', 'PyMOL script', 'JSON descriptor bundle'],
    exportNotes: ['Exports preserve contact cutoff provenance for auditability'],
  },
};
