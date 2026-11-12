/**
 * SSO return target (ADR-0077 §1).
 *
 * The return from the IdP is received by the server at `/api/auth/sso/callback`, which
 * redirects here with a **one-time exchange ticket, not a token**. URLs end up in history,
 * Referer and proxy logs, so the token itself is never put there.
 *
 * All this page does is exchange the ticket for tokens; there is nothing to show the user.
 */
import { useEffect, useRef, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'

import { useI18n } from '../i18n'
import { ApiError } from '../services/api'
import { useAuth } from '../store/AuthContext'

export function SsoCallbackPage() {
  const { t } = useI18n()
  const { completeSsoLogin } = useAuth()
  const [params] = useSearchParams()
  const ticket = params.get('ticket')
  const [destination, setDestination] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The ticket is single-use. Guard so React's development double run does not exchange it twice.
  const exchanged = useRef(false)

  useEffect(() => {
    if (!ticket) {
      setError('sso_ticket_invalid')
      return
    }
    if (exchanged.current) return
    exchanged.current = true
    completeSsoLogin(ticket)
      .then(setDestination)
      .catch((err: unknown) => {
        // Return in the same form as the login page (``?sso_error=<code>``), so the page does
        // not need to read redirects from the server and from here differently.
        setError(err instanceof ApiError ? err.code : 'sso_error')
      })
  }, [ticket, completeSsoLogin])

  if (destination) return <Navigate to={destination} replace />
  if (error) return <Navigate to={`/login?sso_error=${encodeURIComponent(error)}`} replace />
  return (
    <div className="auth-page">
      <p className="card">{t('login.ssoCompleting')}</p>
    </div>
  )
}
