import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  formatMediumWithLocalZone,
  formatWithLocalZone,
  localZoneLabel,
  utcOffsetLabel,
  withLocalZone,
} from './localTime'

describe('utcOffsetLabel', () => {
  it('east is + and hours only', () => {
    expect(utcOffsetLabel(9 * 60)).toBe('UTC+9')
    expect(utcOffsetLabel(14 * 60)).toBe('UTC+14')
  })

  it('adds :minutes when there are minutes', () => {
    expect(utcOffsetLabel(5 * 60 + 30)).toBe('UTC+5:30')
    expect(utcOffsetLabel(5 * 60 + 45)).toBe('UTC+5:45')
    expect(utcOffsetLabel(10 * 60 + 5)).toBe('UTC+10:05')
  })

  it('west is -', () => {
    expect(utcOffsetLabel(-5 * 60)).toBe('UTC-5')
    expect(utcOffsetLabel(-(3 * 60 + 30))).toBe('UTC-3:30')
  })

  it('just UTC when there is no offset', () => {
    expect(utcOffsetLabel(0)).toBe('UTC')
  })
})

describe("the viewer's time zone", () => {
  const at = new Date('2026-11-04T22:00:00Z')

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('flips the sign of getTimezoneOffset (west positive) when writing', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-540)
    expect(localZoneLabel(at)).toBe('UTC+9')
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-330)
    expect(localZoneLabel(at)).toBe('UTC+5:30')
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(240)
    expect(localZoneLabel(at)).toBe('UTC-4')
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)
    expect(localZoneLabel(at)).toBe('UTC')
  })

  it('appends the time zone after the written time', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-540)
    expect(withLocalZone(at, '2026/11/05 07:00')).toBe('2026/11/05 07:00 UTC+9')
  })

  it('notification times carry the time zone too', () => {
    const value = at.toISOString()
    expect(formatWithLocalZone(value, 'en')).toBe(
      `${at.toLocaleString('en')} ${localZoneLabel(at)}`,
    )
  })

  it('times with a longer date carry the time zone too', () => {
    const shown = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(
      at,
    )
    expect(formatMediumWithLocalZone(at, 'en')).toBe(`${shown} ${localZoneLabel(at)}`)
  })
})
