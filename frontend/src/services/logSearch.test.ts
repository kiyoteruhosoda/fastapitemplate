/** Log search query building, pagination math, and row display formatting. */
import { describe, expect, it } from 'vitest'

import { buildLogQuery, formatUtcTimestamp, hasNextPage, orEmpty, pageRange } from './logSearch'

describe('buildLogQuery', () => {
  it('omits empty fields from the query', () => {
    expect(buildLogQuery({ level: 'ERROR', message: '', logger: '   ' }, 0, 50)).toBe(
      '?level=ERROR&limit=50',
    )
  })

  it('trims whitespace around values', () => {
    expect(buildLogQuery({ request_id: '  req-1  ' }, 0, 50)).toBe('?request_id=req-1&limit=50')
  })

  it('adds no offset on the first page', () => {
    expect(buildLogQuery({}, 0, 50)).toBe('?limit=50')
  })

  it('computes the offset from the page size from page 2 on', () => {
    expect(buildLogQuery({}, 2, 50)).toBe('?limit=50&offset=100')
  })

  it('escapes values with symbols (passes LIKE % through as is)', () => {
    expect(buildLogQuery({ message: '100% done' }, 0, 50)).toBe('?message=100%25+done&limit=50')
  })
})

describe('hasNextPage', () => {
  it('has a next page when the total exceeds the end of the page', () => {
    expect(hasNextPage(120, 0, 50)).toBe(true)
    expect(hasNextPage(120, 1, 50)).toBe(true)
    expect(hasNextPage(120, 2, 50)).toBe(false)
  })

  it('has no next page with 0 rows', () => {
    expect(hasNextPage(0, 0, 50)).toBe(false)
  })
})

describe('pageRange', () => {
  it('returns the shown range 1-based', () => {
    expect(pageRange(120, 1, 50, 50)).toEqual({ first: 51, last: 100 })
  })

  it('ends the last page at the number of rows actually shown', () => {
    expect(pageRange(120, 2, 20, 50)).toEqual({ first: 101, last: 120 })
  })

  it('returns 0-0 with 0 rows', () => {
    expect(pageRange(0, 0, 0, 50)).toEqual({ first: 0, last: 0 })
  })
})

describe('formatUtcTimestamp', () => {
  it('replaces T with a space and truncates to seconds', () => {
    expect(formatUtcTimestamp('2026-07-30T13:10:33.602668')).toBe('2026-07-30 13:10:33')
  })

  it('handles values without microseconds', () => {
    expect(formatUtcTimestamp('2026-07-30T13:10:33')).toBe('2026-07-30 13:10:33')
  })

  it('does not convert to local time (shows UTC as is)', () => {
    expect(formatUtcTimestamp('2026-01-01T00:00:00.000001')).toBe('2026-01-01 00:00:00')
  })
})

describe('orEmpty', () => {
  it('fills null with a symbol', () => {
    expect(orEmpty(null)).toBe('—')
  })

  it('treats 0 as a value (not blank)', () => {
    expect(orEmpty(0)).toBe('0')
  })

  it('returns an empty string as is', () => {
    expect(orEmpty('')).toBe('')
  })
})
