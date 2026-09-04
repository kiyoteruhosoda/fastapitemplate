/**
 * 入力フォームを載せるダイアログ（ADR-0027）。
 *
 * 一覧の画面で「追加」を押したときに開く。狭い画面では画面の下から幅いっぱいに、
 * 広い画面では中央に出る。**どちらの形で出すかは `index.css` が決める**ので、
 * このコンポーネントは画面幅を判定しない（ADR-0011）。
 *
 * 素の `<dialog>` を `showModal()` で開く。フォーカスの閉じ込め・Esc での取り消し・
 * 背後の不活性化・重ね順（top layer）はブラウザ側の実装をそのまま使う。
 * 自前で組むと、ヘッダー（`position: sticky`）との重ね順やフォーカスの戻し先を
 * 画面ごとに間違える。
 *
 * 開いているあいだだけ描画する（`{open && <FormDialog …>}` の形で使う）。閉じた
 * `<dialog>` を残しておくと、中の入力欄が読み上げ・テストの検索対象として
 * 一覧側の同名の項目と二重に見つかる。
 */
import { useEffect, useId, useRef, type MouseEvent, type ReactNode } from 'react'

import { useI18n } from '../i18n'

export function FormDialog({
  title,
  onClose,
  children,
}: {
  /** 見出し。何を追加するのかを示す（引き金のボタンと同じ言い回しにする）。 */
  title: string
  /** 閉じる操作（✕・Esc・背景のタップ）。呼び出し側が描画をやめる。 */
  onClose: () => void
  children: ReactNode
}) {
  const { t } = useI18n()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const headingId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    // jsdom は `showModal` を持たない版があるため、無ければ素通しする（テストでは
    // 中身が描かれていることだけを見る）。
    if (dialog === null || typeof dialog.showModal !== 'function') return
    dialog.showModal()
    return () => {
      dialog.close()
    }
  }, [])

  /** 背景（`::backdrop`）のクリックは `<dialog>` 自身に届く。中身は panel が受ける。 */
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
        // Esc は既定だと `<dialog>` だけを閉じ、呼び出し側の状態が開いたまま残る。
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
