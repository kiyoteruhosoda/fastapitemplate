import type { Page } from '@playwright/test'

import { ADMIN } from './admin'
import { expect, test } from './fixtures'

async function signIn(page: Page, password: string): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('メールアドレス').fill(ADMIN.email)
  await page.getByLabel('パスワード', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
}

test('redirects to the sign-in screen when not signed in', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'ログイン' })).toBeVisible()
})

test('stays on the sign-in screen with a wrong password', async ({ page }) => {
  await signIn(page, 'not-the-password')

  await expect(page.getByText('メールアドレスまたはパスワードが正しくありません。')).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
})

test('sign-in survives a reload and ends with sign-out', async ({ page }) => {
  await signIn(page, ADMIN.password)
  const dashboard = page.getByRole('heading', { name: '管理ダッシュボード' })
  await expect(dashboard).toBeVisible()

  await page.reload()
  await expect(dashboard).toBeVisible()

  await page.getByRole('button', { name: 'ログアウト' }).click()
  await expect(page).toHaveURL(/\/login$/)

  await page.goto('/')
  await expect(page).toHaveURL(/\/login$/)
})
