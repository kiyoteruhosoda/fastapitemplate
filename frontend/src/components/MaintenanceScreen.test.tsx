/**
 * メンテナンス中・停止中の画面（ADR-0080 §10）。
 *
 * 確かめ直しは偽物を渡し、「何を出すか」「いつ確かめ直すか」「開いたら消えるか」だけを見る。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
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

/** 閲覧者の時間帯での戻りの見込み（画面と同じ書き方）。 */
function localUntil(): string {
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(UNTIL),
  )
}

describe('MaintenanceScreen', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('宣言の見出し・本文・理由と、戻りの見込みを手元の時間帯で出す', () => {
    renderScreen(DECLARED)

    expect(screen.getByRole('heading', { name: 'T' })).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
    expect(screen.getByText('Reason: Test.')).toBeInTheDocument()
    expect(screen.getByText(`Expected back around ${localUntil()}`)).toBeInTheDocument()
  })

  it('古い edge の形（title・body 無し）でも既定の文で出す', () => {
    renderScreen({ ...DECLARED, title: null, body: null })

    expect(screen.getByRole('heading', { name: 'Under maintenance' })).toBeInTheDocument()
    expect(screen.getByText(/down for scheduled maintenance/)).toBeInTheDocument()
    expect(screen.getByText('Reason: Test.')).toBeInTheDocument()
  })

  it('上流が居ないだけのときは「停止中」の文', () => {
    renderScreen({ reason: 'stopped', title: null, body: null, message: null, until: null })

    expect(screen.getByRole('heading', { name: 'Service stopped' })).toBeInTheDocument()
    expect(screen.queryByText(/Reason:/)).toBeNull()
    expect(screen.queryByText(/Expected back/)).toBeNull()
  })

  it('読めない期限は出さない', () => {
    renderScreen({ ...DECLARED, until: 'soon' })

    expect(screen.queryByText(/Expected back/)).toBeNull()
  })

  it('押せばすぐ確かめ直す', () => {
    const check = renderScreen(DECLARED)

    fireEvent.click(screen.getByRole('button', { name: 'Check now' }))

    expect(check).toHaveBeenCalledTimes(1)
  })

  it('1 分ごとに確かめ直す', () => {
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

  it('閉じている間だけ出て、開いたら消える', () => {
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

describe('閉じている間のトースト', () => {
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

  it('エラーのトーストは出さない（閉じていなければ今までどおり出す）', () => {
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
