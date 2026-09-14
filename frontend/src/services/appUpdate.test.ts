/**
 * 更新の見張り（ADR-0035）。
 *
 * Service Worker は jsdom に無いので、登録の口（`virtual:pwa-register`）を
 * 差し替えて「いつ確認しに行くか」「押したときに何をするか」を検証する。
 * 実際に知らせが出て入れ替わるところは実ブラウザでしか確かめられない。
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

/** 更新の確認だけを肩代わりする、最低限の登録。 */
function fakeRegistration() {
  const update = vi.fn(() => Promise.resolve())
  return {
    registration: { installing: null, update } as unknown as ServiceWorkerRegistration,
    update,
  }
}

/** 見張りを始めて、`registerSW` へ渡された手当てを取り出す。 */
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
  it('待機している版が出たときだけ知らせ、押されるまで入れ替えない', () => {
    const { options, applied } = startWatching()

    expect(applied).toHaveLength(0)

    options.onNeedRefresh?.()

    expect(applied).toHaveLength(1)
    expect(updateSW).not.toHaveBeenCalled()

    applied[0]?.()

    expect(updateSW).toHaveBeenCalledTimes(1)
  })

  it('制御の合図が来なくても、猶予のあとに読み直す', () => {
    const { options, applied } = startWatching()
    options.onNeedRefresh?.()
    applied[0]?.()

    expect(reload).not.toHaveBeenCalled()

    vi.advanceTimersByTime(5000)

    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('定期的に更新を確認する（オフラインのときは起こさない）', () => {
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

  it('タブが手前へ戻ったときに確認する（短い間に何度も叩かない）', () => {
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
