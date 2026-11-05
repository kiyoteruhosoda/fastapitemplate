/**
 * API クライアント（fetch ラッパー）。
 *
 * - **トークンは持たない**（ADR-0076 §4）。httpOnly Cookie で運ばれるので、
 *   この層は `credentials: 'same-origin'` で送るだけでよい。
 * - 更新系には CSRF の二重送信トークンを載せる（`csrf_token` Cookie の値）。
 * - 401 のとき 1 回だけログインを続けてから再試行する。パスワード・パスキーで入ったログインは
 *   更新の口、SSO で入ったログインは見えない枠で IdP へ問い合わせる（ADR-0104。`silentRenewal.ts`）。
 *   続けられなければ「ログインが終わった」と知らせる（画面はログイン画面へ送る。書きかけは
 *   `useSessionDraft` が sessionStorage に残している）。
 * - バックエンドはエラーコード（{"error": "..."}）を返す。表示文言への変換は
 *   i18n（フロントエンド側）で行う。
 * - 前段（edge）が閉じていると答えた 503 は、メンテナンスの画面へ知らせる（ADR-0080 §10）。
 *   例外はこれまでどおり投げる（呼んだ側の処理は止まる。トーストは出ない）。
 */
import { currentOutage, outageFrom, reportOutage, reportReopened } from './maintenance'
import { markSilentSsoTried, clearSilentSsoMarks, signedOutHere } from './silentSso'
import { reportSessionEnded } from './sessionEnded'
import { oneAtATime, renewInFrame } from './silentRenewal'

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
 * ログインを続ける。トークンは行きも帰りも Cookie なので、ここでは何も持ち回さない。
 */
function tryRefresh(): Promise<boolean> {
  // 同時に 401 になった要求は 1 本を待つ（ADR-0091）
  refreshing ??= continueSession().finally(() => {
    refreshing = null
  })
  return refreshing
}

async function continueSession(): Promise<boolean> {
  // パスワード・パスキーで入ったログインは更新の札を持つ（SSO で入ったログインには無いので 401 で返る）
  if (await sendRefresh()) return true
  // サインアウトした後は IdP に問い合わせない（IdP のログイン状態は既定で残るので、入り直してしまう）
  if (signedOutHere()) return false
  return oneAtATime(async () => {
    // 待っている間に、ほかのタブが続けていたかもしれない（Cookie は共有）
    if (await stillSignedIn()) return true
    const result = await renewInFrame()
    if (result === 'renewed') clearSilentSsoMarks()
    // 断られた: ログイン画面が開いても、このタブではもう試さない（再読み込みでは試す。ADR-0077 §10）
    else if (result === 'declined') markSilentSsoTried()
    return result === 'renewed'
  })
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

async function stillSignedIn(): Promise<boolean> {
  const response = await fetch('/api/auth/me', { credentials: 'same-origin' })
  return response.ok
}

/**
 * ログインが切れた・無いという 401 か。入口の 401（パスワード違い・二要素の不足など）では続けない
 * ——続けると、パスワードを打ち間違えただけで IdP への問い合わせが走る。
 */
const SESSION_ERRORS = new Set(['authentication_required', 'invalid_token'])

async function meansSessionExpired(response: Response): Promise<boolean> {
  try {
    return SESSION_ERRORS.has(extractErrorCode(await response.clone().json()))
  } catch {
    return false
  }
}

/** 失敗の応答を例外へ変える。前段が閉じている・二要素の登録が要る、はここで画面へ知らせる。 */
async function failureOf(response: Response): Promise<ApiError> {
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    /* 非 JSON 応答 */
  }
  const outage = outageFrom(response.status, payload)
  if (outage) {
    reportOutage(outage)
    return new ApiError(response.status, 'service_unavailable')
  }
  const code = extractErrorCode(payload)
  // 使っている途中で必須になった。/me を読み直せば登録の画面が出る（ADR-0093）
  if (code === TWO_FACTOR_SETUP_REQUIRED) window.location.reload()
  return new ApiError(response.status, code)
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

  if (response.status === 401 && retry && (await meansSessionExpired(response))) {
    if (await tryRefresh()) return request<T>(method, path, body, false)
    reportSessionEnded()
  }
  if (!response.ok) throw await failureOf(response)
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
