/** システム設定画面（環境変数 > DB > デフォルトの解決結果を編集する）。 */
import { useEffect, useState } from 'react'

import { useToast } from '../components/ToastNotification'
import { useI18n } from '../i18n'
import { api } from '../services/api'
import { useAuth } from '../store/AuthContext'

interface SettingItem {
  key: string
  category: string
  label: string
  value_type: 'string' | 'integer' | 'boolean' | 'list'
  secret?: boolean
  choices?: [value: string, label: string][]
  /** 空でなければ、反映にそのサービスの再起動が必要。 */
  restart_scopes: string[]
  value: unknown
  default: unknown
  env_locked: boolean
  stored: boolean
}

interface RestartRequirement {
  scopes: string[]
  keys: string[]
}

interface SaveResult {
  status: string
  restart_required: RestartRequirement | null
}

export function ConfigPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const { hasScope } = useAuth()
  const [items, setItems] = useState<SettingItem[]>([])
  const [edits, setEdits] = useState<Record<string, unknown>>({})
  const [pendingRestart, setPendingRestart] = useState<RestartRequirement | null>(null)

  const reload = () =>
    api.get<SettingItem[]>('/api/admin/config').then((data) => {
      setItems(data)
      setEdits({})
    })

  useEffect(() => {
    void reload()
  }, [])

  const save = async () => {
    const result = await api.put<SaveResult>('/api/admin/config', { values: edits })
    await reload()
    notify('success', t('common.saved'))
    setPendingRestart(result.restart_required)
  }

  const requestRestart = async () => {
    await api.post('/api/admin/system/restart', {
      scopes: pendingRestart?.scopes ?? null,
      reason: 'system settings changed',
    })
    setPendingRestart(null)
    notify('success', t('config.restartRequested'))
  }

  const setValue = (key: string, value: unknown) => {
    setEdits((prev) => ({ ...prev, [key]: value }))
  }

  const currentValue = (item: SettingItem) => (item.key in edits ? edits[item.key] : item.value)

  // 辞書に訳があればそれを使い、無ければサーバーが返した英語をそのまま出す。
  // 設定キーを追加したときに、訳を足すまでのあいだ画面が壊れないようにする。
  const translateOr = (key: string, fallback: string) => {
    const translated = t(key)
    return translated === key ? fallback : translated
  }

  const labelFor = (item: SettingItem) => translateOr(`config.field.${item.key}`, item.label)

  const choiceLabelFor = (item: SettingItem, value: string, label: string) =>
    translateOr(`config.choice.${item.key}.${value}`, label)

  /** 任意の設定値を表示用の文字列にする（`[object Object]` を出さない）。 */
  const asText = (value: unknown): string => {
    if (value === null || value === undefined) return ''
    if (typeof value === 'string') return value
    if (typeof value === 'number' || typeof value === 'boolean') return String(value)
    if (Array.isArray(value)) return value.join(', ')
    return JSON.stringify(value)
  }

  const parseValue = (item: SettingItem, raw: string): unknown => {
    if (item.value_type === 'integer') return Number(raw)
    if (item.value_type === 'list') {
      return raw
        .split(',')
        .map((entry) => entry.trim())
        .filter(Boolean)
    }
    return raw
  }

  const categories = [...new Set(items.map((i) => i.category))]

  return (
    <div className="card">
      <h1>{t('config.title')}</h1>

      {pendingRestart && (
        <div className="notice">
          <p>{t('config.restartRequired', { keys: pendingRestart.keys.join(', ') })}</p>
          {hasScope('system:manage') ? (
            <button
              type="button"
              onClick={() => {
                void requestRestart()
              }}
            >
              {t('config.restartNow')}
            </button>
          ) : (
            <p>{t('config.restartNeedsPermission')}</p>
          )}
        </div>
      )}

      {categories.map((category) => (
        <section key={category}>
          <h2>{t(`config.category.${category}`)}</h2>
          {items
            .filter((item) => item.category === category)
            .map((item) => (
              <label key={item.key} className="config-row">
                <span>
                  {labelFor(item)} <code>{item.key}</code>
                  {item.env_locked && <em> ({t('config.envLocked')})</em>}
                  {item.restart_scopes.length > 0 && <em> ({t('config.needsRestart')})</em>}
                </span>
                {item.value_type === 'boolean' ? (
                  <input
                    type="checkbox"
                    disabled={item.env_locked}
                    checked={Boolean(currentValue(item))}
                    onChange={(e) => {
                      setValue(item.key, e.target.checked)
                    }}
                  />
                ) : item.choices ? (
                  <select
                    disabled={item.env_locked}
                    value={asText(currentValue(item))}
                    onChange={(e) => {
                      setValue(item.key, e.target.value)
                    }}
                  >
                    {item.choices.map(([value, label]) => (
                      <option key={value} value={value}>
                        {choiceLabelFor(item, value, label)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={
                      item.secret ? 'password' : item.value_type === 'integer' ? 'number' : 'text'
                    }
                    disabled={item.env_locked}
                    value={asText(currentValue(item))}
                    onChange={(e) => {
                      setValue(item.key, parseValue(item, e.target.value))
                    }}
                  />
                )}
              </label>
            ))}
        </section>
      ))}
      <button
        onClick={() => {
          void save()
        }}
        disabled={Object.keys(edits).length === 0}
      >
        {t('config.save')}
      </button>
    </div>
  )
}
