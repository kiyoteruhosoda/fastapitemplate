/**
 * ベルと画面上部のお知らせ（ADR-0047）。
 *
 * 見るのは、未読の数の出し方、押したら既読にして行き先へ進むこと、上部の知らせを
 * 閉じられること、`channels` で出る場所が分かれること。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import type { Inbox, InboxItem } from '../services/notifications'
import { InboxProvider } from '../store/InboxContext'
import { NotificationBanner } from './NotificationBanner'
import { NotificationBell } from './NotificationBell'
import { ToastProvider } from './ToastNotification'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost },
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function item(overrides: Partial<InboxItem>): InboxItem {
  return {
    id: 1,
    title: 'Maintenance tonight',
    body: 'We stop at 22:00',
    link_url: '/items',
    channels: ['bell'],
    sent_at: '2026-09-29T01:00:00Z',
    read_at: null,
    dismissed_at: null,
    ...overrides,
  }
}

function serve(inbox: Inbox) {
  apiGet.mockImplementation((path: string) =>
    path === '/api/notifications' ? Promise.resolve(inbox) : Promise.reject(new Error(path)),
  )
}

function renderWith() {
  render(
    <MemoryRouter initialEntries={['/']}>
      <I18nProvider settings={SETTINGS}>
        <ToastProvider>
          <InboxProvider>
            <NotificationBell />
            <NotificationBanner />
            <Routes>
              <Route path="/" element={<p>home</p>} />
              <Route path="/items" element={<p>items page</p>} />
            </Routes>
          </InboxProvider>
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiPost.mockResolvedValue(undefined)
  })

  it('未読の数を出し、押したら既読にして行き先を開く', async () => {
    serve({ items: [item({})], unread_count: 1 })
    renderWith()

    const bell = await screen.findByRole('button', { name: 'Notifications (1 unread)' })
    fireEvent.click(bell)
    fireEvent.click(screen.getByRole('button', { name: /Maintenance tonight/ }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/notifications/1/read')
    })
    expect(await screen.findByText('items page')).toBeInTheDocument()
  })

  it('既読のものは押しても既読の要求を出さない', async () => {
    serve({ items: [item({ read_at: '2026-09-29T02:00:00Z', link_url: null })], unread_count: 0 })
    renderWith()

    fireEvent.click(await screen.findByRole('button', { name: 'Notifications' }))
    fireEvent.click(screen.getByRole('button', { name: /Maintenance tonight/ }))

    expect(apiPost).not.toHaveBeenCalled()
  })

  it('すべて既読にできる', async () => {
    serve({ items: [item({}), item({ id: 2, title: 'Second' })], unread_count: 2 })
    renderWith()

    fireEvent.click(await screen.findByRole('button', { name: 'Notifications (2 unread)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Mark all as read' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/notifications/read-all')
    })
  })

  it('上部だけのお知らせはベルの一覧に出ない', async () => {
    serve({ items: [item({ channels: ['banner'] })], unread_count: 0 })
    renderWith()

    fireEvent.click(await screen.findByRole('button', { name: 'Notifications' }))

    expect(screen.getByText('No notifications yet.')).toBeInTheDocument()
  })
})

describe('NotificationBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiPost.mockResolvedValue(undefined)
  })

  it('閉じていない上部のお知らせを出し、閉じられる', async () => {
    serve({ items: [item({ channels: ['banner'] })], unread_count: 0 })
    renderWith()

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss this notice' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/notifications/1/dismiss')
    })
  })

  it('押すと閉じて行き先を開く', async () => {
    serve({ items: [item({ channels: ['banner'] })], unread_count: 0 })
    renderWith()

    const status = await screen.findByRole('status')
    fireEvent.click(status.querySelector('button.notification-banner-text') as HTMLButtonElement)

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/notifications/1/dismiss')
    })
    expect(await screen.findByText('items page')).toBeInTheDocument()
  })

  it('閉じたものとベルだけのものは出さない', async () => {
    serve({
      items: [
        item({ id: 1, channels: ['banner'], dismissed_at: '2026-09-29T02:00:00Z' }),
        item({ id: 2, channels: ['bell'] }),
      ],
      unread_count: 1,
    })
    renderWith()

    await screen.findByRole('button', { name: 'Notifications (1 unread)' })
    expect(screen.queryByRole('button', { name: 'Dismiss this notice' })).not.toBeInTheDocument()
  })
})
