/**
 * 「描画が例外を投げること」を検証するときのノイズ抑制。
 *
 * React は描画中の例外を再スローすると同時に ``console.error`` と window の
 * ``error`` イベントへも流す。jsdom は後者をそのまま標準エラーへ出すため、
 * 期待どおり通ったテストでも失敗に見える出力が残る。想定内の例外だけを
 * 黙らせる。
 */
import { vi } from 'vitest'

/** *act* の実行中だけ、描画例外の二次報告を抑制する。 */
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
