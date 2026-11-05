/**
 * ログインを続けられなかった（ADR-0104）ことの知らせ。
 *
 * API の層（`api.ts`）が 401 のあとログインを続けられなかったときに知らせ、認証の状態
 * （`AuthContext`）が聞いて利用者を外す。画面はログイン画面へ移る（行き先は `redirect_to`、
 * 書きかけは `useSessionDraft` が残す）。
 */
type Listener = () => void

const listeners = new Set<Listener>()

/** 知らせを聞く。戻り値で聞くのをやめる。 */
export function subscribeSessionEnded(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function reportSessionEnded(): void {
  for (const listener of listeners) listener()
}
