import type { Page } from '@playwright/test'

import { ADMIN } from './admin'
import { INTENDED_FAULT_HEADER, expect, test } from './fixtures'

/**
 * The in-app screen shown when the front tier (edge) is closed (ADR-0080 §10).
 *
 * Instead of the edge, API requests get a 503 shaped like the edge's. ⚠ Checked on a screen
 * controlled by the Service Worker: reloading still shows the local index.html, so the edge's
 * maintenance page never appears. Switching from there on the API's 503 is the point of this test.
 */
const MAINTENANCE = {
  error: 'service_unavailable',
  reason: 'maintenance',
  until: '2026-10-28T19:30:00Z',
  message: 'Test.',
  title: 'T',
  body: 'B',
}

async function closeTheService(page: Page, body: object): Promise<void> {
  await page.route('**/api/**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      headers: { 'Retry-After': '300', 'Cache-Control': 'no-store', [INTENDED_FAULT_HEADER]: '1' },
      body: JSON.stringify(body),
    }),
  )
}

async function signInUnderServiceWorker(page: Page): Promise<void> {
  await page.goto('/login')
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })
  await page.getByLabel('メールアドレス').fill(ADMIN.email)
  await page.getByLabel('パスワード', { exact: true }).fill(ADMIN.password)
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
  await expect(page.getByRole('heading', { name: '管理ダッシュボード' })).toBeVisible()
  await page.reload()
  await expect
    .poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null))
    .toBe(true)
}

test('when closed, the maintenance screen shows even after reload; when reopened, the original screen returns', async ({ page }) => {
  await signInUnderServiceWorker(page)
  const dashboard = page.getByRole('heading', { name: '管理ダッシュボード' })
  await expect(dashboard).toBeVisible()

  await closeTheService(page, MAINTENANCE)
  const navigation = await page.reload()
  expect(navigation?.fromServiceWorker()).toBe(true)

  await expect(page.getByRole('heading', { name: 'T' })).toBeVisible()
  await expect(page.getByText('B', { exact: true })).toBeVisible()
  await expect(page.getByText('理由: Test.')).toBeVisible()
  await expect(page.getByText(/ごろに戻る見込みです/)).toBeVisible()
  await expect(dashboard).toBeHidden()
  await expect(page.locator('.toast-error')).toHaveCount(0)

  await page.unroute('**/api/**')
  await page.getByRole('button', { name: 'いま確かめる' }).click()

  await expect(page.getByRole('heading', { name: 'T' })).toBeHidden()
  await expect(dashboard).toBeVisible()
})

test('when only the upstream is missing, the "stopped" text is shown', async ({ page }) => {
  await page.goto('/login')
  await closeTheService(page, {
    error: 'service_unavailable',
    reason: 'stopped',
    host: '127.0.0.1',
  })
  await page.reload()

  await expect(page.getByRole('heading', { name: '停止中です' })).toBeVisible()
})
