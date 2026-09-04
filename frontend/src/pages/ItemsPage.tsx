import { useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FormDialog } from '../components/FormDialog'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api } from '../services/api'
import { useAuth } from '../store/AuthContext'

interface Item {
  id: number
  name: string
}

export function ItemsPage() {
  const { t } = useI18n()
  const { hasScope } = useAuth()
  const { notify } = useToast()
  const [items, setItems] = useState<Item[]>([])
  const [name, setName] = useState('')
  const [adding, setAdding] = useState(false)

  const reload = () => api.get<Item[]>('/api/items').then(setItems)

  useEffect(() => {
    void reload()
  }, [])

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
        {hasScope('item:manage') && (
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
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
