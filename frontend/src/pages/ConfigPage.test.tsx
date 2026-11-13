/** System settings page. A rejected save is not silently discarded (ADR-0101). */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { ConfigPage } from './ConfigPage'

const { apiGet, apiPost, apiPut } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost, put: apiPut },
  errorMessageKey: () => 'error.invalid_setting_value',
}))

vi.mock('../store/AuthContext', () => ({
  useAuth: () => ({ hasScope: () => true }),
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

const ITEMS = [
  {
    key: 'REFRESH_TOKEN_EXPIRES_SECONDS',
    category: 'auth',
    label: 'Refresh token lifetime (seconds)',
    value_type: 'integer',
    value: 1209600,
    default: 1209600,
    env_fallback: false,
    stored: false,
    restart_scopes: [],
  },
  {
    key: 'REFRESH_TOKEN_SLIDING_ENABLED',
    category: 'auth',
    label: 'Extend the refresh token lifetime on each refresh',
    value_type: 'boolean',
    value: true,
    default: true,
    env_fallback: false,
    stored: false,
    restart_scopes: [],
  },
]

function renderPage() {
  render(
    <I18nProvider settings={SETTINGS}>
      <ToastProvider>
        <ConfigPage />
      </ToastProvider>
    </I18nProvider>,
  )
}

describe('ConfigPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiGet.mockResolvedValue(ITEMS)
  })

  it('shows the period and whether it extends, with an unset extension shown as on', async () => {
    renderPage()
    expect(await screen.findByDisplayValue('1209600')).toBeInTheDocument()
    expect(document.getElementById('config-REFRESH_TOKEN_SLIDING_ENABLED')).toBeChecked()
  })

  it('shows the reason for a rejected save and keeps the input', async () => {
    apiPut.mockRejectedValue(new Error('refused'))
    renderPage()
    const period = await screen.findByDisplayValue('1209600')

    fireEvent.change(period, { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('That value cannot be used.')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByDisplayValue('0')).toBeInTheDocument()
    })
  })
})
