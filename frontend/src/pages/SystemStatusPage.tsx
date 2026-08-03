/**
 * システムステータス（要 `system:manage`）。
 *
 * バージョンなどのビルド情報と、API・DB の状態を表示する。
 * データは GET /api/admin/system/status から取得する。
 */
import { useCallback, useEffect, useState } from 'react'

import { ActionButton } from '../components/ActionButton'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'

interface SystemStatus {
  version: string
  git_sha: string
  branch: string
  build_time: string
  environment: string
  components: Record<string, string>
  uptime_seconds: number
  timestamp_utc: string
}

/** 稼働時間を「1d 2h 3m」の形へ。1 分未満は秒で示す。 */
function formatUptime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  if (minutes < 1) return `${Math.floor(totalSeconds)}s`
  const parts = [
    { value: Math.floor(minutes / (60 * 24)), unit: 'd' },
    { value: Math.floor(minutes / 60) % 24, unit: 'h' },
    { value: minutes % 60, unit: 'm' },
  ]
  return parts
    .filter((part, index) => part.value > 0 || index === parts.length - 1)
    .map((part) => `${part.value}${part.unit}`)
    .join(' ')
}

function ComponentState({ state }: { state: string }) {
  const { t } = useI18n()
  return (
    <span className={state === 'ok' ? 'result result-success' : 'result result-failure'}>
      {state === 'ok' ? t('status.ok') : t('status.ng')}
    </span>
  )
}

export function SystemStatusPage() {
  const { t } = useI18n()
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setStatus(await api.get<SystemStatus>('/api/admin/system/status'))
      setError(null)
    } catch (err) {
      setStatus(null)
      setError(errorMessageKey(err))
    }
  }, [])

  const [reload, reloading] = usePendingAction(load)

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="card">
      <h1>{t('status.title')}</h1>
      <p className="hint">{t('status.hint')}</p>
      {error && <p className="error">{t(error)}</p>}
      {status && (
        <>
          <section>
            <h2>{t('status.components')}</h2>
            <dl className="status-list">
              <dt>{t('status.api')}</dt>
              <dd>
                <ComponentState state={status.components['api'] ?? 'ng'} />
              </dd>
              <dt>{t('status.database')}</dt>
              <dd>
                <ComponentState state={status.components['database'] ?? 'ng'} />
              </dd>
              <dt>{t('status.uptime')}</dt>
              <dd>{formatUptime(status.uptime_seconds)}</dd>
            </dl>
          </section>
          <section>
            <h2>{t('status.build')}</h2>
            <dl className="status-list">
              <dt>{t('status.version')}</dt>
              <dd>{status.version}</dd>
              <dt>{t('status.gitSha')}</dt>
              <dd>
                <code>{status.git_sha}</code>
              </dd>
              <dt>{t('status.branch')}</dt>
              <dd>{status.branch}</dd>
              <dt>{t('status.buildTime')}</dt>
              <dd className="timestamp">{status.build_time}</dd>
              <dt>{t('status.environment')}</dt>
              <dd>{status.environment}</dd>
              <dt>{t('status.checkedAt')}</dt>
              <dd className="timestamp">{status.timestamp_utc}</dd>
            </dl>
          </section>
        </>
      )}
      <div>
        <ActionButton type="button" pending={reloading} onClick={reload}>
          {t('status.reload')}
        </ActionButton>
      </div>
    </div>
  )
}
