import { describe, expect, it } from 'vitest'

import { bannerItem, bellItems, isInAppLink, type InboxItem } from './notifications'
import { applicationServerKey } from './webPush'

function item(overrides: Partial<InboxItem>): InboxItem {
  return {
    id: 1,
    title: 't',
    body: '',
    link_url: null,
    channels: ['bell'],
    sent_at: '2026-09-29T01:00:00Z',
    read_at: null,
    dismissed_at: null,
    ...overrides,
  }
}

describe('notifications', () => {
  it('shows at the top only the newest unclosed banner', () => {
    const inbox = {
      items: [
        item({ id: 3, channels: ['bell'] }),
        item({ id: 2, channels: ['banner'] }),
        item({ id: 1, channels: ['banner'] }),
      ],
      unread_count: 1,
    }
    expect(bannerItem(inbox)?.id).toBe(2)
    expect(bellItems(inbox).map((i) => i.id)).toEqual([3])
    expect(bannerItem(null)).toBeNull()
  })

  it('tells in-app destinations apart (// is another host)', () => {
    expect(isInAppLink('/items')).toBe(true)
    expect(isInAppLink('//evil.example/')).toBe(false)
    expect(isInAppLink('https://example.com/')).toBe(false)
  })

  it('decodes the public key from base64url into a 65-byte point', () => {
    const raw = new Uint8Array(65).map((_, i) => (i === 0 ? 4 : i))
    const encoded = btoa(String.fromCharCode(...raw))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
    expect(Array.from(applicationServerKey(encoded))).toEqual(Array.from(raw))
  })
})
