import { readFileSync, writeFileSync } from 'node:fs'

import type { Page } from '@playwright/test'

import { expect, test } from './fixtures'

/** サーバーが配っている Service Worker（webServer がビルドした frontend/dist）。 */
const SERVICE_WORKER_FILE = new URL('../dist/sw.js', import.meta.url)

/**
 * Service Worker に制御された画面を開く。
 *
 * 初めて開いたタブは、登録した Service Worker にまだ制御されていない。
 * 登録が済むのを待ってから読み込み直す。
 */
async function openControlledPage(page: Page): Promise<void> {
  await page.goto('/login')
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })
  await page.reload()
  await expect
    .poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null))
    .toBe(true)
}

test('Service Worker の下でも、無い API は SPA の画面にならず 404 のまま', async ({ page }) => {
  await openControlledPage(page)

  const response = await page.goto('/api/e2e-no-such-endpoint')

  expect(response?.status()).toBe(404)
  expect(response?.fromServiceWorker()).toBe(false)
  expect(await response?.headerValue('content-type')).toContain('application/json')
})

test('sw.js が変わると新しい版の知らせが出て、押すと入れ替わる', async ({ page }) => {
  await openControlledPage(page)

  // 新しい版を配ったのと同じことを起こす（中身が 1 バイトでも違えば別の版）。
  const original = readFileSync(SERVICE_WORKER_FILE, 'utf-8')
  writeFileSync(SERVICE_WORKER_FILE, `${original}\n// e2e: ${String(Date.now())}\n`)
  try {
    // 見張りは 30 分ごと・タブが手前へ戻ったときに確かめに行く。待たずにここで起こす。
    await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      await registration?.update()
    })
    const notice = page.getByText('新しい版があります。')
    await expect(notice).toBeVisible()

    const reloaded = page.waitForEvent('load')
    await page.getByRole('button', { name: '再読み込み' }).click()
    await reloaded

    await expect(notice).toBeHidden()
    const state = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      return {
        waiting: registration?.waiting != null,
        controlled: navigator.serviceWorker.controller !== null,
      }
    })
    expect(state).toEqual({ waiting: false, controlled: true })
  } finally {
    writeFileSync(SERVICE_WORKER_FILE, original)
  }
})
