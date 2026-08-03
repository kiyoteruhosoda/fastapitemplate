/**
 * 実行中はスピナーを出して押せなくするボタン（ADR-0022）。
 *
 * サーバーへ問い合わせる操作は、結果が返るまで画面が変わらない。押せたのかどうかが
 * 分からないと利用者は同じボタンを続けて押すので、押した直後に必ず目印を出す。
 *
 * 見た目は素の `<button>` と同じ（`index.css` の指定をそのまま使う）。実行中でも
 * ラベルは差し替えず、スピナーを前に足すだけにする（幅が動くと押した位置がずれる）。
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { useI18n } from '../i18n'

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 実行中。スピナーを出し、押せなくする。 */
  pending: boolean
  children: ReactNode
}

export function ActionButton({ pending, disabled, children, ...buttonProps }: ActionButtonProps) {
  const { t } = useI18n()

  return (
    <button {...buttonProps} disabled={pending || (disabled ?? false)} aria-busy={pending}>
      {pending && (
        <>
          <span className="spinner" aria-hidden="true" />
          {/* 回る印は目でしか分からないので、読み上げ用の文言を別に置く。 */}
          <span className="visually-hidden">{t('common.processing')}</span>
        </>
      )}
      {children}
    </button>
  )
}
