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
  it('上部には、閉じていない banner のうち新しい 1 通だけを出す', () => {
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

  it('アプリの中の行き先を見分ける（// は別のホスト）', () => {
    expect(isInAppLink('/items')).toBe(true)
    expect(isInAppLink('//evil.example/')).toBe(false)
    expect(isInAppLink('https://example.com/')).toBe(false)
  })

  it('公開鍵を base64url から 65 バイトの点へ戻す', () => {
    const raw = new Uint8Array(65).map((_, i) => (i === 0 ? 4 : i))
    const encoded = btoa(String.fromCharCode(...raw))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
    expect(Array.from(applicationServerKey(encoded))).toEqual(Array.from(raw))
  })
})
