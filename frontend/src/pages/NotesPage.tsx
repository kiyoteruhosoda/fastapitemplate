/**
 * 共有メモ（ADR-0070 の見本。要 `note:view`、書くには `note:write`）。
 *
 * 出し分けは 2 段。
 * - 「メモを書く」ボタンは **scope**（`note:write`）で出す。機能を使えるかはトークンが知っている。
 * - 行ごとの「編集」「削除」は、scope に加えて **サーバーが返す `can_change`** で出す。どのメモが
 *   自分のものかはトークンに載っていないので、scope だけでは決められない（両方そろって通る）。
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

interface Note {
  id: number
  title: string
  body: string
  shared_group_id: number | null
  mine: boolean
  can_change: boolean
}

interface ShareTarget {
  id: number
  name: string
}

/** 編集中の内容。`id` が無ければ新規。 */
interface Draft {
  id: number | null
  title: string
  body: string
  sharedGroupId: number | null
}

const EMPTY_DRAFT: Draft = { id: null, title: '', body: '', sharedGroupId: null }

export function NotesPage() {
  const { t } = useI18n()
  const { hasScope } = useAuth()
  const { notify } = useToast()
  const [notes, setNotes] = useState<Note[]>([])
  const [targets, setTargets] = useState<ShareTarget[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [reading, setReading] = useState<Note | null>(null)
  const { pendingActionOf, runForRow } = usePendingRows<'removal'>()
  const canWrite = hasScope('note:write')

  const reload = () => api.get<Note[]>('/api/notes').then(setNotes)

  useEffect(() => {
    void reload()
    if (!canWrite) return
    void api
      .get<ShareTarget[]>('/api/notes/share-targets')
      .then(setTargets)
      .catch(() => {
        setTargets([])
      })
  }, [canWrite])

  const [save, saving] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    if (draft === null) return
    const body = { title: draft.title, body: draft.body, shared_group_id: draft.sharedGroupId }
    try {
      if (draft.id === null) await api.post('/api/notes', body)
      else await api.put(`/api/notes/${String(draft.id)}`, body)
      setDraft(null)
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  const remove = (note: Note) =>
    runForRow(note.id, 'removal', async () => {
      try {
        await api.delete(`/api/notes/${String(note.id)}`)
        await reload()
      } catch (err) {
        notify('error', t(errorMessageKey(err)))
      }
    })

  const sharedWith = (note: Note) => {
    if (note.shared_group_id === null) return t('notes.private')
    return targets.find((g) => g.id === note.shared_group_id)?.name ?? t('notes.sharedGroup')
  }

  // 共有した後に自分が抜けたグループも、いまの共有先として選べるように残す
  const choices =
    draft?.sharedGroupId != null && !targets.some((g) => g.id === draft.sharedGroupId)
      ? [...targets, { id: draft.sharedGroupId, name: t('notes.sharedGroup') }]
      : targets

  return (
    <div className="card">
      <div className="card-head">
        <h1>{t('notes.title')}</h1>
        {canWrite && (
          <button
            type="button"
            className="button-primary"
            onClick={() => {
              setDraft(EMPTY_DRAFT)
            }}
          >
            {t('notes.add')}
          </button>
        )}
      </div>
      <p className="hint">{t('notes.hint')}</p>
      {draft && (
        <FormDialog
          title={t(draft.id === null ? 'notes.add' : 'notes.edit')}
          onClose={() => {
            setDraft(null)
          }}
        >
          <form className="dialog-form" onSubmit={save}>
            <label>
              {t('notes.noteTitle')}
              <input
                value={draft.title}
                maxLength={100}
                required
                onChange={(e) => {
                  setDraft({ ...draft, title: e.target.value })
                }}
              />
            </label>
            <label>
              {t('notes.body')}
              <textarea
                value={draft.body}
                maxLength={4000}
                rows={6}
                onChange={(e) => {
                  setDraft({ ...draft, body: e.target.value })
                }}
              />
            </label>
            <label>
              {t('notes.shareWith')}
              <select
                value={draft.sharedGroupId === null ? '' : String(draft.sharedGroupId)}
                onChange={(e) => {
                  setDraft({
                    ...draft,
                    sharedGroupId: e.target.value === '' ? null : Number(e.target.value),
                  })
                }}
              >
                <option value="">{t('notes.private')}</option>
                {choices.map((group) => (
                  <option key={group.id} value={String(group.id)}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
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
      {reading && (
        <FormDialog
          title={reading.title}
          onClose={() => {
            setReading(null)
          }}
        >
          <p className="note-body">{reading.body || '—'}</p>
          <div className="dialog-actions">
            <button
              type="button"
              onClick={() => {
                setReading(null)
              }}
            >
              {t('common.close')}
            </button>
          </div>
        </FormDialog>
      )}
      {notes.length === 0 ? (
        <p className="hint">{t('notes.empty')}</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('notes.noteTitle')}</th>
                <th>{t('notes.shareWith')}</th>
                <th>{t('notes.owner')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {notes.map((note) => {
                const removing = pendingActionOf(note.id) === 'removal'
                return (
                  <tr key={note.id}>
                    <th scope="row">{note.title}</th>
                    <td>{sharedWith(note)}</td>
                    <td>{t(note.mine ? 'notes.mine' : 'notes.sharedWithMe')}</td>
                    <td className="row-actions">
                      <button
                        type="button"
                        onClick={() => {
                          setReading(note)
                        }}
                      >
                        {t('notes.open')}
                      </button>
                      {canWrite && note.can_change && (
                        <>
                          <button
                            type="button"
                            disabled={removing}
                            onClick={() => {
                              setDraft({
                                id: note.id,
                                title: note.title,
                                body: note.body,
                                sharedGroupId: note.shared_group_id,
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
                              void remove(note)
                            }}
                          >
                            {t('common.delete')}
                          </ActionButton>
                        </>
                      )}
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
