import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// テスト間で DOM を持ち越さない（describe をまたいだ副作用を防ぐ）
afterEach(() => {
  cleanup()
})

// jsdom は `<dialog>` の開閉メソッドを実装していない（要素と `open` 属性はある）。
// 無いままだと `showModal()` を呼ぶ側が黙って何もせず、ダイアログの中身が
// `display: none` のまま残って読み上げ・テストの検索から外れる。
// ここでは `open` 属性の付け外しだけを肩代わりする。フォーカスの閉じ込め・Esc・
// top layer はブラウザの実装であり、jsdom では検証しない（ADR-0027）。
// 型の上では常にあることになっているので、実装の有無を見るために Partial で受ける
// （jsdom が実装した版では肩代わりしない）。
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
