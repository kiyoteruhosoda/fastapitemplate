/**
 * Running button (ADR-0080 §5).
 *
 * Verifies three things: "from press until done a spinner shows and it cannot be pressed",
 * "it returns to normal when done", and "pressing again while running does not run twice".
 * The spinning look itself is CSS, so it is not checked here.
 *
 * Also guards that the label stays as an element while running (= the button width does not
 * change). Hiding it is CSS's job, but reverting to swapping the label would shift the width.
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

/** Minimal screen combined with `usePendingAction`, as in real usage. */
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
  it('shows a spinner and disables while running, and restores when done', async () => {
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
    // The label remains as a placeholder (swapping it would change the button width).
    expect(screen.getByText('Save')).toBeInTheDocument()

    finish()

    await waitFor(() => {
      expect(button).not.toBeDisabled()
    })
    expect(screen.queryByText('Processing...')).not.toBeInTheDocument()
  })

  it('does not run twice when pressed again while running', async () => {
    let finish = (): void => undefined
    const action = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve
        }),
    )
    const button = renderSubject(action)

    fireEvent.click(button)
    // `disabled` waits for a render, so check that presses in the same frame are also stopped.
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
