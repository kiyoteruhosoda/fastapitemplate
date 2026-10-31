/**
 * アイテム（`bounded_contexts/example`）の画面側の見本。一覧のページ送り（ADR-0095）・追加・編集・削除。
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { usePendingRows } from '../hooks/usePendingRows'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { buildLogQuery, formatUtcTimestamp, hasNextPage, pageRange } from '../services/logSearch'
import { useAuth } from '../store/AuthContext'

interface Item {
  id: number
  name: string
  created_at: string
  updated_at: string
}

/** 一覧 API の規約の形（ADR-0095）。`total` はページの件数ではなく全体の件数。 */
interface ItemPage {
  entries: Item[]
  total: number
}

/** 入力中の 1 件。`id` が `null` なら追加。 */
interface Draft {
  id: number | null
  name: string
}

const PAGE_SIZE = 20

export function ItemsPage() {
  const { t } = useI18n()
  const { hasScope } = useAuth()
  const { notify } = useToast()
  const [items, setItems] = useState<ItemPage>({ entries: [], total: 0 })
  const [page, setPage] = useState(0)
  const [draft, setDraft] = useState<Draft | null>(null)
  const { pendingActionOf, runForRow } = usePendingRows<'removal'>()

  const canWrite = hasScope('item:write')

  const reload = useCallback(
    () => api.get<ItemPage>(`/api/items${buildLogQuery({}, page, PAGE_SIZE)}`).then(setItems),
    [page],
  )

  useEffect(() => {
    void reload()
  }, [reload])

  const [submit, submitting] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    if (!draft) return
    try {
      if (draft.id === null) {
        await api.post('/api/items', { name: draft.name })
      } else {
        await api.put(`/api/items/${String(draft.id)}`, { name: draft.name })
      }
      setDraft(null)
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  const remove = (item: Item) =>
    runForRow(item.id, 'removal', async () => {
      try {
        await api.delete(`/api/items/${String(item.id)}`)
        // ページの最後の 1 件を消したら、空のページに残らず 1 つ戻る
        if (items.entries.length === 1 && page > 0) setPage(page - 1)
        else await reload()
      } catch (err) {
        notify('error', t(errorMessageKey(err)))
      }
    })

  const range = pageRange(items.total, page, items.entries.length, PAGE_SIZE)

  return (
    <div className="card">
      <div className="card-head">
        <h1>{t('items.title')}</h1>
        {canWrite && (
          <button
            type="button"
            className="button-primary"
            onClick={() => {
              setDraft({ id: null, name: '' })
            }}
          >
            {t('items.add')}
          </button>
        )}
      </div>
      {draft && (
        <FormDialog
          title={draft.id === null ? t('items.add') : t('items.edit')}
          onClose={() => {
            setDraft(null)
          }}
        >
          <form className="dialog-form" onSubmit={submit}>
            <label>
              {t('items.name')}
              <input
                value={draft.name}
                maxLength={255}
                onChange={(e) => {
                  setDraft({ ...draft, name: e.target.value })
                }}
                required
              />
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
              <ActionButton type="submit" pending={submitting}>
                {draft.id === null ? t('common.add') : t('common.save')}
              </ActionButton>
            </div>
          </form>
        </FormDialog>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{t('items.name')}</th>
              <th>{t('items.updatedAt')}</th>
              {canWrite && <th />}
            </tr>
          </thead>
          <tbody>
            {items.entries.map((item) => {
              const removing = pendingActionOf(item.id) === 'removal'
              return (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.name}</td>
                  <td className="timestamp">{formatUtcTimestamp(item.updated_at)}</td>
                  {canWrite && (
                    <td>
                      <button
                        type="button"
                        disabled={removing}
                        onClick={() => {
                          setDraft({ id: item.id, name: item.name })
                        }}
                      >
                        {t('common.edit')}
                      </button>
                      <ActionButton
                        type="button"
                        className="button-danger"
                        pending={removing}
                        onClick={() => {
                          void remove(item)
                        }}
                      >
                        {t('common.delete')}
                      </ActionButton>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button
          type="button"
          disabled={page === 0}
          onClick={() => {
            setPage(page - 1)
          }}
        >
          {t('audit.previous')}
        </button>
        <span>
          {t('items.range', { first: range.first, last: range.last, total: items.total })}
        </span>
        <button
          type="button"
          disabled={!hasNextPage(items.total, page, PAGE_SIZE)}
          onClick={() => {
            setPage(page + 1)
          }}
        >
          {t('audit.next')}
        </button>
      </div>
    </div>
  )
}
