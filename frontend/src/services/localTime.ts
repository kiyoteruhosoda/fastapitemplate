/**
 * 画面に出す時刻の書き方。サーバーは UTC で返し、見る人の時計に直すのはここだけ
 * （CLAUDE.md「時刻の契約」）。
 *
 * 時刻の後ろには時間帯を `UTC+9` の形で付ける。コピーした時刻がどの時計の時刻か
 * わかるように。`JST` のような略称は環境ごとに出たり出なかったりするので数字で書く。
 *
 * 時刻を文字にするのはこのファイルだけ（ADR-0105）。ほかで `toLocaleString`・
 * `Intl.DateTimeFormat` を書くと ESLint が止める。
 */

/** UTC からのずれ（分・東が正）を `UTC+9`・`UTC+5:30`・`UTC-3:30`・`UTC` の形に。 */
export function utcOffsetLabel(offsetMinutes: number): string {
  if (offsetMinutes === 0) return 'UTC'
  const sign = offsetMinutes < 0 ? '-' : '+'
  const abs = Math.abs(offsetMinutes)
  const hours = Math.floor(abs / 60)
  const minutes = abs % 60
  const tail = minutes === 0 ? '' : `:${String(minutes).padStart(2, '0')}`
  return `UTC${sign}${hours}${tail}`
}

/** その時点での、見る人の時間帯（夏時間はその日のもの）。 */
export function localZoneLabel(at: Date): string {
  // getTimezoneOffset は西が正なので向きを逆にする。
  return utcOffsetLabel(-at.getTimezoneOffset())
}

/** 書式どおりに描いた時刻の後ろに時間帯を付ける。 */
export function withLocalZone(at: Date, formatted: string): string {
  return `${formatted} ${localZoneLabel(at)}`
}

/** 既定の書式（`toLocaleString`）で描いた時刻に時間帯を添える。 */
export function formatWithLocalZone(value: string, locale: string): string {
  const at = new Date(value)
  return withLocalZone(at, at.toLocaleString(locale))
}

/** 日付を少し長め（`Nov 5, 2026`）にした時刻に時間帯を添える。メンテナンス画面の戻りの見込みなど。 */
export function formatMediumWithLocalZone(at: Date, locale: string): string {
  return withLocalZone(
    at,
    new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(at),
  )
}
