/**
 * "A new version is available" notice (ADR-0080 §7; placement in ADR-0106).
 *
 * Shown as a bar at the very top of the screen only when a new version is waiting, and reloads
 * when pressed. The bar appears on every screen (the login screen has no header, so it sits
 * above the header rather than inside it) and stays at the top when scrolling. On signed-in
 * screens the bar height is passed in the CSS variable `--update-bar-height` so the header
 * attaches right below the bar (the height changes when the text wraps).
 *
 * No toast or floating notice at the bottom - it would vanish after a few seconds or get lost
 * in the content, and users who miss it keep using the old version.
 *
 * The watcher (`services/appUpdate.ts`) is passed in as an argument, to keep the side effect
 * of registering the Service Worker out of this component and let tests pass a fake watcher.
 */
import { useEffect, useRef, useState } from 'react'

import { useI18n } from '../i18n'
import type { ApplyUpdate, WatchForUpdate } from '../services/appUpdate'
import { ActionButton } from './ActionButton'

export function AppUpdatePrompt({ watch }: { watch: WatchForUpdate }) {
  const { t } = useI18n()
  const [apply, setApply] = useState<ApplyUpdate | null>(null)
  const [applying, setApplying] = useState(false)
  const barRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // useState treats a function as a lazy initializer, so to store a function itself
    // pass a function that returns it.
    watch((applyUpdate) => {
      setApply(() => applyUpdate)
    })
  }, [watch])

  // Pass the bar height to the header's sticky offset. Reset to 0 when the bar goes away.
  useEffect(() => {
    const bar = barRef.current
    if (!apply || bar === null) return
    const root = document.documentElement
    const publish = () => {
      root.style.setProperty('--update-bar-height', `${String(bar.offsetHeight)}px`)
    }
    publish()
    // jsdom has no ResizeObserver. The height was already passed once, so not observing is fine.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(publish)
    observer?.observe(bar)
    return () => {
      observer?.disconnect()
      root.style.removeProperty('--update-bar-height')
    }
  }, [apply])

  if (!apply) return null

  return (
    <div ref={barRef} className="update-bar" role="status">
      <span className="update-bar-text">{t('update.available')}</span>
      {/* There is a delay between pressing and the page being replaced, so show that the
          press registered (ADR-0080 §5). */}
      <ActionButton
        type="button"
        className="update-bar-button"
        pending={applying}
        onClick={() => {
          setApplying(true)
          apply()
        }}
      >
        {t('update.reload')}
      </ActionButton>
    </div>
  )
}
