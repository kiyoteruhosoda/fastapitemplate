/**
 * 「もう一度サインインしてください」で断られたときの手当て（ADR-0076 §10）。
 *
 * パスキーの追加・削除とメールアドレスの変更は、サインインしてから少し経つと
 * サーバが `reauthentication_required` で断る。断られたら、そのことを知らせて
 * ログイン画面へ送る。行き先（いまの画面）を持たせるので、入り直すと戻ってくる（ADR-0077 §8）。
 */
import { useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { signInPathFor } from '../services/returnTo'

export const REAUTHENTICATION_REQUIRED = 'reauthentication_required'

/** 失敗のエラーコード（`ApiError` の `code`）。形で見る（試験の偽物の `api` でも同じに動く）。 */
function codeOf(error: unknown): unknown {
  return typeof error === 'object' && error !== null && 'code' in error ? error.code : undefined
}

/** 入り直しが要る失敗なら、知らせてログイン画面へ送り `true` を返す。 */
export function useReauthentication(): (error: unknown) => boolean {
  const { t } = useI18n()
  const { notify } = useToast()
  const navigate = useNavigate()
  const location = useLocation()

  return useCallback(
    (error: unknown) => {
      if (codeOf(error) !== REAUTHENTICATION_REQUIRED) return false
      notify('error', t(`error.${REAUTHENTICATION_REQUIRED}`))
      void navigate(signInPathFor(location))
      return true
    },
    [location, navigate, notify, t],
  )
}
