/**
 * 二要素認証（TOTP）の有効化・無効化。プロフィールページの「二要素認証」区画に
 * 出す（ADR-0020）。
 *
 * 有効化は「登録の開始（QR の取得）→ 確認コードの入力」の 2 段階。無効にするときも
 * 現在のコードを求める（開いたままの画面から勝手に外せないようにするため）。
 *
 * 見出しと区画の枠は呼び出し側（ProfilePage）が持ち、ここは中身だけを描く。
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { useToast } from './ToastNotification'

interface TwoFactorStatus {
  enabled: boolean
  enrolling: boolean
}

interface TotpEnrollment {
  secret: string
  otpauth_uri: string
  qr_code: string
}

/** 確認コードの入力欄（有効化の確認・無効化の双方で使う）。 */
function CodeField({
  value,
  onChange,
  autoFocus,
}: {
  value: string
  onChange: (value: string) => void
  autoFocus?: boolean
}) {
  const { t } = useI18n()
  return (
    <label>
      {t('security.code')}
      <input
        type="text"
        inputMode="numeric"
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
        }}
        autoFocus={autoFocus ?? false}
        required
      />
    </label>
  )
}

export function TwoFactorControls() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [status, setStatus] = useState<TwoFactorStatus | null>(null)
  const [enrollment, setEnrollment] = useState<TotpEnrollment | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)

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

  useEffect(() => {
    void reloadStatus()
  }, [reloadStatus])

  const startEnrollment = async () => {
    setError(null)
    try {
      setEnrollment(await api.post<TotpEnrollment>('/api/account/security/two-factor/enrollment'))
      setCode('')
    } catch (err) {
      setError(errorMessageKey(err))
    }
  }

  /** 有効化の確認・無効化はどちらも「コードを送って状態を引き直す」だけ違う。 */
  const submitCode = async (path: string, successKey: string) => {
    setError(null)
    try {
      await api.post(path, { code })
      setEnrollment(null)
      setCode('')
      await reloadStatus()
      notify('success', t(successKey))
    } catch (err) {
      setError(errorMessageKey(err))
    }
  }

  const onSubmit = (path: string, successKey: string) => (e: FormEvent) => {
    e.preventDefault()
    void submitCode(path, successKey)
  }

  if (status === null) return <p className="loading">{t('common.loading')}</p>

  if (status.enabled) {
    return (
      <form
        className="profile-form"
        onSubmit={onSubmit(
          '/api/account/security/two-factor/removal',
          'security.twoFactorDisabled',
        )}
      >
        {error && <p className="error">{t(error)}</p>}
        <p>{t('security.twoFactorOn')}</p>
        <CodeField value={code} onChange={setCode} />
        <button type="submit">{t('security.disableTwoFactor')}</button>
      </form>
    )
  }

  if (enrollment) {
    return (
      <form
        className="card-inset"
        onSubmit={onSubmit(
          '/api/account/security/two-factor/confirmation',
          'security.twoFactorEnabled',
        )}
      >
        {error && <p className="error">{t(error)}</p>}
        <p>{t('security.scanQr')}</p>
        <img className="qr-code" src={enrollment.qr_code} alt={t('security.qrAlt')} />
        <p>
          {t('security.manualSecret')} <code>{enrollment.secret}</code>
        </p>
        <CodeField value={code} onChange={setCode} autoFocus />
        <button type="submit">{t('security.confirm')}</button>
      </form>
    )
  }

  return (
    <>
      {error && <p className="error">{t(error)}</p>}
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
  )
}
