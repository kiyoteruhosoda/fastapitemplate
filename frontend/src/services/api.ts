/**
 * API クライアント（fetch ラッパー）。
 *
 * - JWT を localStorage に保持し、Authorization ヘッダーで送る。
 * - 401 のとき refresh トークンで1回だけ再試行する。
 * - バックエンドはエラーコード（{"error": "..."}）を返す。表示文言への変換は
 *   i18n（フロントエンド側）で行う。
 */

const ACCESS_KEY = 'access_token'
const REFRESH_KEY = 'refresh_token'

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string) {
    super(code)
    this.status = status
    this.code = code
  }
}

/**
 * 例外を i18n の翻訳キーへ変換する。
 *
 * バックエンドはエラーコードだけを返すので、画面側の扱いは常に
 * 「`error.<code>` を引く」に落ちる。各ページで同じ分岐を書かないための入口。
 */
export function errorMessageKey(error: unknown): string {
  return `error.${error instanceof ApiError ? error.code : 'unknown_error'}`
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export function hasTokens(): boolean {
  return localStorage.getItem(ACCESS_KEY) !== null
}

function extractErrorCode(body: unknown): string {
  if (body && typeof body === 'object') {
    const detail = (body as Record<string, unknown>).detail
    if (detail && typeof detail === 'object') {
      const code = (detail as Record<string, unknown>).error
      if (typeof code === 'string') return code
    }
    if (typeof detail === 'string') return detail
  }
  return 'unknown_error'
}

/** ``/api/auth/refresh`` の応答。 */
interface TokenPair {
  access_token: string
  refresh_token: string
}

async function tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh) return false
  const response = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (!response.ok) {
    clearTokens()
    return false
  }
  const pair = (await response.json()) as TokenPair
  setTokens(pair.access_token, pair.refresh_token)
  return true
}

async function request<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = {}
  const access = localStorage.getItem(ACCESS_KEY)
  if (access) headers['Authorization'] = `Bearer ${access}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const init: RequestInit = { method, headers }
  if (body !== undefined) init.body = JSON.stringify(body)

  const response = await fetch(path, init)

  if (response.status === 401 && retry && (await tryRefresh())) {
    return request<T>(method, path, body, false)
  }
  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      /* 非 JSON 応答 */
    }
    throw new ApiError(response.status, extractErrorCode(payload))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
