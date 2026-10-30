/**
 * テナントの管理（ADR-0079 §1・§5。要 `tenant:manage`）。システム管理者だけが使う。
 *
 * テナントの登録・連携先の変更・停止・削除と、テナント管理者の指名。⚠ **中身は出さない。**
 * 並べるのは台帳と人数だけ。指名した人には招待のメールが届き、本人がパスワードを決める
 * （システム管理者はパスワードを知らない）。SSO のテナントなら、その人が IdP で初めて
 * 入ったときに席を受け取る。
 */
import { useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { usePendingRows } from '../hooks/usePendingRows'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { loginPathOf } from '../services/tenantEntrance'

interface Tenant {
  id: number
  slug: string
  display_name: string
  issuer: string | null
  client_id: string | null
  status: 'active' | 'suspended'
  member_count: number
  active_member_count: number
}

interface Designation {
  user_id: number
  invitation_sent: boolean
}

/** 開いているダイアログ。 */
type Dialog =
  | { kind: 'create' }
  | { kind: 'edit'; tenant: Tenant }
  | { kind: 'designate'; tenant: Tenant }
  | { kind: 'delete'; tenant: Tenant }

interface Form {
  slug: string
  displayName: string
  issuer: string
  clientId: string
  email: string
  username: string
  confirmation: string
}

const EMPTY_FORM: Form = {
  slug: '',
  displayName: '',
  issuer: '',
  clientId: '',
  email: '',
  username: '',
  confirmation: '',
}

type RowAction = 'status'

export function TenantsPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [form, setForm] = useState<Form>(EMPTY_FORM)
  const { pendingActionOf, runForRow } = usePendingRows<RowAction>()

  const reload = () => api.get<Tenant[]>('/api/system/tenants').then(setTenants)

  useEffect(() => {
    void reload()
  }, [])

  const open = (next: Dialog) => {
    const tenant = next.kind === 'create' ? null : next.tenant
    setForm({
      ...EMPTY_FORM,
      displayName: tenant?.display_name ?? '',
      issuer: tenant?.issuer ?? '',
      clientId: tenant?.client_id ?? '',
    })
    setDialog(next)
  }

  /** 招待を送れたかを知らせる（送れなければ、受け取り方を案内する）。 */
  const announce = (designation: Designation) => {
    notify(
      'success',
      t(designation.invitation_sent ? 'tenants.invitationSent' : 'tenants.invitationNotSent'),
    )
  }

  const submitByKind = async (current: Dialog) => {
    const person = { email: form.email, username: form.username }
    if (current.kind === 'create') {
      const created = await api.post<{ designation: Designation }>('/api/system/tenants', {
        slug: form.slug,
        display_name: form.displayName,
        issuer: form.issuer || null,
        client_id: form.clientId || null,
        first_admin: person,
      })
      announce(created.designation)
    } else if (current.kind === 'edit') {
      await api.put(`/api/system/tenants/${String(current.tenant.id)}`, {
        display_name: form.displayName,
        issuer: form.issuer,
        client_id: form.clientId,
      })
    } else if (current.kind === 'designate') {
      announce(
        await api.post<Designation>(
          `/api/system/tenants/${String(current.tenant.id)}/administrators`,
          person,
        ),
      )
    } else {
      await api.delete(`/api/system/tenants/${String(current.tenant.id)}`)
    }
  }

  const [submit, submitting] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    if (dialog === null) return
    try {
      await submitByKind(dialog)
      setDialog(null)
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  const toggleStatus = (tenant: Tenant) =>
    runForRow(tenant.id, 'status', async () => {
      try {
        await api.put(`/api/system/tenants/${String(tenant.id)}`, {
          status: tenant.status === 'active' ? 'suspended' : 'active',
        })
        await reload()
      } catch (err) {
        notify('error', t(errorMessageKey(err)))
      }
    })

  const field = (
    key: keyof Form,
    labelKey: string,
    props: { required?: boolean; type?: string },
  ) => (
    <label>
      {t(labelKey)}
      <input
        type={props.type ?? 'text'}
        value={form[key]}
        required={props.required ?? false}
        onChange={(e) => {
          setForm({ ...form, [key]: e.target.value })
        }}
      />
    </label>
  )

  const titleOf = (current: Dialog): string => {
    if (current.kind === 'create') return t('tenants.add')
    if (current.kind === 'edit') return t('tenants.edit')
    if (current.kind === 'designate') return t('tenants.designate')
    return t('tenants.delete')
  }

  const canSubmit = dialog?.kind !== 'delete' || form.confirmation === dialog.tenant.slug

  return (
    <div className="card">
      <div className="card-head">
        <h1>{t('tenants.title')}</h1>
        <button
          type="button"
          className="button-primary"
          onClick={() => {
            open({ kind: 'create' })
          }}
        >
          {t('tenants.add')}
        </button>
      </div>
      <p className="hint">{t('tenants.hint')}</p>
      {dialog && (
        <FormDialog
          title={titleOf(dialog)}
          onClose={() => {
            setDialog(null)
          }}
        >
          <form className="dialog-form" onSubmit={submit}>
            {dialog.kind === 'create' && field('slug', 'tenants.slug', { required: true })}
            {(dialog.kind === 'create' || dialog.kind === 'edit') && (
              <>
                {field('displayName', 'tenants.displayName', { required: true })}
                {field('issuer', 'tenants.issuer', {})}
                {field('clientId', 'tenants.clientId', {})}
                <p className="hint">{t('tenants.ssoHint')}</p>
              </>
            )}
            {(dialog.kind === 'create' || dialog.kind === 'designate') && (
              <>
                {field('email', 'tenants.adminEmail', { required: true, type: 'email' })}
                {field('username', 'tenants.adminName', { required: true })}
                <p className="hint">{t('tenants.designateHint')}</p>
              </>
            )}
            {dialog.kind === 'delete' && (
              <>
                <p className="error">{t('tenants.deleteWarning', { slug: dialog.tenant.slug })}</p>
                {field('confirmation', 'tenants.deleteConfirm', { required: true })}
              </>
            )}
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => {
                  setDialog(null)
                }}
              >
                {t('common.cancel')}
              </button>
              <ActionButton
                type="submit"
                pending={submitting}
                disabled={!canSubmit}
                className={dialog.kind === 'delete' ? 'button-danger' : undefined}
              >
                {dialog.kind === 'delete' ? t('common.delete') : t('common.save')}
              </ActionButton>
            </div>
          </form>
        </FormDialog>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('tenants.displayName')}</th>
              <th>{t('tenants.entrance')}</th>
              <th>{t('tenants.sso')}</th>
              <th>{t('tenants.members')}</th>
              <th>{t('tenants.status')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((tenant) => {
              const busy = pendingActionOf(tenant.id) !== null
              const suspended = tenant.status === 'suspended'
              return (
                <tr key={tenant.id}>
                  <th scope="row">{tenant.display_name}</th>
                  <td>
                    <code>{loginPathOf(tenant.slug)}</code>
                  </td>
                  <td>{tenant.issuer ? t('tenants.ssoOn') : t('tenants.ssoOff')}</td>
                  <td>
                    {t('tenants.memberCount', {
                      active: String(tenant.active_member_count),
                      total: String(tenant.member_count),
                    })}
                  </td>
                  <td>{t(suspended ? 'tenants.suspended' : 'tenants.active')}</td>
                  <td className="row-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        open({ kind: 'edit', tenant })
                      }}
                    >
                      {t('common.edit')}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        open({ kind: 'designate', tenant })
                      }}
                    >
                      {t('tenants.designate')}
                    </button>
                    <ActionButton
                      type="button"
                      pending={busy}
                      onClick={() => {
                        void toggleStatus(tenant)
                      }}
                    >
                      {t(suspended ? 'tenants.resume' : 'tenants.suspend')}
                    </ActionButton>
                    {suspended && (
                      <button
                        type="button"
                        className="button-danger"
                        disabled={busy}
                        onClick={() => {
                          open({ kind: 'delete', tenant })
                        }}
                      >
                        {t('common.delete')}
                      </button>
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
