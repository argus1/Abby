export const config = {
  apiBaseUrl: import.meta.env.VITE_ABBY_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  apiKey: import.meta.env.VITE_ABBY_API_KEY ?? 'dev-local-key',
};
