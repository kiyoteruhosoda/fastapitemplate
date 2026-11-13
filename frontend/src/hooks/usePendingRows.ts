/**
 * Tracks the "operation in progress" per list row (ADR-0080 §5).
 *
 * Operations in a list don't change the display until it is reloaded from the server's reply.
 * To show what was pressed, remember the operation kind as well as the row (deleting and
 * updating show the indicator in different places). Concurrent operations on the same row are
 * rejected (prevents mixing up results).
 *
 * The check uses a ref. State updates don't apply until the next render, so relying on
 * `disabled` alone can't stop a second press in the same frame.
 */
import { useRef, useState } from 'react'

export function usePendingRows<A extends string>(): {
  /** The operation running on that row (`null` when none). */
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
