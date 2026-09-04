/**
 * ログの絞り込みの畳み方（ADR-0027）。
 *
 * jsdom はメディアクエリを適用しないので、検証できるのは `data-open` と
 * `aria-expanded` の遷移だけ（`AppLayout.test.tsx` と同じ理由）。狭い画面で
 * 実際に畳まれるかは `index.css` 側の指定になる。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { I18nProvider } from '../i18n'
import { FilterPanel } from './FilterPanel'

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderPanel() {
  const { container } = render(
    <I18nProvider settings={SETTINGS}>
      <FilterPanel>
        <p>filter fields</p>
      </FilterPanel>
    </I18nProvider>,
  )
  const toggle = screen.getByRole('button', { name: /Filters/ })
  return { container, toggle }
}

describe('FilterPanel', () => {
  it('既定では畳んだ状態で、中身は常に描かれている', () => {
    const { container, toggle } = renderPanel()

    expect(container.querySelector('.filter-panel')).toHaveAttribute('data-open', 'false')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    // 広い画面では開閉ボタンごと消えて常に見えるため、中身は DOM に残す。
    expect(screen.getByText('filter fields')).toBeInTheDocument()
  })

  it('押すたびに開閉が入れ替わる', () => {
    const { container, toggle } = renderPanel()

    fireEvent.click(toggle)
    expect(container.querySelector('.filter-panel')).toHaveAttribute('data-open', 'true')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(toggle)
    expect(container.querySelector('.filter-panel')).toHaveAttribute('data-open', 'false')
  })

  it('開閉ボタンは中身と `aria-controls` で結ばれている', () => {
    const { container, toggle } = renderPanel()

    const fields = container.querySelector('.filter-panel-fields')
    expect(toggle.getAttribute('aria-controls')).toBe(fields?.id)
  })
})
