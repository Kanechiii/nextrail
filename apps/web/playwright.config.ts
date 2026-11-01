import { defineConfig, devices } from '@playwright/test'

// Dedicated test services never reuse a developer's running dashboard or database.
const apiPort = 18000
const webPort = 15173
const apiUrl = `http://127.0.0.1:${apiPort}`
const webUrl = `http://127.0.0.1:${webPort}`

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: webUrl, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    {
      command: `python -m uvicorn nextrail_api.main:app --app-dir ../../services/api --host 127.0.0.1 --port ${apiPort}`,
      url: `${apiUrl}/health`,
      reuseExistingServer: false,
      env: { NEXTRAIL_DB_PATH: ':memory:' },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
      url: webUrl,
      reuseExistingServer: false,
      env: { NEXTRAIL_DEV_API_TARGET: apiUrl, VITE_API_BASE_URL: '/api' },
    },
  ],
})
