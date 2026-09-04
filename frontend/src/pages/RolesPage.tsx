import { useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
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
  const [adding, setAdding] = useState(false)
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

  const [create, creating] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await api.post('/api/admin/roles', { name, permissions: [] })
      setName('')
      setAdding(false)
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
      <div className="card-head">
        <h1>{t('roles.title')}</h1>
        <button
          type="button"
          className="button-primary"
          onClick={() => {
            setAdding(true)
          }}
        >
          {t('roles.add')}
        </button>
      </div>
      {adding && (
        <FormDialog
          title={t('roles.add')}
          onClose={() => {
            setAdding(false)
          }}
        >
          <form className="dialog-form" onSubmit={create}>
            <label>
              {t('roles.name')}
              <input
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                }}
                required
              />
            </label>
            <p className="hint">{t('roles.addHint')}</p>
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => {
                  setAdding(false)
                }}
              >
                {t('common.cancel')}
              </button>
              <ActionButton type="submit" pending={creating}>
                {t('common.add')}
              </ActionButton>
            </div>
          </form>
        </FormDialog>
      )}
      <div className="table-scroll">
        <table className="matrix">
          <thead>
            <tr>
              <th>{t('roles.name')}</th>
              {/* 権限コードは長いので縦組みにする（`.matrix` の指定を参照）。 */}
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
                  {/* 横スクロールしても残す列（`.matrix` が固定する）。 */}
                  <th scope="row">{role.name}</th>
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
                      className="button-danger"
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
