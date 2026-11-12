/**
 * How the input dialog (ADR-0080 §6) closes.
 *
 * Checks that "every close action reaches the caller". With the `<dialog>` default, Esc closes
 * only the dialog and the caller's state stays open, so pressing "Add" next time shows nothing.
 *
 * The look by width (full width from the bottom on narrow screens) is decided by CSS, so it
 * cannot be verified in jsdom (ADR-0080 §2).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import { FormDialog } from './FormDialog'

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderDialog(onClose: () => void) {
  return render(
    <I18nProvider settings={SETTINGS}>
      <FormDialog title="Add user" onClose={onClose}>
        <form className="dialog-form">
          <p>form contents</p>
          <input aria-label="Name" />
        </form>
      </FormDialog>
    </I18nProvider>,
  )
}

describe('FormDialog', () => {
  it('renders the heading and content', () => {
    renderDialog(vi.fn())

    expect(screen.getByRole('heading', { name: 'Add user' })).toBeInTheDocument()
    expect(screen.getByText('form contents')).toBeInTheDocument()
  })

  it('focuses the first input when opened (not the close button)', () => {
    renderDialog(vi.fn())

    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveFocus()
  })

  it('closes with ✕', () => {
    const onClose = vi.fn()
    renderDialog(onClose)

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('also closes on Esc (cancel) and prevents the browser default cancel', () => {
    const onClose = vi.fn()
    const { container } = renderDialog(onClose)
    const dialog = container.querySelector('dialog')
    expect(dialog).not.toBeNull()

    const cancel = new Event('cancel', { bubbles: false, cancelable: true })
    fireEvent(dialog as HTMLDialogElement, cancel)

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(cancel.defaultPrevented).toBe(true)
  })
})
