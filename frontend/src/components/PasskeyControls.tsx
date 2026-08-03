/**
 * パスキーの登録・削除。プロフィールページの「パスキー」区画に出す（ADR-0020）。
 *
 * 見出しと区画の枠は呼び出し側（ProfilePage）が持ち、ここは中身だけを描く。
 */
import { useCallback, useEffect, useState } from 'react'

import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import {
  createPasskey,
  isPasskeyCancellation,
  isPasskeySupported,
  type PasskeyChallenge,
} from '../services/webauthn'
import { ActionButton } from './ActionButton'
import { useToast } from './ToastNotification'

interface Passkey {
  id: number
  name: string
  transports: string[]
  created_at: string | null
  last_used_at: string | null
}

/** 登録済みのパスキーの一覧（1 件も無ければ呼び出し側が代わりの文を出す）。 */
function PasskeyTable({
  passkeys,
  onRemove,
  removingId,
}: {
  passkeys: Passkey[]
  onRemove: (id: number) => void
  /** 削除中のパスキー（その行だけスピナーを出す）。 */
  removingId: number | null
}) {
  const { t, locale } = useI18n()
  const formatDate = (value: string | null) =>
    value ? new Date(value).toLocaleString(locale) : '—'

  return (
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
                <ActionButton
                  type="button"
                  pending={removingId === passkey.id}
                  disabled={removingId !== null}
                  onClick={() => {
                    onRemove(passkey.id)
                  }}
                >
                  {t('common.delete')}
                </ActionButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PasskeyControls() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [passkeys, setPasskeys] = useState<Passkey[]>([])
  const [name, setName] = useState('')
  const [removingId, setRemovingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(
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
    void reload()
  }, [reload])

  const [register, registering] = usePendingAction(async () => {
    setError(null)
    try {
      const challenge = await api.post<PasskeyChallenge>(
        '/api/account/security/passkeys/registration',
      )
      const credential = await createPasskey(challenge.public_key)
      await api.post('/api/account/security/passkeys', {
        challenge_id: challenge.challenge_id,
        credential,
        name: name.trim() || null,
      })
      setName('')
      await reload()
      notify('success', t('security.passkeyRegistered'))
    } catch (err) {
      setError(isPasskeyCancellation(err) ? 'error.passkey_cancelled' : errorMessageKey(err))
    }
  })

  const remove = async (id: number) => {
    setError(null)
    setRemovingId(id)
    try {
      await api.delete(`/api/account/security/passkeys/${id}`)
      await reload()
    } catch (err) {
      setError(errorMessageKey(err))
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <>
      {error && <p className="error">{t(error)}</p>}
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
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                }}
                placeholder={t('security.passkeyNamePlaceholder')}
              />
            </label>
            <ActionButton type="button" pending={registering} onClick={register}>
              {t('security.addPasskey')}
            </ActionButton>
          </div>
        </>
      )}
      {passkeys.length === 0 ? (
        <p>{t('security.noPasskeys')}</p>
      ) : (
        <PasskeyTable
          passkeys={passkeys}
          removingId={removingId}
          onRemove={(id) => {
            void remove(id)
          }}
        />
      )}
    </>
  )
}
