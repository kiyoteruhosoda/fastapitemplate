/**
 * Password change. Shown in the "Change password" section of the profile page (ADR-0080 §4).
 *
 * The heading and section frame belong to the caller (ProfilePage); this renders only the content.
 */
import { useId, useState, type SubmitEvent } from 'react'

import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { ActionButton } from './ActionButton'
import { PasswordInput } from './PasswordInput'
import { useToast } from './ToastNotification'

export function PasswordChangeForm() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  // Fields with a visibility toggle are tied with `for` instead of wrapped in `<label>` (see LoginPage).
  const currentId = useId()
  const nextId = useId()

  const [submit, submitting] = usePendingAction(async (e: SubmitEvent) => {
    e.preventDefault()
    try {
      await api.post('/api/auth/change-password', {
        current_password: current,
        new_password: next,
      })
      notify('success', t('common.saved'))
      setCurrent('')
      setNext('')
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  return (
    <form className="settings-form" onSubmit={submit}>
      <div className="field">
        <label htmlFor={currentId}>{t('changePassword.current')}</label>
        <PasswordInput
          id={currentId}
          autoComplete="current-password"
          value={current}
          onChange={(e) => {
            setCurrent(e.target.value)
          }}
          required
        />
      </div>
      <div className="field">
        <label htmlFor={nextId}>{t('changePassword.new')}</label>
        <PasswordInput
          id={nextId}
          autoComplete="new-password"
          value={next}
          onChange={(e) => {
            setNext(e.target.value)
          }}
          minLength={8}
          required
        />
      </div>
      <ActionButton type="submit" pending={submitting}>
        {t('changePassword.submit')}
      </ActionButton>
    </form>
  )
}
