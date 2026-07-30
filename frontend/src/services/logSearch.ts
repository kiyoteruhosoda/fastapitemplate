/**
 * ログ検索画面の共通処理（システムログ画面・監査ログ画面が共用）。
 *
 * 絞り込み条件のクエリ組み立て・ページ送りの計算・行の表示整形をまとめる。
 * 2 画面が同じ振る舞いをするべき箇所で、画面ごとに書くと片方だけずれる。
 */

/** 1 ページの件数。バックエンドの上限（500）より小さい実用値。 */
export const PAGE_SIZE = 50

/** 検索フォームの値。キーはそのままクエリ名になる。 */
export type LogFilters = Record<string, string>

/** 検索結果（``total`` は条件に一致した総件数で、ページの件数ではない）。 */
export interface LogSearchResult<TEntry> {
  total: number
  entries: TEntry[]
}

/**
 * `?a=1&b=2` を組み立てる。空欄・空白のみの項目は落とす。
 *
 * `page` は 0 始まり。`offset` はここで算出するので、画面はページ番号だけを持つ。
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

/** 表示中のページに次があるか（総件数から求める）。 */
export function hasNextPage(total: number, page: number, pageSize = PAGE_SIZE): boolean {
  return (page + 1) * pageSize < total
}

/** 「51〜100 / 328 件」の範囲部分。0 件のときは 0〜0 を返す。 */
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
 * API が返す UTC の ISO 8601（`2026-07-30T13:10:33.602668`）を一覧向けに整える。
 *
 * `T` を空白にして秒までに切る。`T` のままだと表の狭い列で日付の途中
 * （`2026-07-` / `30T13:…`）で折り返され、マイクロ秒は一覧で読む値ではない。
 * ローカル時刻へは変換しない（画面は UTC で通す）。
 */
export function formatUtcTimestamp(value: string): string {
  return value.replace('T', ' ').replace(/\.\d+/, '')
}

/** 値の無いセルの表示。空欄だと「列がずれた」ように見えるため記号で埋める。 */
export const EMPTY_CELL = '—'

/** `null` を [`EMPTY_CELL`] に置き換える。 */
export function orEmpty(value: string | number | null): string {
  return value === null ? EMPTY_CELL : String(value)
}
