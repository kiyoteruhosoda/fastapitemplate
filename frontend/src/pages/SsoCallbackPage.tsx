/**
 * SSO の戻り先（ADR-0025）。
 *
 * IdP からの戻りはサーバーの `/api/auth/sso/callback` が受け、**トークンではなく
 * 1 回限りの引き換え券**を付けてこの画面へ転送してくる。URL は履歴・Referer・
 * プロキシのログに残るので、トークンそのものは載せない。
 *
 * この画面がやるのは券をトークンへ換えることだけで、利用者に見せるものは無い。
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
  // 券は 1 回限り。React の開発時の二重実行で 2 度換えにいかないよう控える。
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
        // ログイン画面と同じ形（``?sso_error=<コード>``）で返す。サーバーからの
        // 転送とここからの転送で、画面側の読み方を分けないため。
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
