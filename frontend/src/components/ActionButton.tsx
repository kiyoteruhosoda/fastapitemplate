/**
 * Button that shows a spinner and is disabled while running (ADR-0080 §5).
 *
 * Operations that call the server do not change the screen until the result returns. If users
 * cannot tell whether the press registered they press the same button again, so a marker is
 * always shown right after the press.
 *
 * Looks the same as a plain `<button>` (uses the `index.css` rules as is). The spinner is
 * overlaid on the label, and the label is hidden but keeps its space. If the button width
 * changed on press, neighbouring buttons would shift and cause mis-clicks (see `.action-button`).
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { useI18n } from '../i18n'

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Running. Shows a spinner and disables the button. */
  pending: boolean
  children: ReactNode
}

export function ActionButton({
  pending,
  disabled,
  className,
  children,
  ...buttonProps
}: ActionButtonProps) {
  const { t } = useI18n()

  return (
    <button
      {...buttonProps}
      className={className === undefined ? 'action-button' : `action-button ${className}`}
      disabled={pending || (disabled ?? false)}
      aria-busy={pending}
    >
      <span className="action-button-label">{children}</span>
      {pending && (
        <>
          <span className="spinner action-button-spinner" aria-hidden="true" />
          {/* The spinning marker is visual only, so provide separate text for screen readers. */}
          <span className="visually-hidden">{t('common.processing')}</span>
        </>
      )}
    </button>
  )
}
