/**
 * Notice that the session could not be continued (ADR-0104).
 *
 * The API layer (`api.ts`) reports when it couldn't continue the session after a 401, and the auth
 * state (`AuthContext`) listens and signs the user out. The screen moves to sign-in (destination in
 * `redirect_to`; drafts kept by `useSessionDraft`).
 */
type Listener = () => void

const listeners = new Set<Listener>()

/** Listen for the notice. Call the return value to stop listening. */
export function subscribeSessionEnded(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function reportSessionEnded(): void {
  for (const listener of listeners) listener()
}
