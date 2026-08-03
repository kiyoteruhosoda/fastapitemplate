/**
 * 実行中のボタン（ADR-0022）。
 *
 * 検証するのは「押してから終わるまでスピナーが出て押せなくなる」「終われば元に
 * 戻る」「実行中に続けて押しても 2 度目は走らない」の 3 点。回る見た目そのものは
 * CSS が担うのでここでは見ない。
 *
 * ラベルが実行中も要素として残ること（＝ボタンの幅が変わらないこと）もここで守る。
 * 隠すのは CSS の役目だが、ラベルを差し替える実装に戻ると幅が動いてしまう。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { usePendingAction } from '../hooks/usePendingAction'
import { I18nProvider } from '../i18n'
import type { UiSettings } from '../services/uiSettings'
import { ActionButton } from './ActionButton'

const SETTINGS: UiSettings = {
  languages: ['en'],
  default_locale: 'en',
  default_theme: 'light',
}

/** `usePendingAction` と組んだ、実際の使い方どおりの最小の画面。 */
function Subject({ action }: { action: () => Promise<void> }) {
  const [run, pending] = usePendingAction(action)
  return (
    <ActionButton type="button" pending={pending} onClick={run}>
      Save
    </ActionButton>
  )
}

function renderSubject(action: () => Promise<void>) {
  render(
    <I18nProvider settings={SETTINGS}>
      <Subject action={action} />
    </I18nProvider>,
  )
  return screen.getByRole('button', { name: /Save/ })
}

describe('ActionButton', () => {
  it('実行中はスピナーを出して押せなくし、終われば元に戻る', async () => {
    let finish = (): void => undefined
    const action = () =>
      new Promise<void>((resolve) => {
        finish = resolve
      })
    const button = renderSubject(action)

    expect(button).not.toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByText('Processing...')).not.toBeInTheDocument()

    fireEvent.click(button)

    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toBeDisabled()
    expect(screen.getByText('Processing...')).toBeInTheDocument()
    // ラベルは place holder として残る（差し替えるとボタンの幅が動く）。
    expect(screen.getByText('Save')).toBeInTheDocument()

    finish()

    await waitFor(() => {
      expect(button).not.toBeDisabled()
    })
    expect(screen.queryByText('Processing...')).not.toBeInTheDocument()
  })

  it('実行中に続けて押しても 2 度目は走らない', async () => {
    let finish = (): void => undefined
    const action = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve
        }),
    )
    const button = renderSubject(action)

    fireEvent.click(button)
    // `disabled` は描画を待つので、同じフレームで続けて押された分も止まることを見る。
    fireEvent.click(button)
    expect(action).toHaveBeenCalledTimes(1)

    finish()
    await waitFor(() => {
      expect(button).not.toBeDisabled()
    })

    fireEvent.click(button)
    expect(action).toHaveBeenCalledTimes(2)
  })
})
