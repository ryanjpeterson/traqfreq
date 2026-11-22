import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In dev, the API runs on the FastAPI app (uv run traqfreq, :4492).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:4492' } },
  build: { outDir: 'dist', emptyOutDir: true },
});
