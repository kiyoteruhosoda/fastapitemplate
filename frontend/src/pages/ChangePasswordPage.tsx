import { useId, useState, type FormEvent } from 'react'

import { PasswordInput } from '../components/PasswordInput'
import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

export function ChangePasswordPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  // 表示切り替えボタンを持つ欄は `<label>` で囲まず `for` で結ぶ（LoginPage 参照）。
  const currentId = useId()
  const nextId = useId()

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
      <button type="submit">{t('changePassword.submit')}</button>
    </form>
  )
}
