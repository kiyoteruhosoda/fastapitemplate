import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useI18n } from '../i18n'
import { ApiError, errorMessageKey } from '../services/api'
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
  const [passkeyBusy, setPasskeyBusy] = useState(false)

  const submit = async (e: FormEvent) => {
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
  }

  const signInWithPasskey = async () => {
    setError(null)
    setPasskeyBusy(true)
    try {
      await loginWithPasskey()
      navigate('/')
    } catch (err) {
      if (isPasskeyCancellation(err)) {
        setError('error.passkey_cancelled')
      } else {
        setError(errorMessageKey(err))
      }
    } finally {
      setPasskeyBusy(false)
    }
  }

  const backToCredentials = () => {
    setStep('credentials')
    setTotpCode('')
    setError(null)
  }

  return (
    <div className="auth-page">
      <form
        className="card"
        onSubmit={(e) => {
          void submit(e)
        }}
      >
        <h1>{step === 'totp' ? t('login.totpTitle') : t('login.title')}</h1>
        {error && <p className="error">{t(error)}</p>}

        {step === 'credentials' ? (
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
            <label>
              {t('login.password')}
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                }}
                required
              />
            </label>
            <button type="submit">{t('login.submit')}</button>
            {isPasskeySupported() && (
              <button
                type="button"
                onClick={() => {
                  void signInWithPasskey()
                }}
                disabled={passkeyBusy}
              >
                {passkeyBusy ? t('common.loading') : t('login.withPasskey')}
              </button>
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
            <button type="submit">{t('login.submit')}</button>
            <button type="button" onClick={backToCredentials}>
              {t('common.back')}
            </button>
          </>
        )}
      </form>
    </div>
  )
}
