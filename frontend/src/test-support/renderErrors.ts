/**
 * Noise suppression for tests that verify "rendering throws".
 *
 * React rethrows errors thrown during render and also reports them to ``console.error`` and
 * the window ``error`` event. jsdom prints the latter straight to stderr, so even tests that
 * pass as expected leave output that looks like a failure. Silence only the expected errors.
 */
import { vi } from 'vitest'

/** Suppress secondary reports of render errors only while *act* is running. */
export function withSuppressedRenderErrors<T>(act: () => T): T {
  const silenced = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  const swallow = (event: Event) => {
    event.preventDefault()
  }
  window.addEventListener('error', swallow)
  try {
    return act()
  } finally {
    window.removeEventListener('error', swallow)
    silenced.mockRestore()
  }
}
