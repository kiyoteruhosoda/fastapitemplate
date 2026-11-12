/**
 * Maintenance / outage screen (ADR-0080 §10).
 *
 * The recheck is a fake; only "what is shown", "when it rechecks" and "whether it disappears
 * once open" are checked.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import { localZoneLabel } from '../services/localTime'
import {
  reportOutage,
  reportReopened,
  resetOutageForTests,
  type Outage,
} from '../services/maintenance'
import type { UiSettings } from '../services/uiSettings'
import { ToastProvider, useToast } from './ToastNotification'
import { MaintenanceGate, MaintenanceScreen, RECHECK_INTERVAL_MS } from './MaintenanceScreen'

const SETTINGS: UiSettings = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

const UNTIL = '2026-10-28T19:30:00Z'

const DECLARED: Outage = {
  reason: 'maintenance',
  title: 'T',
  body: 'B',
  message: 'Test.',
  until: UNTIL,
}

function renderScreen(outage: Outage, check = vi.fn(() => Promise.resolve())) {
  render(
    <I18nProvider settings={SETTINGS}>
      <MaintenanceScreen outage={outage} check={check} />
    </I18nProvider>,
  )
  return check
}

/** Expected return in the viewer's time zone (formatted as on screen, with the zone). */
function localUntil(): string {
  const at = new Date(UNTIL)
  const shown = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(
    at,
  )
  return `${shown} ${localZoneLabel(at)}`
}

describe('MaintenanceScreen', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows the declared heading, body and reason, and the expected return in the local zone', () => {
    renderScreen(DECLARED)

    expect(screen.getByRole('heading', { name: 'T' })).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
    expect(screen.getByText('Reason: Test.')).toBeInTheDocument()
    expect(screen.getByText(`Expected back around ${localUntil()}`)).toBeInTheDocument()
  })

  it('uses default text for the old edge format (no title or body)', () => {
    renderScreen({ ...DECLARED, title: null, body: null })

    expect(screen.getByRole('heading', { name: 'Under maintenance' })).toBeInTheDocument()
    expect(screen.getByText(/down for scheduled maintenance/)).toBeInTheDocument()
    expect(screen.getByText('Reason: Test.')).toBeInTheDocument()
  })

  it('uses the "stopped" text when the upstream is merely absent', () => {
    renderScreen({ reason: 'stopped', title: null, body: null, message: null, until: null })

    expect(screen.getByRole('heading', { name: 'Service stopped' })).toBeInTheDocument()
    expect(screen.queryByText(/Reason:/)).toBeNull()
    expect(screen.queryByText(/Expected back/)).toBeNull()
  })

  it('omits an unparsable deadline', () => {
    renderScreen({ ...DECLARED, until: 'soon' })

    expect(screen.queryByText(/Expected back/)).toBeNull()
  })

  it('rechecks immediately when pressed', () => {
    const check = renderScreen(DECLARED)

    fireEvent.click(screen.getByRole('button', { name: 'Check now' }))

    expect(check).toHaveBeenCalledTimes(1)
  })

  it('rechecks every minute', () => {
    vi.useFakeTimers()
    try {
      const check = renderScreen(DECLARED)
      expect(check).not.toHaveBeenCalled()

      act(() => {
        vi.advanceTimersByTime(RECHECK_INTERVAL_MS)
      })

      expect(check).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('MaintenanceGate', () => {
  beforeEach(() => {
    resetOutageForTests()
  })

  afterEach(() => {
    resetOutageForTests()
  })

  it('shows only while closed and disappears once open', () => {
    render(
      <I18nProvider settings={SETTINGS}>
        <MaintenanceGate check={() => Promise.resolve()} />
      </I18nProvider>,
    )
    expect(screen.queryByRole('alert')).toBeNull()

    act(() => {
      reportOutage(DECLARED)
    })
    expect(screen.getByRole('heading', { name: 'T' })).toBeInTheDocument()

    act(() => {
      reportReopened()
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('toasts while closed', () => {
  beforeEach(() => {
    resetOutageForTests()
  })

  afterEach(() => {
    resetOutageForTests()
  })

  function Notifier() {
    const { notify } = useToast()
    return (
      <button
        type="button"
        onClick={() => {
          notify('error', 'failed')
        }}
      >
        fail
      </button>
    )
  }

  it('does not show error toasts (shows them as before when not closed)', () => {
    render(
      <ToastProvider>
        <Notifier />
      </ToastProvider>,
    )

    reportOutage(DECLARED)
    fireEvent.click(screen.getByRole('button', { name: 'fail' }))
    expect(screen.queryByText('failed')).toBeNull()

    reportReopened()
    fireEvent.click(screen.getByRole('button', { name: 'fail' }))
    expect(screen.getByText('failed')).toBeInTheDocument()
  })
})
