/**
 * Collapsing the log filters (ADR-0080 §6).
 *
 * jsdom does not apply media queries, so only the `data-open` and `aria-expanded` transitions
 * can be verified (same reason as `AppLayout.test.tsx`). Whether it actually collapses on
 * narrow screens is up to `index.css`.
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
  it('is collapsed by default and the content is always rendered', () => {
    const { container, toggle } = renderPanel()

    expect(container.querySelector('.filter-panel')).toHaveAttribute('data-open', 'false')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    // On wide screens the toggle disappears and the content is always visible, so it stays in the DOM.
    expect(screen.getByText('filter fields')).toBeInTheDocument()
  })

  it('toggles open and closed on each press', () => {
    const { container, toggle } = renderPanel()

    fireEvent.click(toggle)
    expect(container.querySelector('.filter-panel')).toHaveAttribute('data-open', 'true')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(toggle)
    expect(container.querySelector('.filter-panel')).toHaveAttribute('data-open', 'false')
  })

  it('ties the toggle button to the content with `aria-controls`', () => {
    const { container, toggle } = renderPanel()

    const fields = container.querySelector('.filter-panel-fields')
    expect(toggle.getAttribute('aria-controls')).toBe(fields?.id)
  })
})
