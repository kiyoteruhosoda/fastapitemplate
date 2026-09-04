import { useEffect, useId, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { ActionButton } from '../components/ActionButton'
import { PasswordInput } from '../components/PasswordInput'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { ApiError, errorMessageKey } from '../services/api'
import { fetchSsoProvider, startSsoLogin, type SsoProvider } from '../services/sso'
import { isPasskeyCancellation, isPasskeySupported } from '../services/webauthn'
import { useAuth } from '../store/AuthContext'

/** 資格情報の入力 → （二要素認証が有効なら）ワンタイムコードの入力。 */
type Step = 'credentials' | 'totp'

export function LoginPage() {
  const { t } = useI18n()
  const { login, loginWithPasskey } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [params] = useSearchParams()
  // SSO の設定は起動後に変えられるので、画面を開くたびに問い合わせる。
  // 取れないうちは**ローカルの入口を出したままにする**（問い合わせに失敗しただけで
  // 全員が締め出されるのを避ける）。
  const [sso, setSso] = useState<SsoProvider>({
    enabled: false,
    display_name: '',
    local_login_enabled: true,
  })

  useEffect(() => {
    fetchSsoProvider()
      .then(setSso)
      .catch(() => undefined)
  }, [])

  // サーバー側の往復（``/api/auth/sso/callback``）が失敗すると、ここへ
  // ``?sso_error=<コード>`` で戻ってくる。表示文言は画面が決める。
  useEffect(() => {
    const code = params.get('sso_error')
    if (code) setError(`error.${code}`)
  }, [params])
  // パスワード欄は表示切り替えボタンを持つため `<label>` で囲まず `for` で結ぶ
  // （labelable な要素を 2 つ入れると対応付けが曖昧になる）。
  const passwordId = useId()

  const [submit, submitting] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await login(email, password, step === 'totp' ? totpCode : undefined)
      navigate('/')
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 'unknown_error'
      if (code === 'totp_required') {
        // コード要求はエラーではなく次の手順。案内としてコード入力へ進める。
        setStep('totp')
        setTotpCode('')
        setError(null)
        return
      }
      if (code === 'invalid_totp') setTotpCode('')
      setError(errorMessageKey(err))
    }
  })

  const [signInWithPasskey, passkeyPending] = usePendingAction(async () => {
    setError(null)
    try {
      await loginWithPasskey()
      navigate('/')
    } catch (err) {
      if (isPasskeyCancellation(err)) {
        setError('error.passkey_cancelled')
      } else {
        setError(errorMessageKey(err))
      }
    }
  })

  const backToCredentials = () => {
    setStep('credentials')
    setTotpCode('')
    setError(null)
  }

  return (
    <div className="auth-page">
      <form className="card" onSubmit={submit}>
        <h1>{step === 'totp' ? t('login.totpTitle') : t('login.title')}</h1>
        {error && <p className="error">{t(error)}</p>}

        {sso.enabled && (
          <ActionButton
            type="button"
            pending={false}
            onClick={() => {
              startSsoLogin('/')
            }}
          >
            {t('login.withSso', { provider: sso.display_name })}
          </ActionButton>
        )}
        {/* 入口が閉じているときは、押しても 403 になるものを出さない（ADR-0026 決定 2）。 */}
        {!sso.local_login_enabled ? (
          <p className="hint">{t('login.localDisabled')}</p>
        ) : step === 'credentials' ? (
          <>
            <label>
              {t('login.email')}
              <input
                type="email"
                autoComplete="username webauthn"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                }}
                required
              />
            </label>
            <div className="field">
              <label htmlFor={passwordId}>{t('login.password')}</label>
              <PasswordInput
                id={passwordId}
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                }}
                required
              />
            </div>
            <ActionButton type="submit" pending={submitting}>
              {t('login.submit')}
            </ActionButton>
            {isPasskeySupported() && (
              <ActionButton type="button" pending={passkeyPending} onClick={signInWithPasskey}>
                {t('login.withPasskey')}
              </ActionButton>
            )}
            <Link to="/forgot-password">{t('login.forgot')}</Link>
          </>
        ) : (
          <>
            <p>{t('login.totpHint')}</p>
            <label>
              {t('login.totpCode')}
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                value={totpCode}
                onChange={(e) => {
                  setTotpCode(e.target.value)
                }}
                autoFocus
                required
              />
            </label>
            <ActionButton type="submit" pending={submitting}>
              {t('login.submit')}
            </ActionButton>
            <button type="button" onClick={backToCredentials}>
              {t('common.back')}
            </button>
          </>
        )}
      </form>
    </div>
  )
}
