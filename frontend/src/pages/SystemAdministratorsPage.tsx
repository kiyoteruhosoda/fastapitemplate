/**
 * テナントの外の人（運用者・サポート担当）の付け外し（ADR-0079 §1・§5・ADR-0084 §4。要 `system:manage`）。
 *
 * テナントの外の人はテナントに属さない。足すときにロール（運用者かサポート担当か）を選び、
 * 招待のメールが届いた本人がパスワードを決める。自分は外せず、最後の運用者も外せない（サーバーが断る）。
 */
import { useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { usePendingRows } from '../hooks/usePendingRows'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { useAuth } from '../store/AuthContext'

/** テナントの外の人に付けるロール（`master_data.SYSTEM_ROLES`） */
const SYSTEM_ROLES = ['system-admin', 'system-support'] as const
type SystemRole = (typeof SYSTEM_ROLES)[number]

interface Administrator {
  id: number
  email: string
  username: string
  is_active: boolean
  role: string | null
}

export function SystemAdministratorsPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const { user } = useAuth()
  const [administrators, setAdministrators] = useState<Administrator[]>([])
  const [adding, setAdding] = useState(false)
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [role, setRole] = useState<SystemRole>('system-admin')
  const { pendingActionOf, runForRow } = usePendingRows<'removal'>()

  const reload = () =>
    api.get<Administrator[]>('/api/system/administrators').then(setAdministrators)

  useEffect(() => {
    void reload()
  }, [])

  const [add, saving] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    try {
      const designation = await api.post<{ invitation_sent: boolean }>(
        '/api/system/administrators',
        {
          email,
          username,
          role,
        },
      )
      notify(
        'success',
        t(
          designation.invitation_sent ? 'tenants.invitationSent' : 'systemAdmins.invitationNotSent',
        ),
      )
      setAdding(false)
      setEmail('')
      setUsername('')
      setRole('system-admin')
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  const remove = (administrator: Administrator) =>
    runForRow(administrator.id, 'removal', async () => {
      try {
        await api.delete(`/api/system/administrators/${String(administrator.id)}`)
        await reload()
      } catch (err) {
        notify('error', t(errorMessageKey(err)))
      }
    })

  return (
    <div className="card">
      <div className="card-head">
        <h1>{t('systemAdmins.title')}</h1>
        <button
          type="button"
          className="button-primary"
          onClick={() => {
            setAdding(true)
          }}
        >
          {t('systemAdmins.add')}
        </button>
      </div>
      <p className="hint">{t('systemAdmins.hint')}</p>
      {adding && (
        <FormDialog
          title={t('systemAdmins.add')}
          onClose={() => {
            setAdding(false)
          }}
        >
          <form className="dialog-form" onSubmit={add}>
            <label>
              {t('login.email')}
              <input
                type="email"
                value={email}
                required
                onChange={(e) => {
                  setEmail(e.target.value)
                }}
              />
            </label>
            <label>
              {t('tenants.adminName')}
              <input
                value={username}
                required
                onChange={(e) => {
                  setUsername(e.target.value)
                }}
              />
            </label>
            <label>
              {t('systemAdmins.role')}
              <select
                value={role}
                onChange={(e) => {
                  setRole(e.target.value as SystemRole)
                }}
              >
                {SYSTEM_ROLES.map((name) => (
                  <option key={name} value={name}>
                    {t(`systemAdmins.role.${name}`)}
                  </option>
                ))}
              </select>
            </label>
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => {
                  setAdding(false)
                }}
              >
                {t('common.cancel')}
              </button>
              <ActionButton type="submit" pending={saving}>
                {t('common.add')}
              </ActionButton>
            </div>
          </form>
        </FormDialog>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('tenants.adminName')}</th>
              <th>{t('login.email')}</th>
              <th>{t('systemAdmins.role')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {administrators.map((administrator) => (
              <tr key={administrator.id}>
                <th scope="row">{administrator.username}</th>
                <td>{administrator.email}</td>
                <td>{administrator.role ? t(`systemAdmins.role.${administrator.role}`) : ''}</td>
                <td className="row-actions">
                  {administrator.id !== user?.user_id && (
                    <ActionButton
                      type="button"
                      className="button-danger"
                      pending={pendingActionOf(administrator.id) === 'removal'}
                      onClick={() => {
                        void remove(administrator)
                      }}
                    >
                      {t('common.delete')}
                    </ActionButton>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
