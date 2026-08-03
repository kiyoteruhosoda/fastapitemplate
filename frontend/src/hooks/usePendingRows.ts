/**
 * 一覧の行ごとに「いま実行中の操作」を持つ（ADR-0022）。
 *
 * 一覧の中の操作は、サーバーの返事で読み直すまで表示が変わらない。どこを押したのかが
 * 分かるよう、行だけでなく操作の種類まで覚える（削除中と更新中では目印を出す場所が
 * 違う）。同じ行への同時操作は受け付けない（結果の取り違えを防ぐ）。
 *
 * 判定は ref で行う。state の更新は次の描画までに反映されないので、`disabled` だけに
 * 任せると、同じフレームで続けて押された 2 つ目を止められない。
 */
import { useRef, useState } from 'react'

export function usePendingRows<A extends string>(): {
  /** その行で実行中の操作（実行していなければ `null`）。 */
  pendingActionOf: (rowId: number) => A | null
  runForRow: (rowId: number, action: A, request: () => Promise<void>) => Promise<void>
} {
  const runningRef = useRef<Map<number, A>>(new Map())
  const [running, setRunning] = useState<ReadonlyMap<number, A>>(new Map())

  const runForRow = async (rowId: number, action: A, request: () => Promise<void>) => {
    if (runningRef.current.has(rowId)) return
    runningRef.current.set(rowId, action)
    setRunning(new Map(runningRef.current))
    try {
      await request()
    } finally {
      runningRef.current.delete(rowId)
      setRunning(new Map(runningRef.current))
    }
  }

  return {
    pendingActionOf: (rowId) => running.get(rowId) ?? null,
    runForRow,
  }
}
