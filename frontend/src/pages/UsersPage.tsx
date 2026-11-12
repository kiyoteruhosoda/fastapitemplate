/**
 * User management (requires `user:manage`).
 *
 * A user can have several roles. The add form allows multiple selection, and the list toggles
 * them with a checkbox per role column (a role x user matrix).
 * Which role a user acts as is switched in the header (ADR-0078 §1).
 *
 * Updates are serialized per row. A role update replaces the whole list, so checking the same
 * row twice in a row would make the second compute its diff from the stale `roles` and undo
 * the first.
 */
import { useEffect, useMemo, useState, type SubmitEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
import { PasswordInput } from '../components/PasswordInput'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { usePendingRows } from '../hooks/usePendingRows'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

/** The **ways this user can get into this app** (ADR-0076 §7). */
interface SignInEntrances {
  password: boolean
  totp: boolean
  passkeys: number
  identity_providers: string[]
}

interface User {
  id: number
  email: string
  username: string
  is_active: boolean
  roles: string[]
  entrances: SignInEntrances
}

/**
 * Turns the ways in into a short list (ADR-0076 §7).
 *
 * Note: **IdP-side multi-factor does not show here.** Only the entry points this app knows
 * about can be shown, and that is exactly what "there are two authentication systems" means.
 */
function entranceLabels(entrances: SignInEntrances, t: (key: string) => string): string[] {
  const labels: string[] = []
  if (entrances.password) labels.push(t('users.entrance.password'))
  if (entrances.totp) labels.push(t('users.entrance.totp'))
  if (entrances.passkeys > 0) labels.push(`${t('users.entrance.passkey')} ×${entrances.passkeys}`)
  if (entrances.identity_providers.length > 0) labels.push(t('users.entrance.sso'))
  return labels
}

interface Role {
  id: number
  name: string
}

/** Operations that can run within a row (decides where the running marker shows). */
type RowAction = 'update' | 'removal'

export function UsersPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [selectedRoles, setSelectedRoles] = useState<string[]>([])
  const [adding, setAdding] = useState(false)
  const { pendingActionOf, runForRow } = usePendingRows<RowAction>()

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

  /**
   * Roles shown as columns. Even if the role list (`GET /api/admin/roles`) cannot be read,
   * columns are filled in from **role names already assigned**. It cannot be read with a
   * permission narrower than `user:manage` (ADR-0078 §2), and this keeps the assignment display
   * from disappearing entirely in that case.
   */
  const roleNames = useMemo(() => {
    const catalog = roles.map((r) => r.name)
    const assigned = [...new Set(users.flatMap((u) => u.roles))]
      .filter((name) => !catalog.includes(name))
      .sort()
    return [...catalog, ...assigned]
  }, [roles, users])

  const toggleSelected = (name: string) => {
    setSelectedRoles((current) =>
      current.includes(name) ? current.filter((r) => r !== name) : [...current, name],
    )
  }

  const [create, creating] = usePendingAction(async (e: SubmitEvent) => {
    e.preventDefault()
    try {
      await api.post('/api/admin/users', { email, username, password, roles: selectedRoles })
      setEmail('')
      setUsername('')
      setPassword('')
      setSelectedRoles([])
      setAdding(false)
      await reload()
      notify('success', t('common.saved'))
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  /** Update one row. Further operations on that row are not accepted until it finishes. */
  const runExclusively = (userId: number, action: RowAction, request: () => Promise<unknown>) =>
    runForRow(userId, action, async () => {
      try {
        await request()
        await reload()
      } catch (err) {
        notify('error', t(errorMessageKey(err)))
      }
    })

  const update = (user: User, changes: Partial<Pick<User, 'roles' | 'is_active'>>) =>
    runExclusively(user.id, 'update', () => api.put(`/api/admin/users/${user.id}`, changes))

  /** Toggle a role. Multiple roles are allowed (removing one reduces permissions). */
  const toggleRole = (user: User, name: string) =>
    update(user, {
      roles: user.roles.includes(name)
        ? user.roles.filter((r) => r !== name)
        : [...user.roles, name],
    })

  const remove = (user: User) =>
    runExclusively(user.id, 'removal', () => api.delete(`/api/admin/users/${user.id}`))

  return (
    <div className="card">
      <div className="card-head">
        <h1>{t('users.title')}</h1>
        <button
          type="button"
          className="button-primary"
          onClick={() => {
            setAdding(true)
          }}
        >
          {t('users.add')}
        </button>
      </div>
      {adding && (
        <FormDialog
          title={t('users.add')}
          onClose={() => {
            setAdding(false)
          }}
        >
          <form className="dialog-form" onSubmit={create}>
            <label>
              {t('common.email')}
              <input
                type="email"
                autoComplete="off"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                }}
                required
              />
            </label>
            <label>
              {t('common.username')}
              <input
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value)
                }}
                required
              />
            </label>
            {/* The password field has a visibility toggle, so it cannot be wrapped in `<label>`. */}
            <div className="field">
              <label htmlFor="new-user-password">{t('common.password')}</label>
              <PasswordInput
                id="new-user-password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                }}
                minLength={8}
                required
              />
            </div>
            <fieldset className="chip-choice">
              <legend>{t('users.roles')}</legend>
              {roleNames.map((name) => (
                <label key={name} className="chip-option">
                  <input
                    type="checkbox"
                    checked={selectedRoles.includes(name)}
                    onChange={() => {
                      toggleSelected(name)
                    }}
                  />
                  {name}
                </label>
              ))}
            </fieldset>
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
      <p className="hint">{t('users.rolesHint')}</p>
      <div className="table-scroll">
        <table className="matrix">
          <thead>
            <tr>
              <th>{t('common.username')}</th>
              <th>ID</th>
              <th>{t('common.email')}</th>
              {/* Role columns grow in number, so write them vertically (see the `.matrix` rules). */}
              {roleNames.map((name) => (
                <th key={name} className="vertical">
                  {name}
                </th>
              ))}
              <th>{t('common.active')}</th>
              <th>{t('users.entrances')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const rowAction = pendingActionOf(user.id)
              const busy = rowAction !== null
              return (
                <tr key={user.id}>
                  {/* Column that stays during horizontal scroll (fixed by `.matrix`). A human-readable
                      name comes first so it is clear which row is being operated on. */}
                  <th scope="row">{user.username}</th>
                  <td>{user.id}</td>
                  <td>{user.email}</td>
                  {roleNames.map((name) => (
                    <td key={name}>
                      <input
                        type="checkbox"
                        aria-label={`${user.username}: ${name}`}
                        checked={user.roles.includes(name)}
                        disabled={busy}
                        onChange={() => {
                          void toggleRole(user, name)
                        }}
                      />
                    </td>
                  ))}
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`${user.username}: ${t('common.active')}`}
                      checked={user.is_active}
                      disabled={busy}
                      onChange={() => {
                        void update(user, { is_active: !user.is_active })
                      }}
                    />
                  </td>
                  <td>
                    {/* The ways in cannot be changed here (this is an inventory display).
                        Each is revoked on its own side. */}
                    {entranceLabels(user.entrances, t).join(' / ') || t('users.entrance.none')}
                  </td>
                  <td>
                    <ActionButton
                      type="button"
                      className="button-danger"
                      pending={rowAction === 'removal'}
                      disabled={busy}
                      onClick={() => {
                        void remove(user)
                      }}
                    >
                      {t('common.delete')}
                    </ActionButton>
                    {/* Toggling a checkbox shows no change on press, so mark the row. */}
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
