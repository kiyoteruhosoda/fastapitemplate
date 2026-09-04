/**
 * ログ検索の絞り込みを畳める形にする（ADR-0027）。
 *
 * 絞り込みは項目が 6〜8 個あり、狭い画面では 1 列に積むと画面 1 枚分を超える。
 * ログ画面が見せたいのは結果の一覧なので、狭い画面では既定で畳み、「絞り込み」で開く。
 *
 * **広い画面では畳まない。** 開閉ボタンは `index.css` で消し、中身は常に見えている
 * （閉じるための操作が無いのに `aria-expanded` を出さないよう、ボタンごと
 * `display: none` にして支援技術からも外す）。開いているかどうかだけを状態として
 * 持ち、幅の解釈は CSS に閉じる（ADR-0011）。
 */
import { useId, useState, type ReactNode } from 'react'

import { useI18n } from '../i18n'

export function FilterPanel({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const fieldsId = useId()

  return (
    <div className="filter-panel" data-open={open ? 'true' : 'false'}>
      <button
        type="button"
        className="filter-toggle"
        aria-expanded={open}
        aria-controls={fieldsId}
        onClick={() => {
          setOpen((current) => !current)
        }}
      >
        {t('common.filter')}
        <span aria-hidden="true" className="filter-toggle-caret">
          ▾
        </span>
      </button>
      <div id={fieldsId} className="filter-panel-fields">
        {children}
      </div>
    </div>
  )
}
