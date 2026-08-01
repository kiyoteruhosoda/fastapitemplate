/**
 * ユーザー管理（要 `user:manage`）。
 *
 * ロールは 1 人に複数割り当てられる。追加フォームでは複数選択でき、一覧では
 * ロールごとの列のチェックで付け外しする（ロール × ユーザーの対応表）。
 * 利用者自身がどのロールで操作するかはヘッダーで切り替える（ADR-0017）。
 */
import { useEffect, useState, type FormEvent } from 'react'

import { PasswordInput } from '../components/PasswordInput'
import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

interface User {
  id: number
  email: string
  username: string
  is_active: boolean
  roles: string[]
}

interface Role {
  id: number
  name: string
}

export function UsersPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [selectedRoles, setSelectedRoles] = useState<string[]>([])

  const reload = () => api.get<User[]>('/api/admin/users').then(setUsers)

  useEffect(() => {
    void reload()
    void api
      .get<Role[]>('/api/admin/roles')
      .then(setRoles)
      .catch(() => {
        setRoles([])
      })
  }, [])

  const toggleSelected = (name: string) => {
    setSelectedRoles((current) =>
      current.includes(name) ? current.filter((r) => r !== name) : [...current, name],
    )
  }

  const create = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.post('/api/admin/users', { email, username, password, roles: selectedRoles })
      setEmail('')
      setUsername('')
      setPassword('')
      setSelectedRoles([])
      await reload()
      notify('success', t('common.saved'))
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  }

  /** 1 人のロールの付け外し。複数ロールを許す（外すと権限は減る）。 */
  const toggleRole = async (user: User, name: string) => {
    const next = user.roles.includes(name)
      ? user.roles.filter((r) => r !== name)
      : [...user.roles, name]
    try {
      await api.put(`/api/admin/users/${user.id}`, { roles: next })
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  }

  const toggleActive = async (user: User) => {
    await api.put(`/api/admin/users/${user.id}`, { is_active: !user.is_active })
    await reload()
  }

  const remove = async (user: User) => {
    await api.delete(`/api/admin/users/${user.id}`)
    await reload()
  }

  return (
    <div className="card">
      <h1>{t('users.title')}</h1>
      <form
        className="inline-form"
        onSubmit={(e) => {
          void create(e)
        }}
      >
        <input
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
          }}
          placeholder={t('common.email')}
          required
        />
        <input
          value={username}
          onChange={(e) => {
            setUsername(e.target.value)
          }}
          placeholder={t('common.username')}
          required
        />
        <PasswordInput
          autoComplete="new-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
          }}
          placeholder={t('common.password')}
          minLength={8}
          required
        />
        <fieldset className="chip-choice">
          <legend>{t('users.roles')}</legend>
          {roles.map((r) => (
            <label key={r.id} className="chip-option">
              <input
                type="checkbox"
                checked={selectedRoles.includes(r.name)}
                onChange={() => {
                  toggleSelected(r.name)
                }}
              />
              {r.name}
            </label>
          ))}
        </fieldset>
        <button type="submit">{t('users.add')}</button>
      </form>
      <p className="hint">{t('users.rolesHint')}</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{t('common.email')}</th>
              <th>{t('common.username')}</th>
              {roles.map((r) => (
                <th key={r.id}>{r.name}</th>
              ))}
              <th>{t('common.active')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.id}</td>
                <td>{user.email}</td>
                <td>{user.username}</td>
                {roles.map((r) => (
                  <td key={r.id}>
                    <input
                      type="checkbox"
                      aria-label={`${user.username}: ${r.name}`}
                      checked={user.roles.includes(r.name)}
                      onChange={() => {
                        void toggleRole(user, r.name)
                      }}
                    />
                  </td>
                ))}
                <td>
                  <input
                    type="checkbox"
                    aria-label={`${user.username}: ${t('common.active')}`}
                    checked={user.is_active}
                    onChange={() => {
                      void toggleActive(user)
                    }}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className="button-danger"
                    onClick={() => {
                      void remove(user)
                    }}
                  >
                    {t('common.delete')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
