import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/react'
import { afterEach } from 'vitest'

// Don't carry the DOM over between tests (prevents side effects across describe blocks)
afterEach(() => {
  cleanup()
})

// Timeout for `findBy*` / `waitFor` (default 1 second). On a busy CI runner the first render
// of a file alone can exceed 1 second and fail (happened twice in the derived toeic app).
// They proceed as soon as the element appears, so raising the limit doesn't slow fast tests.
configure({ asyncUtilTimeout: 5000 })

// jsdom doesn't implement `<dialog>`'s open/close methods (the element and `open` attribute
// exist). Without them, callers of `showModal()` silently do nothing and the dialog contents stay
// `display: none`, hidden from screen readers and test queries.
// Only toggling the `open` attribute is polyfilled here. Focus trapping, Esc and the top layer
// are browser features and are not verified in jsdom (ADR-0080 §6).
// The types say the methods always exist, so take a Partial to check whether they are
// implemented (no polyfill on jsdom versions that implement them).
const dialogPrototype: Partial<HTMLDialogElement> = HTMLDialogElement.prototype
if (typeof dialogPrototype.showModal !== 'function') {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false
    this.dispatchEvent(new Event('close'))
  }
}
