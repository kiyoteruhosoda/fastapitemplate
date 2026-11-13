/** System settings page (edits the resolved value of environment variable > DB > default). */
import { useEffect, useState } from 'react'

import { ActionButton } from '../components/ActionButton'
import { PasswordInput } from '../components/PasswordInput'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { useAuth } from '../store/AuthContext'

interface SettingItem {
  key: string
  category: string
  label: string
  value_type: 'string' | 'integer' | 'boolean' | 'list'
  secret?: boolean
  choices?: [value: string, label: string][]
  /** If not empty, that service must be restarted for it to take effect. */
  restart_scopes: string[]
  /** A setting decided only by environment variables. View only (ADR-0090). */
  env_only?: boolean
  value: unknown
  default: unknown
  env_fallback: boolean
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
  // For view-only users (only system-settings:view), disable inputs and hide the save button
  // (ADR-0084 §3)
  const canWrite = hasScope('system-settings:write')
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

  const [save, saving] = usePendingAction(async () => {
    try {
      const result = await api.put<SaveResult>('/api/admin/config', { values: edits })
      await reload()
      notify('success', t('common.saved'))
      setPendingRestart(result.restart_required)
    } catch (error) {
      // Keep rejected values in edit (so they can be fixed and submitted again)
      notify('error', t(errorMessageKey(error)))
    }
  })

  const [requestRestart, restarting] = usePendingAction(async () => {
    await api.post('/api/admin/system/restart', {
      scopes: pendingRestart?.scopes ?? null,
      reason: 'system settings changed',
    })
    setPendingRestart(null)
    notify('success', t('config.restartRequested'))
  })

  const setValue = (key: string, value: unknown) => {
    setEdits((prev) => ({ ...prev, [key]: value }))
  }

  const currentValue = (item: SettingItem) => (item.key in edits ? edits[item.key] : item.value)

  // Use the dictionary translation if there is one; otherwise show the English returned by the server.
  // Keeps the page from breaking between adding a setting key and adding its translation.
  const translateOr = (key: string, fallback: string) => {
    const translated = t(key)
    return translated === key ? fallback : translated
  }

  const labelFor = (item: SettingItem) => translateOr(`config.field.${item.key}`, item.label)

  const choiceLabelFor = (item: SettingItem, value: string, label: string) =>
    translateOr(`config.choice.${item.key}.${value}`, label)

  /** Turns any setting value into a display string (never shows `[object Object]`). */
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
            <ActionButton type="button" pending={restarting} onClick={requestRestart}>
              {t('config.restartNow')}
            </ActionButton>
          ) : (
            <p>{t('config.restartNeedsPermission')}</p>
          )}
        </div>
      )}

      <fieldset className="config-fields" disabled={!canWrite}>
        {categories.map((category) => (
          <section key={category}>
            <h2>{t(`config.category.${category}`)}</h2>
            {items
              .filter((item) => item.category === category)
              .map((item) => (
                <div key={item.key} className="config-row">
                  {/* The heading and input are tied with `for` / `id`. A password field has a
                   * visibility toggle in addition to the input, and wrapping it in `<label>` would
                   * put two labelable elements inside and make the association ambiguous (HTML
                   * label content model). */}
                  {/* Setting name, env var name and note are separate elements. On one line,
                   * "Name KEY (applies after restart)" reads as a single sentence. */}
                  <label htmlFor={`config-${item.key}`}>
                    <span className="config-label">{labelFor(item)}</span>
                    <code className="config-key">{item.key}</code>
                    {item.env_only && <em className="config-note">{t('config.envOnly')}</em>}
                    {item.env_fallback && !item.env_only && (
                      <em className="config-note">{t('config.envFallback')}</em>
                    )}
                    {item.restart_scopes.length > 0 && (
                      <em className="config-note">{t('config.needsRestart')}</em>
                    )}
                  </label>
                  {item.value_type === 'boolean' ? (
                    <input
                      id={`config-${item.key}`}
                      type="checkbox"
                      checked={Boolean(currentValue(item))}
                      onChange={(e) => {
                        setValue(item.key, e.target.checked)
                      }}
                    />
                  ) : item.choices ? (
                    <select
                      id={`config-${item.key}`}
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
                  ) : item.secret ? (
                    <PasswordInput
                      id={`config-${item.key}`}
                      value={asText(currentValue(item))}
                      onChange={(e) => {
                        setValue(item.key, parseValue(item, e.target.value))
                      }}
                    />
                  ) : (
                    <input
                      id={`config-${item.key}`}
                      type={item.value_type === 'integer' ? 'number' : 'text'}
                      disabled={item.env_only}
                      value={asText(currentValue(item))}
                      onChange={(e) => {
                        setValue(item.key, parseValue(item, e.target.value))
                      }}
                    />
                  )}
                </div>
              ))}
          </section>
        ))}
      </fieldset>
      {canWrite ? (
        <ActionButton
          type="button"
          className="button-primary"
          pending={saving}
          onClick={save}
          disabled={Object.keys(edits).length === 0}
        >
          {t('config.save')}
        </ActionButton>
      ) : (
        <p className="hint">{t('config.readOnly')}</p>
      )}
    </div>
  )
}
