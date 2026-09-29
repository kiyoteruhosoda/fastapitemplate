/**
 * グループの管理（ADR-0047。要 `group:manage`）。
 *
 * グループは「誰と誰か」を束ねるだけで、権限は持たない（権限はロール）。
 * お知らせの宛先に使う。所属は編集ダイアログで、有効な利用者から選ぶ。
 */
import { useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { usePendingRows } from '../hooks/usePendingRows'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

interface Member {
  id: number
  username: string
  email: string
}

interface Group {
  id: number
  name: string
  description: string
  members: Member[]
}

/** 編集中の内容。`id` が無ければ新規。 */
interface Draft {
  id: number | null
  name: string
  description: string
  memberIds: number[]
}

const EMPTY_DRAFT: Draft = { id: null, name: '', description: '', memberIds: [] }

export function GroupsPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [groups, setGroups] = useState<Group[]>([])
  const [candidates, setCandidates] = useState<Member[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const { pendingActionOf, runForRow } = usePendingRows<'removal'>()

  const reload = () => api.get<Group[]>('/api/admin/groups').then(setGroups)

  useEffect(() => {
    void reload()
    void api
      .get<Member[]>('/api/admin/groups/users')
      .then(setCandidates)
      .catch(() => {
        setCandidates([])
      })
  }, [])

  const toggleMember = (id: number) => {
    setDraft((current) =>
      current === null
        ? current
        : {
            ...current,
            memberIds: current.memberIds.includes(id)
              ? current.memberIds.filter((m) => m !== id)
              : [...current.memberIds, id],
          },
    )
  }

  const [save, saving] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    if (draft === null) return
    const body = { name: draft.name, description: draft.description, member_ids: draft.memberIds }
    try {
      if (draft.id === null) await api.post('/api/admin/groups', body)
      else await api.put(`/api/admin/groups/${String(draft.id)}`, body)
      setDraft(null)
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  const remove = (group: Group) =>
    runForRow(group.id, 'removal', async () => {
      try {
        await api.delete(`/api/admin/groups/${String(group.id)}`)
        await reload()
      } catch (err) {
        notify('error', t(errorMessageKey(err)))
      }
    })

  // 止められた利用者は候補に出ないが、既に所属していれば外せるように並べる。
  const choices = draft
    ? [
        ...candidates,
        ...(groups.find((g) => g.id === draft.id)?.members ?? []).filter(
          (m) => !candidates.some((c) => c.id === m.id),
        ),
      ]
    : []

  return (
    <div className="card">
      <div className="card-head">
        <h1>{t('groups.title')}</h1>
        <button
          type="button"
          className="button-primary"
          onClick={() => {
            setDraft(EMPTY_DRAFT)
          }}
        >
          {t('groups.add')}
        </button>
      </div>
      <p className="hint">{t('groups.hint')}</p>
      {draft && (
        <FormDialog
          title={t(draft.id === null ? 'groups.add' : 'groups.edit')}
          onClose={() => {
            setDraft(null)
          }}
        >
          <form className="dialog-form" onSubmit={save}>
            <label>
              {t('groups.name')}
              <input
                value={draft.name}
                maxLength={100}
                required
                onChange={(e) => {
                  setDraft({ ...draft, name: e.target.value })
                }}
              />
            </label>
            <label>
              {t('groups.description')}
              <input
                value={draft.description}
                maxLength={255}
                onChange={(e) => {
                  setDraft({ ...draft, description: e.target.value })
                }}
              />
            </label>
            <fieldset className="chip-choice">
              <legend>{t('groups.members')}</legend>
              {choices.map((member) => (
                <label key={member.id} className="chip-option">
                  <input
                    type="checkbox"
                    checked={draft.memberIds.includes(member.id)}
                    onChange={() => {
                      toggleMember(member.id)
                    }}
                  />
                  {member.username}
                </label>
              ))}
            </fieldset>
            <div className="dialog-actions">
              <button
                type="button"
                onClick={() => {
                  setDraft(null)
                }}
              >
                {t('common.cancel')}
              </button>
              <ActionButton type="submit" pending={saving}>
                {t('common.save')}
              </ActionButton>
            </div>
          </form>
        </FormDialog>
      )}
      {groups.length === 0 ? (
        <p className="hint">{t('groups.empty')}</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('groups.name')}</th>
                <th>{t('groups.description')}</th>
                <th>{t('groups.members')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => {
                const removing = pendingActionOf(group.id) === 'removal'
                return (
                  <tr key={group.id}>
                    <th scope="row">{group.name}</th>
                    <td>{group.description}</td>
                    <td>
                      {group.members.length === 0
                        ? '—'
                        : group.members.map((m) => m.username).join(', ')}
                    </td>
                    <td className="row-actions">
                      <button
                        type="button"
                        disabled={removing}
                        onClick={() => {
                          setDraft({
                            id: group.id,
                            name: group.name,
                            description: group.description,
                            memberIds: group.members.map((m) => m.id),
                          })
                        }}
                      >
                        {t('common.edit')}
                      </button>
                      <ActionButton
                        type="button"
                        className="button-danger"
                        pending={removing}
                        onClick={() => {
                          void remove(group)
                        }}
                      >
                        {t('common.delete')}
                      </ActionButton>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
