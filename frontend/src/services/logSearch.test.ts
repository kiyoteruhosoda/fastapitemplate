/** ログ検索のクエリ組み立て・ページング計算・行の表示整形。 */
import { describe, expect, it } from 'vitest'

import { buildLogQuery, formatUtcTimestamp, hasNextPage, orEmpty, pageRange } from './logSearch'

describe('buildLogQuery', () => {
  it('未入力の項目はクエリに載せない', () => {
    expect(buildLogQuery({ level: 'ERROR', message: '', logger: '   ' }, 0, 50)).toBe(
      '?level=ERROR&limit=50',
    )
  })

  it('値の前後の空白を落とす', () => {
    expect(buildLogQuery({ request_id: '  req-1  ' }, 0, 50)).toBe('?request_id=req-1&limit=50')
  })

  it('先頭ページでは offset を付けない', () => {
    expect(buildLogQuery({}, 0, 50)).toBe('?limit=50')
  })

  it('2 ページ目以降は件数から offset を求める', () => {
    expect(buildLogQuery({}, 2, 50)).toBe('?limit=50&offset=100')
  })

  it('記号を含む値をエスケープする（LIKE の % もそのまま渡す）', () => {
    expect(buildLogQuery({ message: '100% done' }, 0, 50)).toBe('?message=100%25+done&limit=50')
  })
})

describe('hasNextPage', () => {
  it('総件数がページ末尾を超えていれば次がある', () => {
    expect(hasNextPage(120, 0, 50)).toBe(true)
    expect(hasNextPage(120, 1, 50)).toBe(true)
    expect(hasNextPage(120, 2, 50)).toBe(false)
  })

  it('0 件なら次はない', () => {
    expect(hasNextPage(0, 0, 50)).toBe(false)
  })
})

describe('pageRange', () => {
  it('表示中の範囲を 1 始まりで返す', () => {
    expect(pageRange(120, 1, 50, 50)).toEqual({ first: 51, last: 100 })
  })

  it('最終ページは実際に表示した件数で終わる', () => {
    expect(pageRange(120, 2, 20, 50)).toEqual({ first: 101, last: 120 })
  })

  it('0 件のときは 0〜0', () => {
    expect(pageRange(0, 0, 0, 50)).toEqual({ first: 0, last: 0 })
  })
})

describe('formatUtcTimestamp', () => {
  it('T を空白にして秒までに切る', () => {
    expect(formatUtcTimestamp('2026-07-30T13:10:33.602668')).toBe('2026-07-30 13:10:33')
  })

  it('マイクロ秒が無い値もそのまま扱える', () => {
    expect(formatUtcTimestamp('2026-07-30T13:10:33')).toBe('2026-07-30 13:10:33')
  })

  it('ローカル時刻へ変換しない（UTC のまま表示する）', () => {
    expect(formatUtcTimestamp('2026-01-01T00:00:00.000001')).toBe('2026-01-01 00:00:00')
  })
})

describe('orEmpty', () => {
  it('null は記号で埋める', () => {
    expect(orEmpty(null)).toBe('—')
  })

  it('0 は値として扱う（空欄にしない）', () => {
    expect(orEmpty(0)).toBe('0')
  })

  it('空文字はそのまま返す', () => {
    expect(orEmpty('')).toBe('')
  })
})
