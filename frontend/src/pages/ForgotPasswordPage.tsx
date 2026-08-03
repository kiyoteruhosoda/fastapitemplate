import { useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api } from '../services/api'

export function ForgotPasswordPage() {
  const { t } = useI18n()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)

  const [submit, submitting] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    await api.post('/api/auth/forgot-password', { email })
    setSent(true)
  })

  return (
    <div className="auth-page">
      <form className="card" onSubmit={submit}>
        <h1>{t('forgot.title')}</h1>
        {sent ? (
          <p>{t('forgot.sent')}</p>
        ) : (
          <>
            <label>
              {t('login.email')}
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                }}
                required
              />
            </label>
            <ActionButton type="submit" pending={submitting}>
              {t('forgot.submit')}
            </ActionButton>
          </>
        )}
      </form>
    </div>
  )
}
