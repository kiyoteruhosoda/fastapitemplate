/** Ask the IdP in a hidden frame and read the result from the frame's location (ADR-0104). */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RENEWAL_RESULT_PATH, renewInFrame } from './silentRenewal'

function frameNow(): HTMLIFrameElement {
  const frame = document.querySelector('iframe')
  if (!frame) throw new Error('no frame')
  return frame
}

/** Pretend the frame advanced to `href` and finished loading. */
function land(frame: HTMLIFrameElement, href: string | (() => never)): void {
  const location =
    typeof href === 'string'
      ? new URL(href, 'https://app.example.test')
      : {
          get href(): string {
            return href()
          },
        }
  Object.defineProperty(frame, 'contentWindow', { configurable: true, value: { location } })
  frame.dispatchEvent(new Event('load'))
}

describe('renewInFrame', () => {
  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('starts the continuing round trip in a hidden frame', () => {
    void renewInFrame()
    const frame = frameNow()
    expect(frame.getAttribute('src')).toBe('/api/auth/sso/renew')
    expect(frame.hidden).toBe(true)
  })

  it.each(['renewed', 'declined'] as const)(
    'returns %s from the result page and cleans up the frame',
    async (result) => {
      const pending = renewInFrame()
      land(frameNow(), `${RENEWAL_RESULT_PATH}?result=${result}`)
      await expect(pending).resolves.toBe(result)
      expect(document.querySelector('iframe')).toBeNull()
    },
  )

  it('an unknown result is failed', async () => {
    const pending = renewInFrame()
    land(frameNow(), `${RENEWAL_RESULT_PATH}?result=ok`)
    await expect(pending).resolves.toBe('failed')
  })

  it('stopping on an unreadable origin (the IdP page) is failed', async () => {
    const pending = renewInFrame()
    land(frameNow(), () => {
      throw new DOMException('Blocked a frame', 'SecurityError')
    })
    await expect(pending).resolves.toBe('failed')
  })

  it('arriving at a different page is failed', async () => {
    const pending = renewInFrame()
    land(frameNow(), '/login?sso_error=x')
    await expect(pending).resolves.toBe('failed')
  })

  it('waits through about:blank before it starts', async () => {
    const pending = renewInFrame()
    const frame = frameNow()
    Object.defineProperty(frame, 'contentWindow', {
      configurable: true,
      value: { location: { href: 'about:blank' } },
    })
    frame.dispatchEvent(new Event('load'))
    land(frame, `${RENEWAL_RESULT_PATH}?result=renewed`)
    await expect(pending).resolves.toBe('renewed')
  })

  it('timing out is failed', async () => {
    vi.useFakeTimers()
    const pending = renewInFrame(1000)
    vi.advanceTimersByTime(1000)
    await expect(pending).resolves.toBe('failed')
    expect(document.querySelector('iframe')).toBeNull()
  })
})
