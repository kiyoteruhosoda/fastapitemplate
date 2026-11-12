/**
 * Content settings page (ADR-0085).
 *
 * Checks that options use the dictionary text, only changed items are sent, "Reset to default" sends null,
 * and view-only users (only content-settings:view) get disabled inputs and no save button.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import type * as ApiModule from '../services/api'
import { ContentSettingsPage } from './ContentSettingsPage'

const { apiGet, apiPut, scopes } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  scopes: { granted: [] as string[] },
}))

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  api: { get: apiGet, post: vi.fn(), put: apiPut, delete: vi.fn() },
}))

vi.mock('../store/AuthContext', () => ({
  useAuth: () => ({
    hasScope: (...codes: string[]) => codes.every((c) => scopes.granted.includes(c)),
  }),
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

const ORDER = {
  key: 'item_list_order',
  value_type: 'choice',
  value: 'name',
  default: 'oldest',
  stored: true,
  choices: ['oldest', 'newest', 'name'],
  minimum: null,
  maximum: null,
}

async function renderPage() {
  apiGet.mockResolvedValue([ORDER])
  render(
    <I18nProvider settings={SETTINGS}>
      <ToastProvider>
        <ContentSettingsPage />
      </ToastProvider>
    </I18nProvider>,
  )
  return screen.findByLabelText(/Order of the item list/)
}

describe('ContentSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    scopes.granted = ['content-settings:view', 'content-settings:write']
    apiPut.mockResolvedValue([ORDER])
  })

  it('shows options with dictionary text and sends only changed items', async () => {
    const select = await renderPage()
    expect(select).toHaveValue('name')
    expect(screen.getByRole('option', { name: 'Newest first' })).toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'newest' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/api/admin/content-settings', {
        values: { item_list_order: 'newest' },
      })
    })
  })

  it('sends null for "Reset to default"', async () => {
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Reset to default' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/api/admin/content-settings', {
        values: { item_list_order: null },
      })
    })
  })

  it('disables inputs and hides the save button for view-only users', async () => {
    scopes.granted = ['content-settings:view']
    const select = await renderPage()
    expect(select).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reset to default' })).not.toBeInTheDocument()
  })
})
