/**
 * Back/forward returns to where the reader was, once the page is tall enough (ADR-0107).
 *
 * jsdom has no layout: the page height (`scrollHeight`), the scroll position (`scrollY`) and the
 * ResizeObserver are stood in for here, and `window.scrollTo` is watched.
 */
import { act, render } from '@testing-library/react'
import { BrowserRouter, MemoryRouter, useNavigate, type NavigateFunction } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useHistoryScroll, WAIT_LIMIT_MS } from './useHistoryScroll'

const VIEWPORT = 800

let pageHeight = VIEWPORT
let observers: (() => void)[] = []
let scrollTo: ReturnType<typeof vi.fn>

class FakeResizeObserver {
  private readonly callback: () => void
  constructor(callback: () => void) {
    this.callback = callback
  }
  observe() {
    observers.push(this.callback)
  }
  disconnect() {
    observers = observers.filter((callback) => callback !== this.callback)
  }
}

/** The page grows (the data arrived and was drawn). */
function growPage(height: number) {
  pageHeight = height
  act(() => {
    for (const callback of [...observers]) callback()
  })
}

/** The reader scrolls to `y`. */
function scrollPageTo(y: number) {
  Object.defineProperty(window, 'scrollY', { configurable: true, value: y })
  act(() => {
    window.dispatchEvent(new Event('scroll'))
  })
}

function lastScroll(): number | undefined {
  const call = scrollTo.mock.calls.at(-1) as [number, number] | undefined
  return call?.[1]
}

function renderApp(router: 'memory' | 'browser' = 'memory') {
  let navigate: NavigateFunction | null = null
  function Harness() {
    useHistoryScroll()
    navigate = useNavigate()
    return null
  }
  render(
    router === 'memory' ? (
      <MemoryRouter initialEntries={['/items']}>
        <Harness />
      </MemoryRouter>
    ) : (
      <BrowserRouter>
        <Harness />
      </BrowserRouter>
    ),
  )
  return (to: string | number) => {
    act(() => {
      if (typeof to === 'number') void navigate?.(to)
      else void navigate?.(to)
    })
  }
}

describe('useHistoryScroll', () => {
  beforeEach(() => {
    pageHeight = VIEWPORT
    observers = []
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)
    Object.defineProperty(document.documentElement, 'scrollHeight', {
      configurable: true,
      get: () => pageHeight,
    })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: VIEWPORT })
    scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    // A fresh visit: the first entry has no history state yet
    window.history.replaceState(null, '', '/items')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    window.sessionStorage.clear()
  })

  it('returns to the kept position on back, once the content is drawn', () => {
    const go = renderApp()
    pageHeight = 5000
    scrollPageTo(1200)

    go('/items/7')
    // A new screen opened by a link starts at the top
    expect(lastScroll()).toBe(0)
    pageHeight = VIEWPORT
    scrollPageTo(0)

    scrollTo.mockClear()
    go(-1)
    // The list has not arrived yet: the page is too short, so nothing happens
    expect(scrollTo).not.toHaveBeenCalled()

    growPage(5000)
    expect(lastScroll()).toBe(1200)
  })

  it('does not keep the short page while waiting', () => {
    const go = renderApp()
    pageHeight = 5000
    scrollPageTo(1200)
    go('/items/7')
    pageHeight = VIEWPORT
    go(-1)
    // The browser clamps the short page to the top while the data is loading
    scrollPageTo(0)
    growPage(5000)
    expect(lastScroll()).toBe(1200)
  })

  it('returns to the first screen of a visit with the real browser history', async () => {
    const go = renderApp('browser')
    pageHeight = 5000
    scrollPageTo(1200)
    go('/items/7')
    pageHeight = VIEWPORT
    scrollTo.mockClear()

    // jsdom delivers the back navigation (popstate) in a later task
    await act(async () => {
      window.history.back()
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(window.location.pathname).toBe('/items')
    growPage(5000)
    expect(lastScroll()).toBe(1200)
  })

  it('returns to the top when the list was read at the top', () => {
    const go = renderApp()
    pageHeight = 5000
    go('/items/7')
    // The reader scrolls down on the detail screen, then comes back
    scrollPageTo(2000)
    scrollTo.mockClear()
    go(-1)
    expect(lastScroll()).toBe(0)
  })

  it('returns to the top when the reader scrolled back up to it before leaving', () => {
    const go = renderApp()
    pageHeight = 5000
    scrollPageTo(1200)
    scrollPageTo(0)
    go('/items/7')
    scrollPageTo(2000)
    scrollTo.mockClear()
    go(-1)
    expect(lastScroll()).toBe(0)
  })

  it('also returns on forward', () => {
    const go = renderApp()
    go('/items/7')
    pageHeight = 3000
    scrollPageTo(900)
    go(-1)
    pageHeight = VIEWPORT
    scrollTo.mockClear()
    go(1)
    growPage(3000)
    expect(lastScroll()).toBe(900)
  })

  it('stops when the reader moves the page themselves while waiting', () => {
    const go = renderApp()
    pageHeight = 5000
    scrollPageTo(1200)
    go('/items/7')
    pageHeight = VIEWPORT
    scrollTo.mockClear()
    go(-1)

    act(() => {
      window.dispatchEvent(new Event('wheel'))
    })
    growPage(5000)
    expect(scrollTo).not.toHaveBeenCalled()
  })

  it('goes as far as it can when the content does not grow within the limit', () => {
    vi.useFakeTimers()
    const go = renderApp()
    pageHeight = 5000
    scrollPageTo(1200)
    go('/items/7')
    pageHeight = VIEWPORT
    scrollTo.mockClear()
    go(-1)

    act(() => {
      vi.advanceTimersByTime(WAIT_LIMIT_MS)
    })
    expect(lastScroll()).toBe(1200)
  })

  it('starts at the top when the same list is opened again by a link', () => {
    const go = renderApp()
    pageHeight = 5000
    scrollPageTo(1200)
    go('/items/7')
    scrollTo.mockClear()
    go('/items')
    growPage(5000)
    expect(scrollTo.mock.calls).toEqual([[0, 0]])
  })

  it('keeps the position when only the filters of the same screen change', () => {
    const go = renderApp()
    pageHeight = 5000
    scrollPageTo(1200)
    scrollTo.mockClear()
    go('/items?q=pen')
    expect(scrollTo).not.toHaveBeenCalled()
  })
})
