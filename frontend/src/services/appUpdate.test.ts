/**
 * Update watching (ADR-0080 §7).
 *
 * jsdom has no Service Worker, so we swap out the registration entry point (`virtual:pwa-register`)
 * and verify "when it goes to check" and "what happens on press".
 * Seeing the notice actually appear and the swap happen can only be checked in a real browser.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApplyUpdate } from './appUpdate'
import { UPDATE_CHECK_INTERVAL_MS, watchForUpdate } from './appUpdate'

const { registerSW, updateSW } = vi.hoisted(() => ({
  registerSW: vi.fn(),
  updateSW: vi.fn(() => Promise.resolve()),
}))

vi.mock('virtual:pwa-register', () => ({ registerSW }))

interface RegisterOptions {
  onNeedRefresh?: () => void
  onRegisteredSW?: (swUrl: string, registration: ServiceWorkerRegistration | undefined) => void
}

const reload = vi.fn()

/** Minimal registration that only stands in for the update check. */
function fakeRegistration() {
  const update = vi.fn(() => Promise.resolve())
  return {
    registration: { installing: null, update } as unknown as ServiceWorkerRegistration,
    update,
  }
}

/** Start watching and pull out the handlers passed to `registerSW`. */
function startWatching(): { options: RegisterOptions; applied: ApplyUpdate[] } {
  const applied: ApplyUpdate[] = []
  registerSW.mockImplementation(() => updateSW)
  watchForUpdate((apply) => applied.push(apply))
  const options = registerSW.mock.calls[0]?.[0] as RegisterOptions
  return { options, applied }
}

beforeEach(() => {
  vi.useFakeTimers()
  registerSW.mockReset()
  updateSW.mockClear()
  reload.mockClear()
  vi.stubGlobal('location', { reload })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('watchForUpdate', () => {
  it('notifies only when a waiting version appears, and does not swap until pressed', () => {
    const { options, applied } = startWatching()

    expect(applied).toHaveLength(0)

    options.onNeedRefresh?.()

    expect(applied).toHaveLength(1)
    expect(updateSW).not.toHaveBeenCalled()

    applied[0]?.()

    expect(updateSW).toHaveBeenCalledTimes(1)
  })

  it('reloads after the grace period even without the control signal', () => {
    const { options, applied } = startWatching()
    options.onNeedRefresh?.()
    applied[0]?.()

    expect(reload).not.toHaveBeenCalled()

    vi.advanceTimersByTime(5000)

    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('checks for updates periodically (not while offline)', () => {
    const { options } = startWatching()
    const { registration, update } = fakeRegistration()
    options.onRegisteredSW?.('/sw.js', registration)

    vi.advanceTimersByTime(UPDATE_CHECK_INTERVAL_MS)

    expect(update).toHaveBeenCalledTimes(1)

    const online = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    vi.advanceTimersByTime(UPDATE_CHECK_INTERVAL_MS)

    expect(update).toHaveBeenCalledTimes(1)

    online.mockRestore()
  })

  it('checks when the tab returns to the foreground (not repeatedly in a short time)', () => {
    const { options } = startWatching()
    const { registration, update } = fakeRegistration()
    options.onRegisteredSW?.('/sw.js', registration)

    document.dispatchEvent(new Event('visibilitychange'))

    expect(update).toHaveBeenCalledTimes(1)

    document.dispatchEvent(new Event('visibilitychange'))

    expect(update).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(60 * 1000)
    document.dispatchEvent(new Event('visibilitychange'))

    expect(update).toHaveBeenCalledTimes(2)
  })
})
