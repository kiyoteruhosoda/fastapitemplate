/**
 * Password field whose content can be shown or hidden.
 *
 * Masked input hides typos, so an eye icon switches it to plain text.
 * Hidden by default; each field toggles independently (the state is not persisted).
 *
 * Looks the same as a plain `<input type="password">`. The border uses the same
 * `var(--border)` as `button` / `input` in `index.css`; no colors are hard-coded.
 */
import { useState, type ComponentPropsWithoutRef } from 'react'

import { useI18n } from '../i18n'

/** `type` is owned here (it switches between text / password with the visibility state). */
type PasswordInputProps = Omit<ComponentPropsWithoutRef<'input'>, 'type'>

export function PasswordInput({ className, ...inputProps }: PasswordInputProps) {
  const { t } = useI18n()
  const [visible, setVisible] = useState(false)
  const label = t(visible ? 'common.hidePassword' : 'common.showPassword')

  return (
    <div className={className ? `password-field ${className}` : 'password-field'}>
      <input {...inputProps} type={visible ? 'text' : 'password'} />
      <button
        type="button"
        className="password-toggle"
        aria-label={label}
        aria-pressed={visible}
        title={label}
        disabled={inputProps.disabled}
        onClick={() => {
          setVisible((current) => !current)
        }}
      >
        <EyeIcon crossedOut={visible} />
      </button>
    </div>
  )
}

/**
 * Eye icon. While the text is shown, a slash is overlaid so it is clear that clicking hides it.
 * The color comes from `currentColor` (the button's text color); no per-theme rules.
 */
function EyeIcon({ crossedOut }: { crossedOut: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1.1em"
      height="1.1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M1.8 12S5.4 5.4 12 5.4 22.2 12 22.2 12 18.6 18.6 12 18.6 1.8 12 1.8 12Z" />
      <circle cx="12" cy="12" r="3.1" />
      {crossedOut && <path d="M3.6 3.6 20.4 20.4" />}
    </svg>
  )
}
