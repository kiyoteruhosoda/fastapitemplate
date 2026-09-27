/**
 * IdP（SSO）との連携。セキュリティ画面の「連携」区画に出す（ADR-0040）。
 *
 * 連携を始めると IdP へ画面ごと遷移し、戻ってきたときはこの画面に
 * `?sso_link=linked` か `?sso_link_error=<コード>` が付いている。
 *
 * 見出しと区画の枠は呼び出し側（SecurityPage）が持ち、ここは中身だけを描く。
 */
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { ActionButton } from './ActionButton'
import { useToast } from './ToastNotification'

interface FederatedLink {
  available: boolean
  display_name: string
  linked: boolean
  linked_at: string | null
  can_unlink: boolean
}

/** 連携の戻りに付くエラーコード -> 文言のキー。 */
const LINK_ERRORS: Record<string, string> = {
  sso_identity_taken: 'security.linkTaken',
  sso_already_linked: 'security.linkAlreadyLinked',
  sso_link_session_mismatch: 'security.linkSessionMismatch',
}

export function FederatedIdentityControls() {
  const { t, locale } = useI18n()
  const { notify } = useToast()
  const [link, setLink] = useState<FederatedLink | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()

  const reload = useCallback(
    () =>
      api
        .get<FederatedLink>('/api/auth/sso/link')
        .then(setLink)
        .catch(() => {
          setLink(null)
        }),
    [],
  )

  useEffect(() => {
    void reload()
  }, [reload])

  // IdP から戻ってきた直後の 1 回だけ、結果を伝えてクエリを片付ける。
  // 残したままにすると、画面を再読み込みするたびに同じ報せが出る。
  useEffect(() => {
    const linked = params.get('sso_link')
    const failed = params.get('sso_link_error')
    if (!linked && !failed) return
    if (linked) notify('success', t('security.linkDone'))
    if (failed) setError(LINK_ERRORS[failed] ?? 'security.linkFailed')
    params.delete('sso_link')
    params.delete('sso_link_error')
    setParams(params, { replace: true })
  }, [params, setParams, notify, t])

  const [startLink, starting] = usePendingAction(async () => {
    setError(null)
    try {
      const started = await api.post<{ authorization_url: string }>('/api/auth/sso/link/start')
      // ⚠ サーバーは 303 を返さない。往復状態の Cookie を受け取ってから、
      //   画面が自分で IdP へ遷移する（認証切れを 401 で受けられるようにするため）。
      window.location.assign(started.authorization_url)
    } catch (err) {
      setError(errorMessageKey(err))
    }
  })

  const [removeLink, removing] = usePendingAction(async () => {
    setError(null)
    try {
      await api.delete('/api/auth/sso/link')
      await reload()
      notify('success', t('security.linkRemoved'))
    } catch (err) {
      setError(errorMessageKey(err))
    }
  })

  if (link === null) return <p className="loading">{t('common.loading')}</p>
  if (!link.available) return null

  return (
    <>
      {error && <p className="error">{t(error)}</p>}
      {link.linked ? (
        <>
          <p>
            {t('security.linkedTo', { provider: link.display_name })}
            {link.linked_at ? ` (${new Date(link.linked_at).toLocaleString(locale)})` : ''}
          </p>
          {link.can_unlink ? (
            <ActionButton type="button" pending={removing} onClick={removeLink}>
              {t('security.unlink')}
            </ActionButton>
          ) : (
            // ⚠ 外すと入れなくなる。押せないボタンではなく理由を出す。
            <p className="hint">{t('security.lastEntrance')}</p>
          )}
        </>
      ) : (
        <>
          <p>{t('security.notLinked')}</p>
          <ActionButton type="button" pending={starting} onClick={startLink}>
            {t('security.link', { provider: link.display_name })}
          </ActionButton>
        </>
      )}
    </>
  )
}
