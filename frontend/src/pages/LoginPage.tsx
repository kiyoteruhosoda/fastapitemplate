import { useEffect, useId, useState, type SubmitEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { ActionButton } from '../components/ActionButton'
import { AppMark } from '../components/AppMark'
import { PasswordInput } from '../components/PasswordInput'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { ApiError, errorMessageKey } from '../services/api'
import { REDIRECT_TO_PARAM, sanitizeRedirectTo } from '../services/returnTo'
import { markSilentSsoTried, maySilentSso } from '../services/silentSso'
import { fetchSsoProvider, startSsoLogin, type SsoProvider } from '../services/sso'
import { forgotPasswordPathOf, rememberTenant } from '../services/tenantEntrance'
import { isPasskeyCancellation, isPasskeySupported } from '../services/webauthn'
import { RECONNECT_INTERVAL_MS, useAuth } from '../store/AuthContext'

/** Credentials input -> (if two-factor authentication is enabled) one-time code input. */
type Step = 'credentials' | 'totp'

export function LoginPage() {
  const { t } = useI18n()
  const { login, loginWithPasskey } = useAuth()
  const navigate = useNavigate()
  // Entry tenant (`/t/<slug>/login`). The shared entry point if absent (ADR-0079 §4)
  const { tenant } = useParams<{ tenant?: string }>()
  const [step, setStep] = useState<Step>('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [params] = useSearchParams()
  // The page the user was trying to open (ADR-0077 §8). Whichever entry they use, return here once in.
  const destination = sanitizeRedirectTo(params.get(REDIRECT_TO_PARAM))
  // SSO settings can change after startup, so ask every time the page opens.
  // Note: **no entry points until it is fetched.** It fails when the server is unreachable (e.g.
  // during a release), and then no entry point works. Showing the default (password fields) would
  // leave the user stranded on a page without the IdP button once the server is back. Keep asking
  // until connected.
  const [sso, setSso] = useState<SsoProvider | null>(null)
  const [ssoUnreachable, setSsoUnreachable] = useState(false)
  // If signed in at the IdP, the user gets in without pressing the button (ADR-0077 §9). Whether to
  // try is decided by the URL at open.
  // Note: **once it decides to try, it does not render the entry points.** Rendering and then
  // redirecting flashes the login page.
  const [silentAllowed] = useState(() => maySilentSso(params))

  useEffect(() => {
    let timer: number | undefined
    let cancelled = false
    const ask = () => {
      fetchSsoProvider(tenant)
        .then((provider) => {
          if (cancelled) return
          if (provider.enabled && silentAllowed && markSilentSsoTried()) {
            rememberTenant(tenant)
            startSsoLogin(destination, tenant, { silent: true })
            return
          }
          setSso(provider)
          setSsoUnreachable(false)
        })
        .catch(() => {
          if (cancelled) return
          setSsoUnreachable(true)
          timer = window.setTimeout(ask, RECONNECT_INTERVAL_MS)
        })
    }
    ask()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [tenant, destination, silentAllowed])

  // When the server-side round trip (``/api/auth/sso/callback``) fails, it comes back here
  // with ``?sso_error=<code>``. The page decides the displayed text.
  useEffect(() => {
    const code = params.get('sso_error')
    if (code) setError(`error.${code}`)
  }, [params])

  // After signing out at the IdP it comes back with `?signed_out=1` (ADR-0077 §2).
  // **Without showing it, it cannot be told apart from being kicked out by expiry.**
  useEffect(() => {
    if (params.get('signed_out')) setNotice('login.signedOut')
  }, [params])
  // The password field has a visibility toggle, so it is tied with `for` instead of wrapped in `<label>`
  // (two labelable elements inside make the association ambiguous).
  const passwordId = useId()

  const [submit, submitting] = usePendingAction(async (e: SubmitEvent) => {
    e.preventDefault()
    setError(null)
    setNotice(null)
    try {
      await login(email, password, step === 'totp' ? totpCode : undefined, tenant)
      void navigate(destination)
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 'unknown_error'
      if (code === 'totp_required') {
        // A code request is not an error but the next step. Proceed to code input as guidance.
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
      void navigate(destination)
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

  if (!sso) {
    return (
      <div className="auth-page">
        <div className="card">
          <AppMark size={44} />
          <h1>{t('login.title')}</h1>
          <p className={ssoUnreachable ? 'hint' : 'loading'}>
            <span className="spinner" aria-hidden="true" />{' '}
            {t(ssoUnreachable ? 'common.unreachable' : 'common.loading')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <form className="card" onSubmit={submit}>
        <AppMark size={44} />
        <h1>{step === 'totp' ? t('login.totpTitle') : t('login.title')}</h1>
        {notice && <p className="hint">{t(notice)}</p>}
        {error && <p className="error">{t(error)}</p>}

        {sso.enabled && (
          <ActionButton
            type="button"
            pending={false}
            onClick={() => {
              rememberTenant(tenant)
              startSsoLogin(destination, tenant)
            }}
          >
            {t('login.withSso', { provider: sso.display_name })}
          </ActionButton>
        )}
        {/* When the entry is closed, do not show things that would return 403 when pressed
            (ADR-0076 §3 decision 2). */}
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
            <Link to={forgotPasswordPathOf(tenant)}>{t('login.forgot')}</Link>
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
