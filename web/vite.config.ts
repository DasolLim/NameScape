import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // MapLibre ships a web worker the dep optimizer cannot pre-bundle.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // e2e/*.spec.ts belongs to Playwright, not Vitest.
    exclude: ['node_modules/**', 'e2e/**'],
  },
})
