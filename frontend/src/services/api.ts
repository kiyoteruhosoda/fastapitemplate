/**
 * API クライアント（fetch ラッパー）。
 *
 * - **トークンは持たない**（ADR-0076 §4）。httpOnly Cookie で運ばれるので、
 *   この層は `credentials: 'same-origin'` で送るだけでよい。
 * - 更新系には CSRF の二重送信トークンを載せる（`csrf_token` Cookie の値）。
 * - 401 のとき更新の口を 1 回だけ叩いて再試行する（更新もトークンを Cookie で受ける）。
 * - バックエンドはエラーコード（{"error": "..."}）を返す。表示文言への変換は
 *   i18n（フロントエンド側）で行う。
 * - 前段（edge）が閉じていると答えた 503 は、メンテナンスの画面へ知らせる（ADR-0080 §10）。
 *   例外はこれまでどおり投げる（呼んだ側の処理は止まる。トーストは出ない）。
 */
import { currentOutage, outageFrom, reportOutage, reportReopened } from './maintenance'

/** CSRF の二重送信トークン。**この Cookie だけは JavaScript から読める。** */
const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const TWO_FACTOR_SETUP_REQUIRED = 'two_factor_setup_required'

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

/**
 * CSRF トークンを Cookie から読む。
 *
 * **毎回読み直す。** セッションを張り直すたびに新しくなるので、控えておくと
 * 更新やロール切り替えの後に古い値を送ることになる。
 */
function csrfToken(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]*)`))
  return match?.[1] ? decodeURIComponent(match[1]) : null
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

let refreshing: Promise<boolean> | null = null

/**
 * 更新の口を叩く。トークンは行きも帰りも Cookie なので、ここでは何も持ち回さない。
 */
function tryRefresh(): Promise<boolean> {
  // 同時に 401 になった要求は 1 本の更新を待つ（ADR-0091）
  refreshing ??= sendRefresh().finally(() => {
    refreshing = null
  })
  return refreshing
}

async function sendRefresh(): Promise<boolean> {
  const headers: Record<string, string> = {}
  const csrf = csrfToken()
  if (csrf) headers[CSRF_HEADER] = csrf
  const response = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers,
    credentials: 'same-origin',
  })
  return response.ok
}

async function request<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (UNSAFE_METHODS.has(method)) {
    const csrf = csrfToken()
    if (csrf) headers[CSRF_HEADER] = csrf
  }

  const init: RequestInit = { method, headers, credentials: 'same-origin' }
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
    const outage = outageFrom(response.status, payload)
    if (outage) {
      reportOutage(outage)
      throw new ApiError(response.status, 'service_unavailable')
    }
    const code = extractErrorCode(payload)
    // 使っている途中で必須になった。/me を読み直せば登録の画面が出る（ADR-0092）
    if (code === TWO_FACTOR_SETUP_REQUIRED) window.location.reload()
    throw new ApiError(response.status, code)
  }
  // 答えが返った＝閉じていない（メンテナンスの画面を出していれば戻す）
  if (currentOutage()) reportReopened()
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
