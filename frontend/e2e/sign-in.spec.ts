import type { Page } from '@playwright/test'

import { ADMIN } from './admin'
import { expect, test } from './fixtures'

async function signIn(page: Page, password: string): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('メールアドレス').fill(ADMIN.email)
  await page.getByLabel('パスワード', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'ログイン', exact: true }).click()
}

test('ログインしていなければログイン画面へ送られる', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'ログイン' })).toBeVisible()
})

test('パスワードを間違えるとログイン画面に留まる', async ({ page }) => {
  await signIn(page, 'not-the-password')

  await expect(page.getByText('メールアドレスまたはパスワードが正しくありません。')).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
})

test('ログインは読み込み直しても続き、ログアウトで終わる', async ({ page }) => {
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
