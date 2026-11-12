/**
 * Shared logic for log search screens (used by both the system log and audit log screens).
 *
 * Gathers filter query building, pagination math, and row display formatting.
 * Both screens must behave the same here; writing it per screen lets one drift.
 */

/** Rows per page. A practical value below the backend limit (500). */
export const PAGE_SIZE = 50

/** Search form values. Keys become query names as is. */
export type LogFilters = Record<string, string>

/** Search result (``total`` is the total number of matches, not the count on the page). */
export interface LogSearchResult<TEntry> {
  total: number
  entries: TEntry[]
}

/**
 * Build `?a=1&b=2`. Empty or whitespace-only fields are dropped.
 *
 * `page` is 0-based. `offset` is computed here, so the screen only holds the page number.
 */
export function buildLogQuery(filters: LogFilters, page = 0, pageSize = PAGE_SIZE): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    const trimmed = value.trim()
    if (trimmed) params.set(key, trimmed)
  }
  params.set('limit', String(pageSize))
  if (page > 0) params.set('offset', String(page * pageSize))
  return `?${params.toString()}`
}

/** Whether the shown page has a next page (computed from the total). */
export function hasNextPage(total: number, page: number, pageSize = PAGE_SIZE): boolean {
  return (page + 1) * pageSize < total
}

/** The range part of "51〜100 / 328 件". Returns 0〜0 when there are no rows. */
export function pageRange(
  total: number,
  page: number,
  shown: number,
  pageSize = PAGE_SIZE,
): { first: number; last: number } {
  if (total === 0 || shown === 0) return { first: 0, last: 0 }
  const first = page * pageSize + 1
  return { first, last: first + shown - 1 }
}

/**
 * Format the API's UTC ISO 8601 (`2026-07-30T13:10:33.602668`) for the list.
 *
 * Replace `T` with a space and truncate to seconds. With `T`, narrow table columns wrap mid-date
 * (`2026-07-` / `30T13:…`), and microseconds aren't a value anyone reads in a list.
 * Not converted to local time (the screen stays in UTC).
 */
export function formatUtcTimestamp(value: string): string {
  return value.replace('T', ' ').replace(/\.\d+/, '')
}

/** Display for empty cells. A blank looks like "the columns shifted", so fill with a symbol. */
export const EMPTY_CELL = '—'

/** Replace `null` with [`EMPTY_CELL`]. */
export function orEmpty(value: string | number | null): string {
  return value === null ? EMPTY_CELL : String(value)
}
