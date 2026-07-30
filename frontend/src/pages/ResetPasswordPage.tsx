import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

export function ResetPasswordPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await api.post('/api/auth/reset-password', {
        token: params.get('token') ?? '',
        new_password: password,
      })
      navigate('/login')
    } catch (err) {
      setError(errorMessageKey(err))
    }
  }

  return (
    <div className="auth-page">
      <form
        className="card"
        onSubmit={(e) => {
          void submit(e)
        }}
      >
        <h1>{t('reset.title')}</h1>
        {error && <p className="error">{t(error)}</p>}
        <label>
          {t('reset.newPassword')}
          <input
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
            }}
            minLength={8}
            required
          />
        </label>
        <button type="submit">{t('reset.submit')}</button>
      </form>
    </div>
  )
}
