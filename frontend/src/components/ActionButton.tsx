/**
 * 実行中はスピナーを出して押せなくするボタン（ADR-0022）。
 *
 * サーバーへ問い合わせる操作は、結果が返るまで画面が変わらない。押せたのかどうかが
 * 分からないと利用者は同じボタンを続けて押すので、押した直後に必ず目印を出す。
 *
 * 見た目は素の `<button>` と同じ（`index.css` の指定をそのまま使う）。スピナーは
 * ラベルの上に重ね、ラベルは場所を占めたまま隠す。押した瞬間にボタンの幅が変わると、
 * 隣のボタンが動いて押し間違いの元になるため（`.action-button` の指定を参照）。
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { useI18n } from '../i18n'

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 実行中。スピナーを出し、押せなくする。 */
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
          {/* 回る印は目でしか分からないので、読み上げ用の文言を別に置く。 */}
          <span className="visually-hidden">{t('common.processing')}</span>
        </>
      )}
    </button>
  )
}
