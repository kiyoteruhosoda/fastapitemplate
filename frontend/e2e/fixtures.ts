import { test as base, expect } from '@playwright/test'

/**
 * どの試験にも掛ける見張り。画面が正しく見えていても、裏で捕まえていない例外や
 * 5xx の応答が出ていれば、その試験を落とす。
 */
export const test = base.extend<{ watchForFaults: void }>({
  watchForFaults: [
    async ({ page }, use) => {
      const faults: string[] = []
      page.on('pageerror', (error) => {
        faults.push(`pageerror: ${error.message}`)
      })
      page.on('response', (response) => {
        if (response.status() >= 500) faults.push(`${response.status()} ${response.url()}`)
      })
      await use()
      expect(faults).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
