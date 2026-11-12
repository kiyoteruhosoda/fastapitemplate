/**
 * Audit log page (search and browse the `audit_log` table).
 *
 * The record of "who did what". `result=failure` extracts only failed operations, and
 * `requestId` only one request. Entering the same `requestId` on the system log page
 * (`/admin/logs`) lets you match up what was happening behind it.
 *
 * Actors and targets are shown by internal ID, because the audit log does not store PII such
 * as email addresses (ADR-0075 §1). To trace a user from an ID, use the user management page.
 */
import { useCallback, useEffect, useState, type SubmitEvent } from 'react'

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

/** Which action triggered the search. Held so the running marker shows only on the pressed action. */
type SearchTrigger = 'search' | 'failuresOnly' | 'reset' | 'previous' | 'next'

export function AuditLogsPage() {
  const { t } = useI18n()
  // Keep the values being typed (form) separate from the searched values (applied)
  // (pagination keeps the conditions)
  const [form, setForm] = useState<LogFilters>(EMPTY_FILTERS)
  const [applied, setApplied] = useState<LogFilters>(EMPTY_FILTERS)
  const [page, setPage] = useState(0)
  const [options, setOptions] = useState<FilterOptions>(NO_OPTIONS)
  const [trigger, setTrigger] = useState<SearchTrigger | null>(null)
  const { result, searching } = useLogSearch<AuditLogEntry>('/api/admin/audit-logs', applied, page)
  // No marker while not fetching (nobody pressed anything for the initial load).
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

  const search = (e: SubmitEvent) => {
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

  /** "Failures only" is the most common filter, so make it one click. */
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

      {/* Pagination shows no change until the table content is replaced, so mark the pressed control. */}
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
