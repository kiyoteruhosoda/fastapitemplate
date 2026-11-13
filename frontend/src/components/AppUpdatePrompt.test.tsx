/**
 * New-version notice (ADR-0080 §7).
 *
 * jsdom has no Service Worker, so a fake watcher is passed in and only "nothing is shown until
 * notified" and "nothing is swapped until pressed" are verified.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import type { UpdateReadyListener, WatchForUpdate } from '../services/appUpdate'
import type { UiSettings } from '../services/uiSettings'
import { AppUpdatePrompt } from './AppUpdatePrompt'

const SETTINGS: UiSettings = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderPrompt() {
  const watcher: { notify?: UpdateReadyListener } = {}
  const watch: WatchForUpdate = (onUpdateReady) => {
    watcher.notify = onUpdateReady
  }

  const view = render(
    <I18nProvider settings={SETTINGS}>
      <AppUpdatePrompt watch={watch} />
    </I18nProvider>,
  )

  return { watcher, view }
}

describe('AppUpdatePrompt', () => {
  it('shows nothing until a new version is waiting', () => {
    renderPrompt()

    expect(screen.queryByRole('status')).toBeNull()
  })

  it('shows the notice once waiting and swaps only when pressed', () => {
    const { watcher } = renderPrompt()
    const apply = vi.fn()

    act(() => {
      watcher.notify?.(apply)
    })

    expect(screen.getByText('A new version is available.')).toBeInTheDocument()
    expect(apply).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Reload' }))

    expect(apply).toHaveBeenCalledTimes(1)
  })

  it('passes the height that pushes the header down only while shown', () => {
    const { watcher, view } = renderPrompt()
    const root = document.documentElement

    expect(root.style.getPropertyValue('--update-bar-height')).toBe('')

    act(() => {
      watcher.notify?.(vi.fn())
    })

    expect(root.style.getPropertyValue('--update-bar-height')).toMatch(/^\d+px$/)

    view.unmount()

    expect(root.style.getPropertyValue('--update-bar-height')).toBe('')
  })
})
