/**
 * Handling for requests refused with "please sign in again" (ADR-0076 §10).
 *
 * Adding/removing a passkey and changing the email address are refused by the server with
 * `reauthentication_required` once some time has passed since sign-in. When refused, tell the
 * user and send them to the sign-in screen. The destination (the current screen) is carried
 * along, so signing in again brings them back (ADR-0077 §8).
 */
import { useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { signInPathFor } from '../services/returnTo'

export const REAUTHENTICATION_REQUIRED = 'reauthentication_required'

/**
 * Error code of a failure (`ApiError`'s `code`). Checked by shape, so it also works with the
 * fake `api` in tests.
 */
function codeOf(error: unknown): unknown {
  return typeof error === 'object' && error !== null && 'code' in error ? error.code : undefined
}

/** If the failure requires signing in again, notify, send to the sign-in screen and return `true`. */
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
