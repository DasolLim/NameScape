import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: { baseURL: 'http://localhost:5173', trace: 'on-first-retry' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  // Both servers: the smoke test asserts the real API is reachable through
  // the Vite proxy, so a frontend-only run cannot pass.
  webServer: [
    {
      command: 'cd ../api && uv run uvicorn app.main:app --port 8000',
      // Local dev has no Anthropic key, and moderation fails closed without
      // one. This bypass is development only and must never be set in prod.
      env: { MODERATION_DEV_BYPASS: 'true' },
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
})
