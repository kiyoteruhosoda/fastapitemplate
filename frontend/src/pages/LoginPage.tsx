import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useI18n } from '../i18n'
import { ApiError } from '../services/api'
import { useAuth } from '../store/AuthContext'

export function LoginPage() {
  const { t } = useI18n()
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err instanceof ApiError ? `error.${err.code}` : 'error.unknown_error')
    }
  }

  return (
    <div className="auth-page">
      <form className="card" onSubmit={submit}>
        <h1>{t('login.title')}</h1>
        {error && <p className="error">{t(error)}</p>}
        <label>
          {t('login.email')}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          {t('login.password')}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit">{t('login.submit')}</button>
        <Link to="/forgot-password">{t('login.forgot')}</Link>
      </form>
    </div>
  )
}
