/**
 * Content settings (rules for the tenant's content. ADR-0084 §3, ADR-0085).
 *
 * Viewing needs `content-settings:view`, changing needs `content-settings:write`. For view-only
 * users (auditors) the inputs are disabled and no save button is shown. The server returns the
 * item definitions; the dictionary holds only the display text.
 * "Reset to default" clears the value so the definition's default applies.
 */
import { useEffect, useState } from 'react'

import { ActionButton } from '../components/ActionButton'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { useAuth } from '../store/AuthContext'

type SettingValue = string | boolean | number

interface ContentSetting {
  key: string
  value_type: 'choice' | 'boolean' | 'integer'
  value: SettingValue
  default: SettingValue
  stored: boolean
  choices: string[]
  minimum: number | null
  maximum: number | null
}

const ENDPOINT = '/api/admin/content-settings'

export function ContentSettingsPage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const { hasScope } = useAuth()
  const canWrite = hasScope('content-settings:write')
  const [items, setItems] = useState<ContentSetting[]>([])
  const [edits, setEdits] = useState<Record<string, SettingValue | null>>({})

  useEffect(() => {
    void api.get<ContentSetting[]>(ENDPOINT).then(setItems)
  }, [])

  const [save, saving] = usePendingAction(async () => {
    try {
      setItems(await api.put<ContentSetting[]>(ENDPOINT, { values: edits }))
      setEdits({})
      notify('success', t('common.saved'))
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  // If the dictionary has no translation, show the key as is (so the page does not break between
  // adding an item and adding its translation)
  const translateOr = (key: string, fallback: string) => {
    const translated = t(key)
    return translated === key ? fallback : translated
  }

  const current = (item: ContentSetting): SettingValue => {
    const edited = edits[item.key]
    if (edited === null) return item.default
    return edited ?? item.value
  }

  const change = (key: string, value: SettingValue | null) => {
    setEdits((prev) => ({ ...prev, [key]: value }))
  }

  const isDefault = (item: ContentSetting) =>
    edits[item.key] === null || (!(item.key in edits) && !item.stored)

  return (
    <div className="card">
      <h1>{t('contentSettings.title')}</h1>
      <p className="hint">{t('contentSettings.hint')}</p>
      <fieldset className="config-fields" disabled={!canWrite}>
        {items.map((item) => {
          const id = `content-setting-${item.key}`
          const value = current(item)
          return (
            <div key={item.key} className="config-row">
              <label htmlFor={id}>
                <span className="config-label">
                  {translateOr(`contentSettings.field.${item.key}`, item.key)}
                </span>
                <code className="config-key">{item.key}</code>
                {isDefault(item) && (
                  <em className="config-note">{t('contentSettings.isDefault')}</em>
                )}
              </label>
              {item.value_type === 'boolean' ? (
                <input
                  id={id}
                  type="checkbox"
                  checked={value === true}
                  onChange={(e) => {
                    change(item.key, e.target.checked)
                  }}
                />
              ) : item.value_type === 'choice' ? (
                <select
                  id={id}
                  value={String(value)}
                  onChange={(e) => {
                    change(item.key, e.target.value)
                  }}
                >
                  {item.choices.map((choice) => (
                    <option key={choice} value={choice}>
                      {translateOr(`contentSettings.choice.${item.key}.${choice}`, choice)}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={id}
                  type="number"
                  min={item.minimum ?? undefined}
                  max={item.maximum ?? undefined}
                  value={String(value)}
                  onChange={(e) => {
                    change(item.key, Number(e.target.value))
                  }}
                />
              )}
              {canWrite && !isDefault(item) && (
                <button
                  type="button"
                  onClick={() => {
                    change(item.key, null)
                  }}
                >
                  {t('contentSettings.reset')}
                </button>
              )}
            </div>
          )
        })}
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
        <p className="hint">{t('contentSettings.readOnly')}</p>
      )}
    </div>
  )
}
