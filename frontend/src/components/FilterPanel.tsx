/**
 * Makes the log search filters collapsible (ADR-0080 §6).
 *
 * The filters have 6-8 fields; stacked in one column on a narrow screen they exceed a whole
 * screen. Log pages are about the result list, so on narrow screens the filters are collapsed
 * by default and opened with "Filter".
 *
 * **Not collapsed on wide screens.** The toggle button is removed in `index.css` and the
 * content is always visible (the whole button gets `display: none` so assistive technology
 * does not see an `aria-expanded` with no way to close). Only open/closed is held as state;
 * width handling stays in CSS (ADR-0080 §2).
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
