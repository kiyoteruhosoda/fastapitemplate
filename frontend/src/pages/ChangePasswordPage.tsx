import { useState, type FormEvent } from 'react'

import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

export function ChangePasswordPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')

  const submit = async (e: FormEvent) => {
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
  }

  return (
    <form
      className="card"
      onSubmit={(e) => {
        void submit(e)
      }}
    >
      <h1>{t('changePassword.title')}</h1>
      <label>
        {t('changePassword.current')}
        <input
          type="password"
          value={current}
          onChange={(e) => {
            setCurrent(e.target.value)
          }}
          required
        />
      </label>
      <label>
        {t('changePassword.new')}
        <input
          type="password"
          value={next}
          onChange={(e) => {
            setNext(e.target.value)
          }}
          minLength={8}
          required
        />
      </label>
      <button type="submit">{t('changePassword.submit')}</button>
    </form>
  )
}
