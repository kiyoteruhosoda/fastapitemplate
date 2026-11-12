/**
 * How times are written on screen. The server returns UTC; this is the only place it's converted to
 * the viewer's clock (CLAUDE.md "time contract").
 *
 * The time zone is appended as `UTC+9`, so a copied time shows which clock it's in. Abbreviations
 * like `JST` appear in some environments and not others, so write it numerically.
 *
 * This file is the only place times are turned into text (ADR-0105). Writing `toLocaleString` or
 * `Intl.DateTimeFormat` elsewhere is stopped by ESLint.
 */

/** Offset from UTC (minutes, east positive) as `UTC+9`, `UTC+5:30`, `UTC-3:30`, or `UTC`. */
export function utcOffsetLabel(offsetMinutes: number): string {
  if (offsetMinutes === 0) return 'UTC'
  const sign = offsetMinutes < 0 ? '-' : '+'
  const abs = Math.abs(offsetMinutes)
  const hours = Math.floor(abs / 60)
  const minutes = abs % 60
  const tail = minutes === 0 ? '' : `:${String(minutes).padStart(2, '0')}`
  return `UTC${sign}${hours}${tail}`
}

/** The viewer's time zone at that instant (daylight saving as of that day). */
export function localZoneLabel(at: Date): string {
  // getTimezoneOffset is west-positive, so flip the sign.
  return utcOffsetLabel(-at.getTimezoneOffset())
}

/** Append the time zone to a time rendered with the given format. */
export function withLocalZone(at: Date, formatted: string): string {
  return `${formatted} ${localZoneLabel(at)}`
}

/** Append the time zone to a time rendered with the default format (`toLocaleString`). */
export function formatWithLocalZone(value: string, locale: string): string {
  const at = new Date(value)
  return withLocalZone(at, at.toLocaleString(locale))
}

/**
 * Append the time zone to a time with a slightly longer date (`Nov 5, 2026`). E.g. the expected
 * return time on the maintenance screen.
 */
export function formatMediumWithLocalZone(at: Date, locale: string): string {
  return withLocalZone(
    at,
    new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(at),
  )
}
