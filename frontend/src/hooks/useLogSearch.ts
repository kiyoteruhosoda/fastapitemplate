/**
 * Fetching the log lists (system logs and audit logs).
 *
 * Refetches whenever the filters or page change. While fetching, `searching` is true so the
 * search button can show an in-progress indicator (ADR-0080 §5). Nothing is fetched when the
 * filters are unchanged, so a search that wouldn't change the results never leaves a spinner.
 */
import { useEffect, useState } from 'react'

import { api } from '../services/api'
import { buildLogQuery, type LogFilters, type LogSearchResult } from '../services/logSearch'

export function useLogSearch<E>(
  path: string,
  filters: LogFilters,
  page: number,
): { result: LogSearchResult<E>; searching: boolean } {
  const [result, setResult] = useState<LogSearchResult<E>>({ total: 0, entries: [] })
  const [searching, setSearching] = useState(true)

  useEffect(() => {
    // When filters change in quick succession, don't overwrite new results with a stale response.
    let current = true
    setSearching(true)
    void api
      .get<LogSearchResult<E>>(`${path}${buildLogQuery(filters, page)}`)
      .then((data) => {
        if (current) setResult(data)
      })
      .finally(() => {
        if (current) setSearching(false)
      })
    return () => {
      current = false
    }
  }, [path, filters, page])

  return { result, searching }
}
