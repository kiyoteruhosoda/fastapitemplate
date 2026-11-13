/**
 * Dialog that holds an input form (ADR-0080 §6).
 *
 * Opened when "Add" is pressed on a list page. On narrow screens it appears full width from
 * the bottom; on wide screens in the center. **Which form it takes is decided by `index.css`**,
 * so this component does not check the screen width (ADR-0080 §2).
 *
 * Opens a plain `<dialog>` with `showModal()`. Focus trapping, Esc to cancel, making the
 * background inert and stacking (top layer) all use the browser's implementation. Hand-rolled
 * versions get the stacking against the header (`position: sticky`) or the focus return
 * target wrong page by page.
 *
 * Rendered only while open (use as `{open && <FormDialog …>}`). A closed `<dialog>` left
 * in the DOM makes its inputs show up twice for screen readers and test queries, alongside
 * same-named items on the list page.
 *
 * jsdom has no `<dialog>` open/close methods, so in tests `vitest.setup.ts` only toggles
 * the `open` attribute.
 */
import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from 'react'

import { useI18n } from '../i18n'

export function FormDialog({
  title,
  onClose,
  children,
}: {
  /** Heading. Says what is being added (use the same wording as the triggering button). */
  title: string
  /** Close action (✕, Esc, tapping the backdrop). The caller stops rendering. */
  onClose: () => void
  children: ReactNode
}) {
  const { t } = useI18n()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const headingId = useId()

  // Open once rendered. It closes when the caller stops rendering (close in the cleanup).
  // StrictMode's second run also works, since the cleanup closes before reopening
  // (calling `showModal()` on an open `<dialog>` throws).
  //
  // Once open, move focus to the first input. By default it lands on the close button (✕)
  // first in the DOM, so keyboard and screen reader users would start at "Close".
  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog === null) return
    dialog.showModal()
    dialog.querySelector<HTMLElement>('.dialog-form :is(input, select, textarea)')?.focus()
    return () => {
      dialog.close()
    }
  }, [])

  /** Clicks on the backdrop (`::backdrop`) reach the `<dialog>` itself; content clicks reach the panel. */
  const closeOnBackdrop = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === event.currentTarget) onClose()
  }

  return (
    <dialog
      ref={dialogRef}
      className="form-dialog"
      aria-labelledby={headingId}
      onClick={closeOnBackdrop}
      onCancel={(event) => {
        // By default Esc closes only the `<dialog>`, leaving the caller's state open.
        event.preventDefault()
        onClose()
      }}
    >
      <div className="form-dialog-panel">
        <div className="form-dialog-head">
          <h2 id={headingId}>{title}</h2>
          <button
            type="button"
            className="button-ghost form-dialog-close"
            aria-label={t('common.close')}
            onClick={onClose}
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>
        {children}
      </div>
    </dialog>
  )
}
