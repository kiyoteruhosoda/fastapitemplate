import type { Page } from '@playwright/test'

import { ADMIN } from './admin'
import { INTENDED_FAULT_HEADER, expect, test } from './fixtures'

/**
 * 前段（edge）が閉じたときのアプリ内の画面（ADR-0080 §10）。
 *
 * edge の代わりに、API への要求へ edge と同じ形の 503 を返す。⚠ Service Worker に制御された
 * 画面で確かめる ——読み込み直しても手元の index.html が出るので、edge のメンテナンス画面は
 * 見えない。そこから API の 503 で切り替わることがこの試験の本題。
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

test('閉じると読み込み直してもメンテナンスの画面になり、開くと元の画面へ戻る', async ({ page }) => {
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

test('上流が居ないだけのときは「停止中」の文', async ({ page }) => {
  await page.goto('/login')
  await closeTheService(page, {
    error: 'service_unavailable',
    reason: 'stopped',
    host: '127.0.0.1',
  })
  await page.reload()

  await expect(page.getByRole('heading', { name: '停止中です' })).toBeVisible()
})
