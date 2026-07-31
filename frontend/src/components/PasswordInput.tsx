/**
 * パスワード入力欄（入力内容の表示・非表示を切り替えられる）。
 *
 * 伏せ字のままだと打ち間違いに気付けないため、目のアイコンで平文表示へ切り替える。
 * 既定は非表示で、切り替えは欄ごとに独立している（表示状態は保存しない）。
 *
 * 見た目は素の `<input type="password">` と揃える。枠線は `index.css` の
 * `button` / `input` と同じ `var(--border)` をそのまま使い、色を直に書かない。
 */
import { useState, type ComponentPropsWithoutRef } from 'react'

import { useI18n } from '../i18n'

/** `type` だけは自前で持つ（表示状態で text / password を切り替えるため）。 */
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
 * 目のアイコン。表示中は「押すと隠れる」ことが分かるよう斜線を重ねる。
 * 色は `currentColor`（ボタンの文字色）に任せ、テーマごとの指定を持たない。
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
