import { test as base, expect } from '@playwright/test'

/** 試験がわざと返した応答の印（下の見張りが 5xx として数えない）。 */
export const INTENDED_FAULT_HEADER = 'x-e2e-intended'

/**
 * どの試験にも掛ける見張り。画面が正しく見えていても、裏で捕まえていない例外や
 * 5xx の応答が出ていれば、その試験を落とす。
 */
export const test = base.extend<{ watchForFaults: undefined }>({
  watchForFaults: [
    async ({ page }, use) => {
      const faults: string[] = []
      page.on('pageerror', (error) => {
        faults.push(`pageerror: ${error.message}`)
      })
      // CSP（ADR-0059）に断られた読み込み・実行は、画面が動いて見えても落とす
      page.on('console', (message) => {
        if (message.type() === 'error' && message.text().includes('Content Security Policy')) {
          faults.push(`csp: ${message.text()}`)
        }
      })
      page.on('response', (response) => {
        // 試験がわざと返した 5xx（前段が閉じているふり。maintenance.spec.ts）は数えない
        if (response.status() >= 500 && response.headers()[INTENDED_FAULT_HEADER] === undefined)
          faults.push(`${response.status()} ${response.url()}`)
      })
      await use(undefined)
      expect(faults).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
