/**
 * システム管理者どうしの付け外し（ADR-0079 §1・§5。要 `system:manage`）。
 *
 * システム管理者はテナントに属さない人。足すと招待のメールが届き、本人がパスワードを決める。
 * 自分は外せず、最後の 1 人も外せない（サーバーが断る）。
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

interface Administrator {
  id: number
  email: string
  username: string
  is_active: boolean
}

export function SystemAdministratorsPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const { user } = useAuth()
  const [administrators, setAdministrators] = useState<Administrator[]>([])
  const [adding, setAdding] = useState(false)
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
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
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {administrators.map((administrator) => (
              <tr key={administrator.id}>
                <th scope="row">{administrator.username}</th>
                <td>{administrator.email}</td>
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
