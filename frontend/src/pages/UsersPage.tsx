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
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'

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
  // 更新中の行（同じ行への同時更新を防ぐ）。ref は判定用、state は描画用。
  const pendingRef = useRef<Set<number>>(new Set())
  const [pending, setPending] = useState<number[]>([])

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

  /**
   * 1 行分の更新。終わるまでその行の次の操作を受け付けない。
   *
   * 判定は ref で行う（描画を待つ `disabled` だけに任せると、同じフレームで
   * 続けて押された 2 つ目を止められない）。
   */
  const runExclusively = async (userId: number, action: () => Promise<unknown>) => {
    if (pendingRef.current.has(userId)) return
    pendingRef.current.add(userId)
    setPending([...pendingRef.current])
    try {
      await action()
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    } finally {
      pendingRef.current.delete(userId)
      setPending([...pendingRef.current])
    }
  }

  const update = (user: User, changes: Partial<Pick<User, 'roles' | 'is_active'>>) =>
    runExclusively(user.id, () => api.put(`/api/admin/users/${user.id}`, changes))

  /** ロールの付け外し。複数ロールを許す（外すと権限は減る）。 */
  const toggleRole = (user: User, name: string) =>
    update(user, {
      roles: user.roles.includes(name)
        ? user.roles.filter((r) => r !== name)
        : [...user.roles, name],
    })

  const remove = (user: User) =>
    runExclusively(user.id, () => api.delete(`/api/admin/users/${user.id}`))

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
              {roleNames.map((name) => (
                <th key={name}>{name}</th>
              ))}
              <th>{t('common.active')}</th>
              <th>{t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const busy = pending.includes(user.id)
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
                    <button
                      type="button"
                      className="button-danger"
                      disabled={busy}
                      onClick={() => {
                        void remove(user)
                      }}
                    >
                      {t('common.delete')}
                    </button>
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
