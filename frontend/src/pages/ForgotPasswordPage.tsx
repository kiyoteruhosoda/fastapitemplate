import { useState, type FormEvent } from 'react'

import { useI18n } from '../i18n'
import { api } from '../services/api'

export function ForgotPasswordPage() {
  const { t } = useI18n()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    await api.post('/api/auth/forgot-password', { email })
    setSent(true)
  }

  return (
    <div className="auth-page">
      <form
        className="card"
        onSubmit={(e) => {
          void submit(e)
        }}
      >
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
            <button type="submit">{t('forgot.submit')}</button>
          </>
        )}
      </form>
    </div>
  )
}
