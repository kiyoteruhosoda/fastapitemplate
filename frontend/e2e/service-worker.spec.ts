import { readFileSync, writeFileSync } from 'node:fs'

import type { Page } from '@playwright/test'

import { expect, test } from './fixtures'

/** The Service Worker served by the server (frontend/dist built by webServer). */
const SERVICE_WORKER_FILE = new URL('../dist/sw.js', import.meta.url)

/**
 * Open a screen controlled by the Service Worker.
 *
 * A freshly opened tab is not yet controlled by the registered Service Worker.
 * Wait for registration to finish, then reload.
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

test('under the Service Worker, a missing API stays 404 instead of the SPA', async ({ page }) => {
  await openControlledPage(page)

  const response = await page.goto('/api/e2e-no-such-endpoint')

  expect(response?.status()).toBe(404)
  expect(response?.fromServiceWorker()).toBe(false)
  expect(await response?.headerValue('content-type')).toContain('application/json')
})

test('when sw.js changes, a new-version notice appears and swaps the version', async ({ page }) => {
  await openControlledPage(page)

  // Simulate deploying a new version (a single differing byte makes it a different version).
  const original = readFileSync(SERVICE_WORKER_FILE, 'utf-8')
  writeFileSync(SERVICE_WORKER_FILE, `${original}\n// e2e: ${String(Date.now())}\n`)
  try {
    // The watcher checks every 30 minutes and when the tab returns to the foreground. Trigger it here instead of waiting.
    await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      await registration?.update()
    })
    const notice = page.getByText('新しい版があります。')
    await expect(notice).toBeVisible()
    // Shown in the top banner, not at the bottom of the screen (ADR-0106).
    const bar = await notice.locator('xpath=..').boundingBox()
    expect(bar?.y).toBe(0)

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
