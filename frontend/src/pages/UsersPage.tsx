import { useEffect, useState, type FormEvent } from 'react'

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
  const [role, setRole] = useState('member')

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

  const create = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.post('/api/admin/users', {
        email,
        username,
        password,
        roles: [role],
      })
      setEmail('')
      setUsername('')
      setPassword('')
      await reload()
      notify('success', t('common.saved'))
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
        <input
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
          }}
          placeholder={t('common.password')}
          minLength={8}
          required
        />
        <select
          value={role}
          onChange={(e) => {
            setRole(e.target.value)
          }}
        >
          {roles.map((r) => (
            <option key={r.id} value={r.name}>
              {r.name}
            </option>
          ))}
        </select>
        <button type="submit">{t('users.add')}</button>
      </form>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{t('common.email')}</th>
              <th>{t('common.username')}</th>
              <th>Roles</th>
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
                <td>{user.roles.join(', ')}</td>
                <td>
                  <input
                    type="checkbox"
                    checked={user.is_active}
                    onChange={() => {
                      void toggleActive(user)
                    }}
                  />
                </td>
                <td>
                  <button
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
