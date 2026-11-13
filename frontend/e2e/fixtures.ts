import { test as base, expect } from '@playwright/test'

/** Marks responses a test returned on purpose (the watcher below does not count them as 5xx). */
export const INTENDED_FAULT_HEADER = 'x-e2e-intended'

/**
 * Watcher applied to every test. Even if the screen looks right, fail the test when an
 * uncaught exception or a 5xx response happens behind the scenes.
 */
export const test = base.extend<{ watchForFaults: undefined }>({
  watchForFaults: [
    async ({ page }, use) => {
      const faults: string[] = []
      page.on('pageerror', (error) => {
        faults.push(`pageerror: ${error.message}`)
      })
      // Loads/executions refused by the CSP (ADR-0073 §5) fail the test even if the screen seems to work
      page.on('console', (message) => {
        if (message.type() === 'error' && message.text().includes('Content Security Policy')) {
          faults.push(`csp: ${message.text()}`)
        }
      })
      page.on('response', (response) => {
        // Don't count 5xx a test returned on purpose (pretending the front tier is closed; maintenance.spec.ts)
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
