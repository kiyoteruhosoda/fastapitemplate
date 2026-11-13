/**
 * Outer frame of the signed-in screens (header, navigation, main content, footer).
 *
 * On narrow screens the sidebar becomes a drawer. Its open state lives here, and it can be
 * closed from the header menu button, the overlay and the navigation links. Screen width
 * handling is left to the CSS media queries (`index.css`); this only toggles the `data-open`
 * attribute (on wide screens the sidebar is always visible).
 *
 * While open, the header and content are hidden under the overlay. If only the keyboard could
 * still reach them, the user would be "operating invisible elements", so on open focus moves
 * into the drawer and Tab is trapped there, and on close focus returns to the menu button
 * (ADR-0080 §2).
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import { InboxProvider } from '../store/InboxContext'
import { Footer } from './Footer'
import { Header } from './Header'
import { NotificationBanner } from './NotificationBanner'
import { Sidebar } from './Sidebar'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), select:not([disabled]), input:not([disabled])'

function focusableIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
}

/** Wraps Tab / Shift+Tab focus movement within *container*. */
function keepFocusInside(container: HTMLElement, event: KeyboardEvent): void {
  const items = focusableIn(container)
  const first = items.at(0)
  const last = items.at(-1)
  if (first === undefined || last === undefined) return

  const active = document.activeElement
  const outside = !(active instanceof Node) || !container.contains(active)
  const leavingBackwards = event.shiftKey && (active === first || outside)
  const leavingForwards = !event.shiftKey && (active === last || outside)
  if (!leavingBackwards && !leavingForwards) return

  event.preventDefault()
  ;(leavingBackwards ? last : first).focus()
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false)
  const { pathname } = useLocation()
  const toggleRef = useRef<HTMLButtonElement>(null)
  const navRef = useRef<HTMLElement>(null)
  // Record used to return focus only on "closed" (does nothing on the initial render).
  const wasOpen = useRef(false)

  const closeNav = useCallback(() => {
    setNavOpen(false)
  }, [])

  const toggleNav = useCallback(() => {
    setNavOpen((open) => !open)
  }, [])

  // Close the drawer when the page changes (including navigation by in-page buttons).
  useEffect(() => {
    setNavOpen(false)
  }, [pathname])

  // While open: move focus to the first control, close on Esc, trap Tab.
  useEffect(() => {
    const nav = navRef.current
    if (!navOpen || nav === null) return

    // The drawer is `visibility: hidden` (= not focusable) while closed, so wait for the
    // next frame where the open state is rendered before moving focus.
    // Calling focus() without waiting for that frame is ignored by the browser.
    const frame = requestAnimationFrame(() => {
      focusableIn(nav).at(0)?.focus()
    })

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false)
      else if (event.key === 'Tab') keepFocusInside(nav, event)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [navOpen])

  // On close, return focus to the menu button (the drawer becomes hidden and focus
  // would have nowhere to be).
  useEffect(() => {
    if (navOpen) {
      wasOpen.current = true
      return
    }
    if (wasOpen.current) {
      wasOpen.current = false
      toggleRef.current?.focus()
    }
  }, [navOpen])

  return (
    // Announcements (bell and top banner) use the same list, so fetch it once in the frame (ADR-0081 §3).
    <InboxProvider>
      <div className="layout">
        <Header navOpen={navOpen} onToggleNav={toggleNav} toggleRef={toggleRef} />
        <div className="layout-body">
          <Sidebar open={navOpen} onClose={closeNav} navRef={navRef} />
          {/* Overlay for tapping outside the drawer to close it. Screen reader and keyboard
            users can close it with the close button in the drawer and Esc, so it is hidden
            from assistive technology. */}
          {navOpen && (
            <div
              className="nav-overlay"
              data-testid="nav-overlay"
              aria-hidden="true"
              onClick={closeNav}
            />
          )}
          <main className="content">
            <NotificationBanner />
            {children}
          </main>
        </div>
        <Footer />
      </div>
    </InboxProvider>
  )
}
