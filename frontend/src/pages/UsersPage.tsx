/**
 * ユーザー管理（要 `user:manage`）。
 *
 * ロールは 1 人に複数割り当てられる。追加フォームでは複数選択でき、一覧では
 * ロールごとの列のチェックで付け外しする（ロール × ユーザーの対応表）。
 * 利用者自身がどのロールで操作するかはヘッダーで切り替える（ADR-0017）。
 *
 * 更新は 1 行ずつ直列に行う。ロールの更新はリスト全体の置き換えなので、同じ行へ
 * 続けてチェックを入れると、2 つ目が古い `roles` から差分を作って 1 つ目を打ち消す。
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { PasswordInput } from '../components/PasswordInput'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { usePendingRows } from '../hooks/usePendingRows'
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

/** 行の中で実行しうる操作（実行中の目印をどこに出すかが変わる）。 */
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
   * 列に出すロール。ロール一覧（`GET /api/admin/roles`）が読めない場合でも、
   * **既に割り当てられているロール名**から列を補う。読めないのは `user:manage`
   * より更に絞った権限のときで（ADR-0018）、そのときに割り当ての表示ごと
   * 消えてしまわないようにする。
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

  const [create, creating] = usePendingAction(async (e: FormEvent) => {
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
  })

  /** 1 行分の更新。終わるまでその行の次の操作を受け付けない。 */
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

  /** ロールの付け外し。複数ロールを許す（外すと権限は減る）。 */
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
      <h1>{t('users.title')}</h1>
      <form className="inline-form" onSubmit={create}>
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
        <ActionButton type="submit" pending={creating}>
          {t('users.add')}
        </ActionButton>
      </form>
      <p className="hint">{t('users.rolesHint')}</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{t('common.email')}</th>
              <th>{t('common.username')}</th>
              {roleNames.map((name) => (
                <th key={name}>{name}</th>
              ))}
              <th>{t('common.active')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const rowAction = pendingActionOf(user.id)
              const busy = rowAction !== null
              return (
                <tr key={user.id}>
                  <td>{user.id}</td>
                  <td>{user.email}</td>
                  <td>{user.username}</td>
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
