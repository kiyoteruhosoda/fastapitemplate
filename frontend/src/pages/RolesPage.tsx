import { useEffect, useState } from 'react'

import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

interface Role {
  id: number
  name: string
  permissions: string[]
}

interface Permission {
  id: number
  code: string
}

export function RolesPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [roles, setRoles] = useState<Role[]>([])
  const [permissions, setPermissions] = useState<Permission[]>([])
  const [name, setName] = useState('')

  const reload = () => api.get<Role[]>('/api/admin/roles').then(setRoles)

  useEffect(() => {
    void reload()
    void api
      .get<Permission[]>('/api/admin/permissions')
      .then(setPermissions)
      .catch(() => {
        setPermissions([])
      })
  }, [])

  const create = async () => {
    if (!name.trim()) return
    try {
      await api.post('/api/admin/roles', { name, permissions: [] })
      setName('')
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  }

  const togglePermission = async (role: Role, code: string) => {
    const next = role.permissions.includes(code)
      ? role.permissions.filter((c) => c !== code)
      : [...role.permissions, code]
    await api.put(`/api/admin/roles/${role.id}`, { permissions: next })
    await reload()
  }

  const remove = async (role: Role) => {
    await api.delete(`/api/admin/roles/${role.id}`)
    await reload()
  }

  return (
    <div className="card">
      <h1>{t('roles.title')}</h1>
      <div className="inline-form">
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
          placeholder="name"
        />
        <button
          onClick={() => {
            void create()
          }}
        >
          {t('roles.add')}
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Role</th>
            {permissions.map((p) => (
              <th key={p.id} className="vertical">
                <code>{p.code}</code>
              </th>
            ))}
            <th>{t('common.actions')}</th>
          </tr>
        </thead>
        <tbody>
          {roles.map((role) => (
            <tr key={role.id}>
              <td>{role.name}</td>
              {permissions.map((p) => (
                <td key={p.id}>
                  <input
                    type="checkbox"
                    checked={role.permissions.includes(p.code)}
                    onChange={() => {
                      void togglePermission(role, p.code)
                    }}
                  />
                </td>
              ))}
              <td>
                <button
                  onClick={() => {
                    void remove(role)
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
  )
}
