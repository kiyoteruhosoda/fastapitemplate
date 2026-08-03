/**
 * 押されてから終わるまでを「実行中」として持つ（ADR-0022）。
 *
 * 画面ごとに `busy` の useState を書き足すと、置き忘れた画面だけ無反応に見える。
 * 実行中かどうかは `ActionButton` の `pending` へ渡し、二重送信の防止もここで行う
 * （実行中の再呼び出しは無視する）。
 *
 * 返り値の `run` は `void` を返すので、`onSubmit` / `onClick` にそのまま渡せる
 * （`no-misused-promises` に触れない）。
 *
 * エラーは握り潰さない（渡した関数の中で扱う）。ここが担うのは実行中かどうかだけで、
 * 失敗しても必ず解除する。
 */
import { useEffect, useRef, useState } from 'react'

export function usePendingAction<A extends unknown[]>(
  action: (...args: A) => Promise<void>,
): [run: (...args: A) => void, pending: boolean] {
  const [pending, setPending] = useState(false)
  // 実行中かどうかは state と別に ref でも持つ。state の更新は次の描画までに
  // 反映されないので、続けて押されたときの判定には間に合わない。
  const running = useRef(false)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = (...args: A) => {
    if (running.current) return
    running.current = true
    setPending(true)
    void action(...args).finally(() => {
      running.current = false
      // 成功して別画面へ移った後は更新しない（この部品はもう無い）。
      if (mounted.current) setPending(false)
    })
  }

  return [run, pending]
}
