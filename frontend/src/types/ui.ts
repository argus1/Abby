export type StubStatus = 'planned' | 'stubbed' | 'available';

export interface ServiceLayerModule {
  title: string;
  service: string;
  status: StubStatus;
  bullets: string[];
}
