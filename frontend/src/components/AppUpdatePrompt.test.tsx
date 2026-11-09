/**
 * 新しい版の知らせ（ADR-0080 §7）。
 *
 * Service Worker そのものは jsdom に無いので、見張り役は偽物を渡して
 * 「知らせが来るまで出さない」「押すまで入れ替えない」だけを検証する。
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
  it('新しい版が待機するまで何も出さない', () => {
    renderPrompt()

    expect(screen.queryByRole('status')).toBeNull()
  })

  it('待機したら知らせを出し、押されたときだけ入れ替える', () => {
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

  it('出ている間だけ、ヘッダーを下げる高さを渡す', () => {
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
