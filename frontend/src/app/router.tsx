import { createBrowserRouter } from 'react-router-dom';

import { AppLayout } from '../components/layout/AppLayout';
import { BatchJobPage } from '../pages/BatchJobPage';
import { ComparePage } from '../pages/ComparePage';
import { DashboardPage } from '../pages/DashboardPage';
import { PredictionPage } from '../pages/PredictionPage';
import { ProjectPage } from '../pages/ProjectPage';
import { SettingsPage } from '../pages/SettingsPage';
import { StructurePage } from '../pages/StructurePage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'projects/:projectId', element: <ProjectPage /> },
      { path: 'projects/:projectId/new-prediction', element: <ProjectPage /> },
      { path: 'projects/:projectId/structures/:structureId', element: <StructurePage /> },
      { path: 'predictions/:predictionId', element: <PredictionPage /> },
      { path: 'projects/:projectId/batch-jobs/:jobId', element: <BatchJobPage /> },
      { path: 'compare/:leftPredictionId/:rightPredictionId', element: <ComparePage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);
