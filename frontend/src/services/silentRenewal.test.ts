/** 見えない枠で IdP に問い合わせ、枠の行き先から結果を読む（ADR-0104）。 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RENEWAL_RESULT_PATH, renewInFrame } from './silentRenewal'

function frameNow(): HTMLIFrameElement {
  const frame = document.querySelector('iframe')
  if (!frame) throw new Error('no frame')
  return frame
}

/** 枠が `href` まで進んで読み込みを終えたことにする。 */
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

  it('見えない枠で続ける往復を始める', () => {
    void renewInFrame()
    const frame = frameNow()
    expect(frame.getAttribute('src')).toBe('/api/auth/sso/renew')
    expect(frame.hidden).toBe(true)
  })

  it.each(['renewed', 'declined'] as const)(
    '結果の頁の %s を返し、枠を片付ける',
    async (result) => {
      const pending = renewInFrame()
      land(frameNow(), `${RENEWAL_RESULT_PATH}?result=${result}`)
      await expect(pending).resolves.toBe(result)
      expect(document.querySelector('iframe')).toBeNull()
    },
  )

  it('知らない結果は failed', async () => {
    const pending = renewInFrame()
    land(frameNow(), `${RENEWAL_RESULT_PATH}?result=ok`)
    await expect(pending).resolves.toBe('failed')
  })

  it('読めないオリジン（IdP の画面）で止まったら failed', async () => {
    const pending = renewInFrame()
    land(frameNow(), () => {
      throw new DOMException('Blocked a frame', 'SecurityError')
    })
    await expect(pending).resolves.toBe('failed')
  })

  it('別の頁へ着いたら failed', async () => {
    const pending = renewInFrame()
    land(frameNow(), '/login?sso_error=x')
    await expect(pending).resolves.toBe('failed')
  })

  it('始まる前の about:blank は待つ', async () => {
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

  it('時間切れは failed', async () => {
    vi.useFakeTimers()
    const pending = renewInFrame(1000)
    vi.advanceTimersByTime(1000)
    await expect(pending).resolves.toBe('failed')
    expect(document.querySelector('iframe')).toBeNull()
  })
})
