/** システム設定画面（環境変数 > DB > デフォルトの解決結果を編集する）。 */
import { useEffect, useState } from 'react'

import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { api } from '../services/api'

interface SettingItem {
  key: string
  category: string
  label: string
  value_type: 'string' | 'integer' | 'boolean' | 'list'
  secret?: boolean
  value: unknown
  default: unknown
  env_locked: boolean
  stored: boolean
}

export function ConfigPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [items, setItems] = useState<SettingItem[]>([])
  const [edits, setEdits] = useState<Record<string, unknown>>({})

  const reload = () =>
    api.get<SettingItem[]>('/api/admin/config').then((data) => {
      setItems(data)
      setEdits({})
    })

  useEffect(() => {
    void reload()
  }, [])

  const save = async () => {
    await api.put('/api/admin/config', { values: edits })
    await reload()
    notify('success', t('common.saved'))
  }

  const setValue = (key: string, value: unknown) =>
    setEdits((prev) => ({ ...prev, [key]: value }))

  const currentValue = (item: SettingItem) =>
    item.key in edits ? edits[item.key] : item.value

  const categories = [...new Set(items.map((i) => i.category))]

  return (
    <div className="card">
      <h1>{t('config.title')}</h1>
      {categories.map((category) => (
        <section key={category}>
          <h2>{category}</h2>
          {items
            .filter((item) => item.category === category)
            .map((item) => (
              <label key={item.key} className="config-row">
                <span>
                  {item.label} <code>{item.key}</code>
                  {item.env_locked && <em> ({t('config.envLocked')})</em>}
                </span>
                {item.value_type === 'boolean' ? (
                  <input
                    type="checkbox"
                    disabled={item.env_locked}
                    checked={Boolean(currentValue(item))}
                    onChange={(e) => setValue(item.key, e.target.checked)}
                  />
                ) : (
                  <input
                    type={
                      item.secret
                        ? 'password'
                        : item.value_type === 'integer'
                          ? 'number'
                          : 'text'
                    }
                    disabled={item.env_locked}
                    value={String(currentValue(item) ?? '')}
                    onChange={(e) =>
                      setValue(
                        item.key,
                        item.value_type === 'integer'
                          ? Number(e.target.value)
                          : e.target.value,
                      )
                    }
                  />
                )}
              </label>
            ))}
        </section>
      ))}
      <button onClick={save} disabled={Object.keys(edits).length === 0}>
        {t('config.save')}
      </button>
    </div>
  )
}
