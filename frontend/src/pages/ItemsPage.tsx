import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api } from '../services/api'
import { buildLogQuery, hasNextPage, pageRange } from '../services/logSearch'
import { useAuth } from '../store/AuthContext'

interface Item {
  id: number
  name: string
}

/** 一覧 API の規約の形（ADR-0095）。`total` はページの件数ではなく全体の件数。 */
interface ItemPage {
  entries: Item[]
  total: number
}

const PAGE_SIZE = 20

export function ItemsPage() {
  const { t } = useI18n()
  const { hasScope } = useAuth()
  const { notify } = useToast()
  const [items, setItems] = useState<ItemPage>({ entries: [], total: 0 })
  const [page, setPage] = useState(0)
  const [name, setName] = useState('')
  const [adding, setAdding] = useState(false)

  const reload = useCallback(
    () => api.get<ItemPage>(`/api/items${buildLogQuery({}, page, PAGE_SIZE)}`).then(setItems),
    [page],
  )

  useEffect(() => {
    void reload()
  }, [reload])

  const range = pageRange(items.total, page, items.entries.length, PAGE_SIZE)

  const [submit, submitting] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.post('/api/items', { name })
      setName('')
      setAdding(false)
      await reload()
    } catch {
      notify('error', t('error.unknown_error'))
    }
  })

  return (
    <div className="card">
      <div className="card-head">
        <h1>{t('items.title')}</h1>
        {hasScope('item:write') && (
          <button
            type="button"
            className="button-primary"
            onClick={() => {
              setAdding(true)
            }}
          >
            {t('items.add')}
          </button>
        )}
      </div>
      {adding && (
        <FormDialog
          title={t('items.add')}
          onClose={() => {
            setAdding(false)
          }}
        >
          <form className="dialog-form" onSubmit={submit}>
            <label>
              {t('items.name')}
              <input
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                }}
                required
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
              <ActionButton type="submit" pending={submitting}>
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
              <th>ID</th>
              <th>{t('items.name')}</th>
            </tr>
          </thead>
          <tbody>
            {items.entries.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.name}</td>
              </tr>
            ))}
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
