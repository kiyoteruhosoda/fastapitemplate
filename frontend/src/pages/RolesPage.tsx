import { useEffect, useState } from 'react'

import { ActionButton } from '../components/ActionButton'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { usePendingRows } from '../hooks/usePendingRows'
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

/** 行の中で実行しうる操作（実行中の目印をどこに出すかが変わる）。 */
type RowAction = 'update' | 'removal'

export function RolesPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [roles, setRoles] = useState<Role[]>([])
  const [permissions, setPermissions] = useState<Permission[]>([])
  const [name, setName] = useState('')
  const { pendingActionOf, runForRow } = usePendingRows<RowAction>()

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

  const [create, creating] = usePendingAction(async () => {
    if (!name.trim()) return
    try {
      await api.post('/api/admin/roles', { name, permissions: [] })
      setName('')
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  /** 1 行分の更新。終わるまでその行の次の操作を受け付けない。 */
  const runExclusively = (roleId: number, action: RowAction, request: () => Promise<unknown>) =>
    runForRow(roleId, action, async () => {
      try {
        await request()
        await reload()
      } catch (err) {
        notify('error', t(errorMessageKey(err)))
      }
    })

  const togglePermission = (role: Role, code: string) => {
    const next = role.permissions.includes(code)
      ? role.permissions.filter((c) => c !== code)
      : [...role.permissions, code]
    return runExclusively(role.id, 'update', () =>
      api.put(`/api/admin/roles/${role.id}`, { permissions: next }),
    )
  }

  const remove = (role: Role) =>
    runExclusively(role.id, 'removal', () => api.delete(`/api/admin/roles/${role.id}`))

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
        <ActionButton type="button" pending={creating} onClick={create}>
          {t('roles.add')}
        </ActionButton>
      </div>
      <div className="table-scroll">
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
            {roles.map((role) => {
              const rowAction = pendingActionOf(role.id)
              const busy = rowAction !== null
              return (
                <tr key={role.id}>
                  <td>{role.name}</td>
                  {permissions.map((p) => (
                    <td key={p.id}>
                      <input
                        type="checkbox"
                        aria-label={`${role.name}: ${p.code}`}
                        checked={role.permissions.includes(p.code)}
                        disabled={busy}
                        onChange={() => {
                          void togglePermission(role, p.code)
                        }}
                      />
                    </td>
                  ))}
                  <td>
                    <ActionButton
                      type="button"
                      pending={rowAction === 'removal'}
                      disabled={busy}
                      onClick={() => {
                        void remove(role)
                      }}
                    >
                      {t('common.delete')}
                    </ActionButton>
                    {/* チェックの付け外しは押しても表示が変わらないので、行に目印を出す。 */}
                    {rowAction === 'update' && (
                      <span className="spinner" role="status" aria-label={t('common.processing')} />
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
