/**
 * Show / hide toggle of the password field.
 *
 * Verifies three things: "masked by default", "pressing shows plain text and pressing again
 * reverts", and "the value is not lost when toggling". The look (border) is CSS, so not checked.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'

import { I18nProvider } from '../i18n'
import type { UiSettings } from '../services/uiSettings'
import { PasswordInput } from './PasswordInput'

const SETTINGS: UiSettings = {
  languages: ['en'],
  default_locale: 'en',
  default_theme: 'light',
}

function renderInput(props: ComponentProps<typeof PasswordInput> = {}) {
  return render(
    <I18nProvider settings={SETTINGS}>
      {/* It has a visibility toggle, so it is tied with `for` / `id` instead of wrapped in
       * `<label>` (matching how callers write it). */}
      <label htmlFor="test-password">Password</label>
      <PasswordInput id="test-password" {...props} />
    </I18nProvider>,
  )
}

function field() {
  return screen.getByLabelText('Password')
}

describe('PasswordInput', () => {
  it('is masked by default', () => {
    renderInput()
    expect(field()).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button', { name: 'Show password' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('shows plain text on press and masks again on a second press', () => {
    renderInput()

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(field()).toHaveAttribute('type', 'text')

    const hide = screen.getByRole('button', { name: 'Hide password' })
    expect(hide).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(hide)
    expect(field()).toHaveAttribute('type', 'password')
  })

  it('keeps the value when toggling', () => {
    renderInput()

    fireEvent.change(field(), { target: { value: 'correct horse' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(field()).toHaveValue('correct horse')
  })

  it('disables the toggle when the input is disabled', () => {
    renderInput({ disabled: true })
    expect(screen.getByRole('button', { name: 'Show password' })).toBeDisabled()
  })
})
