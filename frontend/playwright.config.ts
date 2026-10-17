import { defineConfig, devices } from '@playwright/test'

import { ADMIN } from './e2e/admin'

/**
 * E2E（実ブラウザの煙試験）の設定（ADR-0054）。
 *
 * 本物のサーバー（FastAPI ＋ 使い捨ての SQLite ＋ ビルドした画面）を立て、Chromium で
 * 画面を通す。Vitest（jsdom）には Service Worker が無いので、SW の働きはここでしか見られない。
 *
 *   npm run test:e2e
 *
 * ⚠ 画面のビルドとサーバーの起動は webServer が毎回行う（立ちっぱなしのサーバーを使い回さない）。
 */
const PORT = process.env.E2E_PORT ?? '8100'
const BASE_URL = `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // 試験は 1 つのサーバーと DB を共有し、service-worker.spec.ts は配った sw.js を書き換える。
  // 並べて走らせない。
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  // CI では落ちたときに trace 付きの HTML レポートを持ち帰る（e2e.yml）。
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: BASE_URL,
    // 試験は画面の日本語の文言で要素を探す。
    locale: 'ja-JP',
    // retries が 0 なので、1 回目の失敗の trace を残す。
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Playwright のブラウザが入っていない手元では、PLAYWRIGHT_CHROMIUM_EXECUTABLE で
        // 入っている Chrome を指す。CI（Playwright の像）では使わない。
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
    // 画面のビルドとマイグレーションを含む。
    timeout: 300_000,
    env: {
      E2E_PORT: PORT,
      ADMIN_INITIAL_PASSWORD: ADMIN.password,
    },
  },
})
