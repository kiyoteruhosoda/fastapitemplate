import { defineConfig, devices } from '@playwright/test'

import { ADMIN } from './e2e/admin'

/**
 * E2E (real-browser smoke tests) configuration (ADR-0072 §6).
 *
 * Starts a real server (FastAPI + throwaway SQLite + built frontend) and drives the screens in
 * Chromium. Vitest (jsdom) has no Service Worker, so SW behaviour can only be checked here.
 *
 *   npm run test:e2e
 *
 * ⚠ webServer builds the frontend and starts the server every run (no reuse of a running server).
 */
const PORT = process.env.E2E_PORT ?? '8100'
const BASE_URL = `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // Tests share one server and DB, and service-worker.spec.ts rewrites the served sw.js.
  // Don't run them in parallel.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  // On CI, keep an HTML report with traces when tests fail (e2e.yml).
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: BASE_URL,
    // Tests find elements by the Japanese text on screen.
    locale: 'ja-JP',
    // retries is 0, so keep the trace of the first failure.
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // On local machines without Playwright's browsers, point PLAYWRIGHT_CHROMIUM_EXECUTABLE
        // at an installed Chrome. Not used on CI (the Playwright image).
        ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
          ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } }
          : {}),
      },
    },
  ],
  webServer: {
    command: 'npm run build && bash e2e/run-server.sh',
    url: `${BASE_URL}/readyz`,
    reuseExistingServer: false,
    // Includes the frontend build and migrations.
    timeout: 300_000,
    env: {
      E2E_PORT: PORT,
      ADMIN_INITIAL_PASSWORD: ADMIN.password,
    },
  },
})
