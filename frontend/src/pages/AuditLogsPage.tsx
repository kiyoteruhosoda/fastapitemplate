/**
 * 監査ログ画面（`audit_log` テーブルの検索・閲覧）。
 *
 * 「誰が何をしたか」の記録。`result=failure` で失敗した操作だけを、`requestId` で
 * 1 リクエスト分だけを取り出せる。同じ `requestId` をシステムログ画面
 * （`/admin/logs`）に入れれば、その裏で何が起きていたかを突き合わせられる。
 *
 * 実行者・対象は内部 ID で表示する。監査ログにメールアドレス等の PII を保存しない
 * ため（ADR-0013）。ID から利用者を辿るときはユーザー管理画面を見る。
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { FilterPanel } from '../components/FilterPanel'
import { useLogSearch } from '../hooks/useLogSearch'
import { useI18n } from '../i18n'
import { api } from '../services/api'
import {
  formatUtcTimestamp,
  hasNextPage,
  orEmpty,
  pageRange,
  type LogFilters,
} from '../services/logSearch'

interface AuditLogEntry {
  id: number
  occurred_at: string
  event_type: string
  result: string
  actor_user_id: number | null
  target_type: string | null
  target_id: string | null
  ip_address: string | null
  user_agent: string | null
  reason: string | null
  request_id: string | null
}

interface FilterOptions {
  event_types: string[]
  results: string[]
  target_types: string[]
}

const EMPTY_FILTERS: LogFilters = {
  event_type: '',
  result: '',
  actor_user_id: '',
  target_type: '',
  target_id: '',
  request_id: '',
  occurred_from: '',
  occurred_to: '',
}

const NO_OPTIONS: FilterOptions = { event_types: [], results: [], target_types: [] }

/** どの操作が検索を起こしたか。押した操作にだけ実行中の目印を出すために持つ。 */
type SearchTrigger = 'search' | 'failuresOnly' | 'reset' | 'previous' | 'next'

export function AuditLogsPage() {
  const { t } = useI18n()
  // 入力中の値（form）と検索済みの値（applied）を分ける（ページ送りで条件を保つ）
  const [form, setForm] = useState<LogFilters>(EMPTY_FILTERS)
  const [applied, setApplied] = useState<LogFilters>(EMPTY_FILTERS)
  const [page, setPage] = useState(0)
  const [options, setOptions] = useState<FilterOptions>(NO_OPTIONS)
  const [trigger, setTrigger] = useState<SearchTrigger | null>(null)
  const { result, searching } = useLogSearch<AuditLogEntry>('/api/admin/audit-logs', applied, page)
  // 取得していないあいだは目印を出さない（初回の読み込みは誰も押していない）。
  const pendingTrigger = searching ? trigger : null

  useEffect(() => {
    void api
      .get<FilterOptions>('/api/admin/audit-logs/filters')
      .then(setOptions)
      .catch(() => {
        setOptions(NO_OPTIONS)
      })
  }, [])

  const update = useCallback((key: string, value: string) => {
    setForm((current) => ({ ...current, [key]: value }))
  }, [])

  const search = (e: FormEvent) => {
    e.preventDefault()
    setTrigger('search')
    setPage(0)
    setApplied(form)
  }

  const reset = () => {
    setTrigger('reset')
    setPage(0)
    setForm(EMPTY_FILTERS)
    setApplied(EMPTY_FILTERS)
  }

  /** 「失敗だけ」は最頻の絞り込みなので 1 クリックで出せるようにする。 */
  const showFailuresOnly = () => {
    const failuresOnly = { ...EMPTY_FILTERS, result: 'failure' }
    setTrigger('failuresOnly')
    setPage(0)
    setForm(failuresOnly)
    setApplied(failuresOnly)
  }

  const goToPage = (next: number, from: SearchTrigger) => {
    setTrigger(from)
    setPage(next)
  }

  const range = pageRange(result.total, page, result.entries.length)

  return (
    <div className="card">
      <h1>{t('audit.title')}</h1>
      <p className="hint">{t('audit.hint')}</p>

      <FilterPanel>
        <form className="filter-form" onSubmit={search}>
          <label>
            {t('audit.eventType')}
            <select
              value={form.event_type}
              onChange={(e) => {
                update('event_type', e.target.value)
              }}
            >
              <option value="">{t('audit.allEventTypes')}</option>
              {options.event_types.map((eventType) => (
                <option key={eventType} value={eventType}>
                  {eventType}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('audit.result')}
            <select
              value={form.result}
              onChange={(e) => {
                update('result', e.target.value)
              }}
            >
              <option value="">{t('audit.allResults')}</option>
              {options.results.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('audit.actor')}
            <input
              type="number"
              min={1}
              value={form.actor_user_id}
              onChange={(e) => {
                update('actor_user_id', e.target.value)
              }}
            />
          </label>
          <label>
            {t('audit.targetType')}
            <select
              value={form.target_type}
              onChange={(e) => {
                update('target_type', e.target.value)
              }}
            >
              <option value="">{t('audit.allTargetTypes')}</option>
              {options.target_types.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('audit.targetId')}
            <input
              value={form.target_id}
              onChange={(e) => {
                update('target_id', e.target.value)
              }}
            />
          </label>
          <label>
            {t('audit.requestId')}
            <input
              value={form.request_id}
              onChange={(e) => {
                update('request_id', e.target.value)
              }}
            />
          </label>
          <label>
            {t('audit.from')}
            <input
              type="datetime-local"
              value={form.occurred_from}
              onChange={(e) => {
                update('occurred_from', e.target.value)
              }}
            />
          </label>
          <label>
            {t('audit.to')}
            <input
              type="datetime-local"
              value={form.occurred_to}
              onChange={(e) => {
                update('occurred_to', e.target.value)
              }}
            />
          </label>
          <div className="filter-actions">
            <ActionButton type="submit" pending={pendingTrigger === 'search'} disabled={searching}>
              {t('audit.search')}
            </ActionButton>
            <ActionButton
              type="button"
              pending={pendingTrigger === 'failuresOnly'}
              disabled={searching}
              onClick={showFailuresOnly}
            >
              {t('audit.failuresOnly')}
            </ActionButton>
            <ActionButton
              type="button"
              pending={pendingTrigger === 'reset'}
              disabled={searching}
              onClick={reset}
            >
              {t('audit.reset')}
            </ActionButton>
          </div>
        </form>
      </FilterPanel>

      <p className="result-count">
        {t('audit.resultCount', { first: range.first, last: range.last, total: result.total })}
      </p>

      {result.entries.length === 0 ? (
        <p className="hint">{t('audit.empty')}</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('audit.time')}</th>
                <th>{t('audit.eventType')}</th>
                <th>{t('audit.result')}</th>
                <th>{t('audit.actor')}</th>
                <th>{t('audit.target')}</th>
                <th>{t('audit.reason')}</th>
                <th>{t('audit.ipAddress')}</th>
                <th>{t('audit.requestId')}</th>
              </tr>
            </thead>
            <tbody>
              {result.entries.map((entry) => (
                <tr key={entry.id}>
                  <td className="timestamp">{formatUtcTimestamp(entry.occurred_at)}</td>
                  <td>
                    <code>{entry.event_type}</code>
                  </td>
                  <td>
                    <span className={`result result-${entry.result}`}>{entry.result}</span>
                  </td>
                  <td>{orEmpty(entry.actor_user_id)}</td>
                  <td>
                    {entry.target_type === null
                      ? orEmpty(null)
                      : `${entry.target_type}${entry.target_id === null ? '' : `:${entry.target_id}`}`}
                  </td>
                  <td>{orEmpty(entry.reason)}</td>
                  <td>{orEmpty(entry.ip_address)}</td>
                  <td>
                    <code>{orEmpty(entry.request_id)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ページ送りは押しても表の中身が入れ替わるまで変化がないので、押した側に目印を出す。 */}
      <div className="pager">
        <ActionButton
          type="button"
          pending={pendingTrigger === 'previous'}
          disabled={page === 0 || searching}
          onClick={() => {
            goToPage(page - 1, 'previous')
          }}
        >
          {t('audit.previous')}
        </ActionButton>
        <ActionButton
          type="button"
          pending={pendingTrigger === 'next'}
          disabled={!hasNextPage(result.total, page) || searching}
          onClick={() => {
            goToPage(page + 1, 'next')
          }}
        >
          {t('audit.next')}
        </ActionButton>
      </div>
    </div>
  )
}
