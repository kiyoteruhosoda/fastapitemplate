/**
 * Enabling / disabling two-factor authentication (TOTP). Shown in the "Two-factor
 * authentication" section of the profile page (ADR-0080 §4).
 *
 * Enabling takes two steps: "start enrollment (get the QR)" -> "enter the confirmation code".
 * Disabling also asks for the current code (so it cannot be removed from a page left open).
 *
 * The heading and section frame belong to the caller (ProfilePage); this renders only the content.
 */
import { useCallback, useEffect, useState, type SubmitEvent } from 'react'

import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { ActionButton } from './ActionButton'
import { useToast } from './ToastNotification'

interface TwoFactorStatus {
  enabled: boolean
  enrolling: boolean
  /** Whether the app settings require it (ADR-0093). When true, no way to disable it is shown. */
  required: boolean
}

interface TotpEnrollment {
  secret: string
  otpauth_uri: string
  qr_code: string
}

const CONFIRMATION_PATH = '/api/account/security/two-factor/confirmation'

/** Confirmation code field (used both to confirm enabling and to disable). */
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

export function TwoFactorControls({ onEnabled }: { onEnabled?: () => Promise<void> }) {
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

  const [startEnrollment, starting] = usePendingAction(async () => {
    setError(null)
    try {
      setEnrollment(await api.post<TotpEnrollment>('/api/account/security/two-factor/enrollment'))
      setCode('')
    } catch (err) {
      setError(errorMessageKey(err))
    }
  })

  /**
   * Confirming enablement and disabling both just "send the code and reload the state".
   * Only one of them is on screen at a time, so a single running flag is enough.
   */
  const [submitCode, submitting] = usePendingAction(
    async (e: SubmitEvent, path: string, successKey: string) => {
      e.preventDefault()
      setError(null)
      try {
        await api.post(path, { code })
        setEnrollment(null)
        setCode('')
        await reloadStatus()
        notify('success', t(successKey))
        if (path === CONFIRMATION_PATH) await onEnabled?.()
      } catch (err) {
        setError(errorMessageKey(err))
      }
    },
  )

  const onSubmit = (path: string, successKey: string) => (e: SubmitEvent) => {
    submitCode(e, path, successKey)
  }

  if (status === null) return <p className="loading">{t('common.loading')}</p>

  if (status.enabled && status.required) return <p>{t('security.twoFactorRequired')}</p>

  if (status.enabled) {
    return (
      <form
        className="settings-form"
        onSubmit={onSubmit(
          '/api/account/security/two-factor/removal',
          'security.twoFactorDisabled',
        )}
      >
        {error && <p className="error">{t(error)}</p>}
        <p>{t('security.twoFactorOn')}</p>
        <CodeField value={code} onChange={setCode} />
        <ActionButton type="submit" pending={submitting}>
          {t('security.disableTwoFactor')}
        </ActionButton>
      </form>
    )
  }

  if (enrollment) {
    return (
      <form
        className="card-inset"
        onSubmit={onSubmit(CONFIRMATION_PATH, 'security.twoFactorEnabled')}
      >
        {error && <p className="error">{t(error)}</p>}
        <p>{t('security.scanQr')}</p>
        <img className="qr-code" src={enrollment.qr_code} alt={t('security.qrAlt')} />
        <p>
          {t('security.manualSecret')} <code>{enrollment.secret}</code>
        </p>
        <CodeField value={code} onChange={setCode} autoFocus />
        <ActionButton type="submit" pending={submitting}>
          {t('security.confirm')}
        </ActionButton>
      </form>
    )
  }

  return (
    <>
      {error && <p className="error">{t(error)}</p>}
      <p>{t('security.twoFactorOff')}</p>
      <ActionButton type="button" pending={starting} onClick={startEnrollment}>
        {status.enrolling ? t('security.restartEnrollment') : t('security.enable')}
      </ActionButton>
    </>
  )
}
