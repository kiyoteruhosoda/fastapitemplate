/**
 * 入る・出るときに手元へ残す印と、前段が閉じている間の聞き直し。
 *
 * - 入れたら、ボタンを押さずに入る試し（ADR-0066）の印を消す。消えないと、次に期限が切れても試さない
 * - サインアウトしたら印を付ける。付かないと、IdP の SSO が残っていてすぐ入り直してしまう
 * - 入った入口のテナント（ADR-0064）を覚え、IdP のサインアウトもそのテナントへ送る
 * - 前段が閉じている間は `/me` を聞き直さず、開いたらすぐ聞き直す（ADR-0067）
 */
import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ApiModule from '../services/api'
import { ApiError } from '../services/api'
import { reportOutage, reportReopened, resetOutageForTests } from '../services/maintenance'
import { maySilentSso } from '../services/silentSso'
import { rememberTenant, rememberedTenant } from '../services/tenantEntrance'
import { AuthProvider, RECONNECT_INTERVAL_MS, useAuth, type Me } from './AuthContext'

const { get, post, exchangeSsoTicket, startSsoLogout, assertPasskey } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  exchangeSsoTicket: vi.fn(),
  startSsoLogout: vi.fn(),
  assertPasskey: vi.fn(),
}))

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  api: { get, post },
}))
vi.mock('../services/sso', () => ({ exchangeSsoTicket, startSsoLogout }))
vi.mock('../services/webauthn', () => ({ assertPasskey }))

const ME: Me = {
  user_id: 1,
  email: 'admin@example.com',
  username: 'admin',
  scopes: [],
  roles: ['owner'],
  active_role: null,
  has_password: true,
  rp_logout_enabled: false,
}

const DECLARED = {
  reason: 'maintenance',
  title: null,
  body: null,
  message: null,
  until: null,
} as const

/** 描いた AuthProvider の中身を外から触る。 */
function renderAuth(): { current: () => ReturnType<typeof useAuth> } {
  let latest: ReturnType<typeof useAuth> | null = null
  function Probe() {
    latest = useAuth()
    return null
  }
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
  return {
    current: () => {
      if (!latest) throw new Error('AuthProvider が描かれていない')
      return latest
    },
  }
}

async function renderSignedOut() {
  get.mockRejectedValue(new ApiError(401, 'not_authenticated'))
  const auth = renderAuth()
  await waitFor(() => {
    expect(auth.current().loading).toBe(false)
  })
  get.mockResolvedValue(ME)
  return auth
}

/** 前に試して・サインアウトした跡（どちらかがあれば、ログイン画面は試さない）。 */
function leaveSilentSsoMarks() {
  window.localStorage.setItem('ssoSignedOut', '1')
  window.sessionStorage.setItem('ssoSilentTried', '1')
  expect(maySilentSso(new URLSearchParams())).toBe(false)
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    window.sessionStorage.clear()
    resetOutageForTests()
    post.mockResolvedValue({ expires_in: 300 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('入れたら試しの印を消す（ADR-0066）', () => {
    it('パスワードで入った', async () => {
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      await act(() => auth.current().login('admin@example.com', 'pw'))
      expect(auth.current().user).toEqual(ME)
      expect(maySilentSso(new URLSearchParams())).toBe(true)
    })

    it('パスキーで入った', async () => {
      post.mockResolvedValueOnce({ challenge_id: 'c', public_key: {} })
      assertPasskey.mockResolvedValue({ id: 'cred' })
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      await act(() => auth.current().loginWithPasskey())
      expect(maySilentSso(new URLSearchParams())).toBe(true)
    })

    it('SSO で入った（戻り先を返す）', async () => {
      exchangeSsoTicket.mockResolvedValue({ expires_in: 300, redirect_to: '/items' })
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      let back = ''
      await act(async () => {
        back = await auth.current().completeSsoLogin('ticket')
      })
      expect(back).toBe('/items')
      expect(maySilentSso(new URLSearchParams())).toBe(true)
    })

    it('入れなかったら印は残す', async () => {
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      post.mockRejectedValueOnce(new ApiError(401, 'invalid_credentials'))
      await act(async () => {
        await expect(auth.current().login('admin@example.com', 'wrong')).rejects.toThrow()
      })
      expect(maySilentSso(new URLSearchParams())).toBe(false)
    })
  })

  describe('入口のテナント（ADR-0064）', () => {
    it('入った入口のテナントを送り、覚える', async () => {
      const auth = await renderSignedOut()
      await act(() => auth.current().login('boss@acme.example', 'pw', undefined, 'acme'))
      expect(post).toHaveBeenCalledWith('/api/auth/login', {
        email: 'boss@acme.example',
        password: 'pw',
        totp_code: null,
        tenant: 'acme',
      })
      expect(rememberedTenant()).toBe('acme')
    })

    it('共通の入口から入ったら、前のテナントを忘れる', async () => {
      rememberTenant('acme')
      const auth = await renderSignedOut()
      await act(() => auth.current().login('admin@example.com', 'pw'))
      expect(post).toHaveBeenCalledWith(
        '/api/auth/login',
        expect.objectContaining({ tenant: null }),
      )
      expect(rememberedTenant()).toBeUndefined()
    })
  })

  describe('サインアウト', () => {
    it('印を付け、次にログイン画面を開いても試さない（IdP へは送らない設定）', async () => {
      get.mockResolvedValue(ME)
      const auth = renderAuth()
      await waitFor(() => {
        expect(auth.current().user).toEqual(ME)
      })
      await act(() => auth.current().logout())
      expect(auth.current().user).toBeNull()
      expect(post).toHaveBeenCalledWith('/api/auth/logout')
      expect(maySilentSso(new URLSearchParams())).toBe(false)
      expect(startSsoLogout).not.toHaveBeenCalled()
    })

    it('IdP まで通す設定なら、アプリのサインアウトが済んでから入口のテナントの IdP へ送る', async () => {
      rememberTenant('acme')
      get.mockResolvedValue({ ...ME, rp_logout_enabled: true })
      let finishLogout: (value: unknown) => void = () => undefined
      post.mockImplementation((path: string) =>
        path === '/api/auth/logout'
          ? new Promise((resolve) => {
              finishLogout = resolve
            })
          : Promise.resolve({ expires_in: 300 }),
      )
      const auth = renderAuth()
      await waitFor(() => {
        expect(auth.current().user).not.toBeNull()
      })
      let done: Promise<void> = Promise.resolve()
      act(() => {
        done = auth.current().logout()
      })
      expect(startSsoLogout).not.toHaveBeenCalled()
      await act(async () => {
        finishLogout(undefined)
        await done
      })
      expect(startSsoLogout).toHaveBeenCalledWith('acme')
    })
  })

  describe('前段が閉じている間（ADR-0067）', () => {
    it('届かない間も、閉じていれば聞き直さず、開いたらすぐ聞き直す', async () => {
      vi.useFakeTimers()
      get.mockRejectedValue(new ApiError(503, 'service_unavailable'))
      const auth = renderAuth()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(auth.current().unreachable).toBe(true)

      act(() => {
        reportOutage(DECLARED)
      })
      get.mockClear()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS * 3)
      })
      expect(get).not.toHaveBeenCalled()

      get.mockResolvedValue(ME)
      await act(async () => {
        reportReopened()
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(get).toHaveBeenCalledTimes(1)
      expect(auth.current().user).toEqual(ME)
      expect(auth.current().unreachable).toBe(false)
    })

    it('閉じていなければ、届かない間は間を置いて聞き直す', async () => {
      vi.useFakeTimers()
      get.mockRejectedValue(new ApiError(502, 'bad_gateway'))
      const auth = renderAuth()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(auth.current().unreachable).toBe(true)
      get.mockClear()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS)
      })
      expect(get).toHaveBeenCalledTimes(1)
    })
  })
})
