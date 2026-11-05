import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  formatMediumWithLocalZone,
  formatWithLocalZone,
  localZoneLabel,
  utcOffsetLabel,
  withLocalZone,
} from './localTime'

describe('utcOffsetLabel', () => {
  it('東は + と時間だけ', () => {
    expect(utcOffsetLabel(9 * 60)).toBe('UTC+9')
    expect(utcOffsetLabel(14 * 60)).toBe('UTC+14')
  })

  it('分があれば :分 を付ける', () => {
    expect(utcOffsetLabel(5 * 60 + 30)).toBe('UTC+5:30')
    expect(utcOffsetLabel(5 * 60 + 45)).toBe('UTC+5:45')
    expect(utcOffsetLabel(10 * 60 + 5)).toBe('UTC+10:05')
  })

  it('西は -', () => {
    expect(utcOffsetLabel(-5 * 60)).toBe('UTC-5')
    expect(utcOffsetLabel(-(3 * 60 + 30))).toBe('UTC-3:30')
  })

  it('ずれが無ければ UTC だけ', () => {
    expect(utcOffsetLabel(0)).toBe('UTC')
  })
})

describe('見る人の時間帯', () => {
  const at = new Date('2026-11-04T22:00:00Z')

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('getTimezoneOffset（西が正）の向きを直して書く', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-540)
    expect(localZoneLabel(at)).toBe('UTC+9')
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-330)
    expect(localZoneLabel(at)).toBe('UTC+5:30')
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(240)
    expect(localZoneLabel(at)).toBe('UTC-4')
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0)
    expect(localZoneLabel(at)).toBe('UTC')
  })

  it('書いた時刻の後ろに時間帯を添える', () => {
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-540)
    expect(withLocalZone(at, '2026/11/05 07:00')).toBe('2026/11/05 07:00 UTC+9')
  })

  it('お知らせの時刻も時間帯つき', () => {
    const value = at.toISOString()
    expect(formatWithLocalZone(value, 'en')).toBe(
      `${at.toLocaleString('en')} ${localZoneLabel(at)}`,
    )
  })

  it('日付を長めにした時刻も時間帯つき', () => {
    const shown = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(
      at,
    )
    expect(formatMediumWithLocalZone(at, 'en')).toBe(`${shown} ${localZoneLabel(at)}`)
  })
})
