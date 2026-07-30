/**
 * 狭い画面向けナビゲーション（ドロワー）の開閉。
 *
 * 画面幅による見た目の切り替えは CSS（`index.css` のメディアクエリ）が担い、
 * jsdom はメディアクエリを適用しない。ここで検証するのは、メディアクエリが
 * 解釈する状態 — メニューボタンの `aria-expanded` と `nav[data-open]` — が
 * 操作どおりに変わることと、閉じる操作が揃っていることに絞る。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import type { Me } from '../store/AuthContext'
import { AuthProvider } from '../store/AuthContext'
import { ThemeProvider } from '../theme'
import { AppLayout } from './AppLayout'

const ME: Me = {
  user_id: 1,
  email: 'admin@example.com',
  username: 'admin',
  scopes: ['dashboard:view', 'item:view'],
}

vi.mock('../services/api', () => ({
  api: {
    get: vi.fn(() => Promise.resolve(ME)),
    post: vi.fn(() => Promise.resolve({})),
  },
  hasTokens: () => true,
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  errorMessageKey: () => 'errors.unknown',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <I18nProvider settings={SETTINGS}>
        <ThemeProvider settings={SETTINGS}>
          <AuthProvider>
            <AppLayout>
              <p>content</p>
            </AppLayout>
          </AuthProvider>
        </ThemeProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
}

/** ドロワーが開くのはサインイン後なので、`/me` の解決を待ってから操作する。 */
async function renderSignedIn() {
  renderLayout()
  await waitFor(() => {
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  })
  return { nav: () => screen.getByRole('navigation', { name: 'Menu' }) }
}

function toggle() {
  return screen.getByRole('button', { name: 'Menu' })
}

function overlay() {
  return screen.getByTestId('nav-overlay')
}

function click(element: HTMLElement) {
  act(() => {
    element.click()
  })
}

describe('AppLayout のナビゲーション', () => {
  beforeEach(() => {
    // Footer が /info を読む。ネットワークへ出さない。
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false } as Response)),
    )
    // jsdom は matchMedia を持たない（ThemeProvider が OS の配色を見る）。
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    )
  })

  it('既定では閉じている', async () => {
    const { nav } = await renderSignedIn()
    expect(nav()).toHaveAttribute('data-open', 'false')
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    // 開いていないあいだはオーバーレイを描かない（本文を触れる）。
    expect(screen.queryByTestId('nav-overlay')).not.toBeInTheDocument()
  })

  it('メニューボタンで開き、もう一度押すと閉じる', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    expect(nav()).toHaveAttribute('data-open', 'true')
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')

    click(toggle())
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('オーバーレイをタップすると閉じる', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    click(overlay())
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('ドロワー内の閉じるボタンで閉じる', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    click(screen.getByRole('button', { name: 'Close menu' }))
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('Esc で閉じる', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('ナビゲーションのリンクを選ぶと閉じる', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    click(screen.getByRole('link', { name: 'Items' }))
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('保有していない scope の項目は出さない', async () => {
    const { nav } = await renderSignedIn()
    expect(nav()).toHaveAttribute('data-open', 'false')
    expect(screen.getByRole('link', { name: 'Items' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument()
  })
})
