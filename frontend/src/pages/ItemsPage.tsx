import { useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
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

  const reload = () => api.get<Item[]>('/api/items').then(setItems)

  useEffect(() => {
    void reload()
  }, [])

  const [submit, submitting] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.post('/api/items', { name })
      setName('')
      await reload()
    } catch {
      notify('error', t('error.unknown_error'))
    }
  })

  return (
    <div className="card">
      <h1>{t('items.title')}</h1>
      {hasScope('item:manage') && (
        <form className="inline-form" onSubmit={submit}>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value)
            }}
            placeholder={t('items.name')}
            required
          />
          <ActionButton type="submit" pending={submitting}>
            {t('items.add')}
          </ActionButton>
        </form>
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
