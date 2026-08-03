/**
 * システムログ画面（`log` テーブルの検索・閲覧）。
 *
 * 「システムが何をしたか」の運用ログ。「誰が何をしたか」は監査ログ画面
 * （`/admin/audit-logs`）で見る。行の `requestId` をそちらの絞り込みに入れれば、
 * 同じリクエストの記録を突き合わせられる。
 *
 * 絞り込みの選択肢（ログレベル）はバックエンドから取得する。列挙を画面へ写して
 * 二重管理しないため。
 */
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
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

interface LogEntry {
  id: number
  created_at: string
  level: string
  logger: string
  message: string
  request_id: string | null
  user_id_hash: string | null
  path: string | null
  method: string | null
  status_code: number | null
  duration_ms: number | null
  trace: string | null
}

interface FilterOptions {
  levels: string[]
}

/** どの操作が検索を起こしたか。押した操作にだけ実行中の目印を出すために持つ。 */
type SearchTrigger = 'search' | 'reset' | 'previous' | 'next'

const EMPTY_FILTERS: LogFilters = {
  level: '',
  logger: '',
  message: '',
  request_id: '',
  created_from: '',
  created_to: '',
}

export function SystemLogsPage() {
  const { t } = useI18n()
  // 入力中の値（form）と、実際に検索した値（applied）を分ける。入力の途中で
  // 検索が走らないようにし、ページ送りは検索済みの条件を保ったまま行う。
  const [form, setForm] = useState<LogFilters>(EMPTY_FILTERS)
  const [applied, setApplied] = useState<LogFilters>(EMPTY_FILTERS)
  const [page, setPage] = useState(0)
  const [levels, setLevels] = useState<string[]>([])
  const [expanded, setExpanded] = useState<number | null>(null)
  const [trigger, setTrigger] = useState<SearchTrigger | null>(null)
  const { result, searching } = useLogSearch<LogEntry>('/api/admin/logs', applied, page)
  // 取得していないあいだは目印を出さない（初回の読み込みは誰も押していない）。
  const pendingTrigger = searching ? trigger : null

  useEffect(() => {
    void api
      .get<FilterOptions>('/api/admin/logs/filters')
      .then((options) => {
        setLevels(options.levels)
      })
      .catch(() => {
        setLevels([])
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

  const goToPage = (next: number, from: SearchTrigger) => {
    setTrigger(from)
    setPage(next)
  }

  const range = pageRange(result.total, page, result.entries.length)

  return (
    <div className="card">
      <h1>{t('logs.title')}</h1>
      <p className="hint">{t('logs.hint')}</p>

      <form className="filter-form" onSubmit={search}>
        <label>
          {t('logs.level')}
          <select
            value={form.level}
            onChange={(e) => {
              update('level', e.target.value)
            }}
          >
            <option value="">{t('logs.allLevels')}</option>
            {levels.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('logs.logger')}
          <input
            value={form.logger}
            onChange={(e) => {
              update('logger', e.target.value)
            }}
            placeholder="app.request"
          />
        </label>
        <label>
          {t('logs.message')}
          <input
            value={form.message}
            onChange={(e) => {
              update('message', e.target.value)
            }}
          />
        </label>
        <label>
          {t('logs.requestId')}
          <input
            value={form.request_id}
            onChange={(e) => {
              update('request_id', e.target.value)
            }}
          />
        </label>
        <label>
          {t('logs.from')}
          <input
            type="datetime-local"
            value={form.created_from}
            onChange={(e) => {
              update('created_from', e.target.value)
            }}
          />
        </label>
        <label>
          {t('logs.to')}
          <input
            type="datetime-local"
            value={form.created_to}
            onChange={(e) => {
              update('created_to', e.target.value)
            }}
          />
        </label>
        <div className="filter-actions">
          <ActionButton type="submit" pending={pendingTrigger === 'search'} disabled={searching}>
            {t('logs.search')}
          </ActionButton>
          <ActionButton
            type="button"
            pending={pendingTrigger === 'reset'}
            disabled={searching}
            onClick={reset}
          >
            {t('logs.reset')}
          </ActionButton>
        </div>
      </form>

      <p className="result-count">
        {t('logs.resultCount', { first: range.first, last: range.last, total: result.total })}
      </p>

      {result.entries.length === 0 ? (
        <p className="hint">{t('logs.empty')}</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('logs.time')}</th>
                <th>{t('logs.level')}</th>
                <th>{t('logs.logger')}</th>
                <th>{t('logs.message')}</th>
                <th>{t('logs.requestId')}</th>
                <th>{t('logs.path')}</th>
                <th>{t('logs.status')}</th>
                <th>{t('logs.duration')}</th>
              </tr>
            </thead>
            <tbody>
              {result.entries.map((log) => (
                <tr key={log.id}>
                  <td className="timestamp">{formatUtcTimestamp(log.created_at)}</td>
                  <td>
                    <span className={`level level-${log.level.toLowerCase()}`}>{log.level}</span>
                  </td>
                  <td>{log.logger}</td>
                  <td>
                    {log.message}
                    {log.trace !== null && (
                      <>
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => {
                            setExpanded(expanded === log.id ? null : log.id)
                          }}
                        >
                          {expanded === log.id ? t('logs.hideTrace') : t('logs.showTrace')}
                        </button>
                        {expanded === log.id && <pre className="trace">{log.trace}</pre>}
                      </>
                    )}
                  </td>
                  <td>
                    <code>{orEmpty(log.request_id)}</code>
                  </td>
                  <td>{log.path === null ? orEmpty(null) : `${log.method ?? ''} ${log.path}`}</td>
                  <td>{orEmpty(log.status_code)}</td>
                  <td>{log.duration_ms === null ? orEmpty(null) : `${log.duration_ms} ms`}</td>
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
          {t('logs.previous')}
        </ActionButton>
        <ActionButton
          type="button"
          pending={pendingTrigger === 'next'}
          disabled={!hasNextPage(result.total, page) || searching}
          onClick={() => {
            goToPage(page + 1, 'next')
          }}
        >
          {t('logs.next')}
        </ActionButton>
      </div>
    </div>
  )
}
