/** アカウントのセキュリティ設定（二要素認証・パスキー）。 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import {
  createPasskey,
  isPasskeyCancellation,
  isPasskeySupported,
  type PasskeyChallenge,
} from '../services/webauthn'

interface TwoFactorStatus {
  enabled: boolean
  enrolling: boolean
}

interface TotpEnrollment {
  secret: string
  otpauth_uri: string
  qr_code: string
}

interface Passkey {
  id: number
  name: string
  transports: string[]
  created_at: string | null
  last_used_at: string | null
}

export function SecurityPage() {
  const { t, locale } = useI18n()
  const { notify } = useToast()

  const [status, setStatus] = useState<TwoFactorStatus | null>(null)
  const [enrollment, setEnrollment] = useState<TotpEnrollment | null>(null)
  const [code, setCode] = useState('')
  const [twoFactorError, setTwoFactorError] = useState<string | null>(null)

  const [passkeys, setPasskeys] = useState<Passkey[]>([])
  const [passkeyName, setPasskeyName] = useState('')
  const [passkeyBusy, setPasskeyBusy] = useState(false)
  const [passkeyError, setPasskeyError] = useState<string | null>(null)

  const reloadStatus = useCallback(
    () =>
      api
        .get<TwoFactorStatus>('/api/account/security/two-factor')
        .then(setStatus)
        .catch(() => {
          setStatus(null)
        }),
    [],
  )

  const reloadPasskeys = useCallback(
    () =>
      api
        .get<Passkey[]>('/api/account/security/passkeys')
        .then(setPasskeys)
        .catch(() => {
          setPasskeys([])
        }),
    [],
  )

  useEffect(() => {
    void reloadStatus()
    void reloadPasskeys()
  }, [reloadStatus, reloadPasskeys])

  const formatDate = (value: string | null) =>
    value ? new Date(value).toLocaleString(locale) : '—'

  // --- 二要素認証 -------------------------------------------------------

  const startEnrollment = async () => {
    setTwoFactorError(null)
    try {
      setEnrollment(await api.post<TotpEnrollment>('/api/account/security/two-factor/enrollment'))
      setCode('')
    } catch (err) {
      setTwoFactorError(errorMessageKey(err))
    }
  }

  const confirmEnrollment = async (e: FormEvent) => {
    e.preventDefault()
    setTwoFactorError(null)
    try {
      await api.post('/api/account/security/two-factor/confirmation', { code })
      setEnrollment(null)
      setCode('')
      await reloadStatus()
      notify('success', t('security.twoFactorEnabled'))
    } catch (err) {
      setTwoFactorError(errorMessageKey(err))
    }
  }

  const disableTwoFactor = async (e: FormEvent) => {
    e.preventDefault()
    setTwoFactorError(null)
    try {
      await api.post('/api/account/security/two-factor/removal', { code })
      setCode('')
      await reloadStatus()
      notify('success', t('security.twoFactorDisabled'))
    } catch (err) {
      setTwoFactorError(errorMessageKey(err))
    }
  }

  // --- パスキー ---------------------------------------------------------

  const registerPasskey = async () => {
    setPasskeyError(null)
    setPasskeyBusy(true)
    try {
      const challenge = await api.post<PasskeyChallenge>(
        '/api/account/security/passkeys/registration',
      )
      const credential = await createPasskey(challenge.public_key)
      await api.post('/api/account/security/passkeys', {
        challenge_id: challenge.challenge_id,
        credential,
        name: passkeyName.trim() || null,
      })
      setPasskeyName('')
      await reloadPasskeys()
      notify('success', t('security.passkeyRegistered'))
    } catch (err) {
      setPasskeyError(isPasskeyCancellation(err) ? 'error.passkey_cancelled' : errorMessageKey(err))
    } finally {
      setPasskeyBusy(false)
    }
  }

  const removePasskey = async (id: number) => {
    setPasskeyError(null)
    try {
      await api.delete(`/api/account/security/passkeys/${id}`)
      await reloadPasskeys()
    } catch (err) {
      setPasskeyError(errorMessageKey(err))
    }
  }

  return (
    <div className="card">
      <h1>{t('security.title')}</h1>

      <section>
        <h2>{t('security.twoFactor')}</h2>
        {twoFactorError && <p className="error">{t(twoFactorError)}</p>}
        {status === null ? (
          <p className="loading">{t('common.loading')}</p>
        ) : status.enabled ? (
          <form
            className="inline-form"
            onSubmit={(e) => {
              void disableTwoFactor(e)
            }}
          >
            <p>{t('security.twoFactorOn')}</p>
            <label>
              {t('security.code')}
              <input
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value)
                }}
                required
              />
            </label>
            <button type="submit">{t('security.disableTwoFactor')}</button>
          </form>
        ) : enrollment ? (
          <form
            className="card-inset"
            onSubmit={(e) => {
              void confirmEnrollment(e)
            }}
          >
            <p>{t('security.scanQr')}</p>
            <img className="qr-code" src={enrollment.qr_code} alt={t('security.qrAlt')} />
            <p>
              {t('security.manualSecret')} <code>{enrollment.secret}</code>
            </p>
            <label>
              {t('security.code')}
              <input
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value)
                }}
                autoFocus
                required
              />
            </label>
            <button type="submit">{t('security.confirm')}</button>
          </form>
        ) : (
          <>
            <p>{t('security.twoFactorOff')}</p>
            <button
              type="button"
              onClick={() => {
                void startEnrollment()
              }}
            >
              {status.enrolling ? t('security.restartEnrollment') : t('security.enable')}
            </button>
          </>
        )}
      </section>

      <section>
        <h2>{t('security.passkeys')}</h2>
        {passkeyError && <p className="error">{t(passkeyError)}</p>}
        {!isPasskeySupported() ? (
          <p>{t('security.passkeyUnsupported')}</p>
        ) : (
          <>
            <p>{t('security.passkeyHint')}</p>
            <div className="inline-form">
              <label>
                {t('security.passkeyName')}
                <input
                  type="text"
                  value={passkeyName}
                  onChange={(e) => {
                    setPasskeyName(e.target.value)
                  }}
                  placeholder={t('security.passkeyNamePlaceholder')}
                />
              </label>
              <button
                type="button"
                onClick={() => {
                  void registerPasskey()
                }}
                disabled={passkeyBusy}
              >
                {passkeyBusy ? t('common.loading') : t('security.addPasskey')}
              </button>
            </div>
          </>
        )}
        {passkeys.length === 0 ? (
          <p>{t('security.noPasskeys')}</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('security.passkeyName')}</th>
                  <th>{t('security.registeredAt')}</th>
                  <th>{t('security.lastUsedAt')}</th>
                  <th>{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {passkeys.map((passkey) => (
                  <tr key={passkey.id}>
                    <td>{passkey.name}</td>
                    <td>{formatDate(passkey.created_at)}</td>
                    <td>{formatDate(passkey.last_used_at)}</td>
                    <td>
                      <button
                        type="button"
                        onClick={() => {
                          void removePasskey(passkey.id)
                        }}
                      >
                        {t('common.delete')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
