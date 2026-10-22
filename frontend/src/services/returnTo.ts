/**
 * サインインの往復で行き先を落とさない（ADR-0055）。
 *
 * 未サインインで深いリンク（`/items?q=…` など）を開くと、ログイン画面へ送られる。
 * 行き先を持たずに送ると、サインインした先は着地（`/`）になり、**開こうとしていた画面には
 * 二度と戻れない**。経路だけでなくクエリも行き先の一部として持ち回す。
 *
 * ⚠ **外部 URL へ戻さない。** 正本の検証はサーバ側（`RedirectTarget.parse`）で、
 * ここは同じ形に絞ってから渡すだけ。
 */
import { loginPathOf, rememberedTenant } from './tenantEntrance'

/** ログイン画面と SSO の入口で使うクエリの名前（両側で同じ綴りを使う）。 */
export const REDIRECT_TO_PARAM = 'redirect_to'

/** 行き先が無い（または外を指している）ときの戻り先。 */
const LANDING = '/'

/**
 * サーバが受け取る長さの上限（`/api/auth/sso/login` の `redirect_to` と、往復の記録の列）。
 * 超えた値を渡すと入口が 422 で止まるので、着地へ倒す。
 */
const MAX_LENGTH = 255

/** 自サイト内の絶対パスだけを通す。⚠ サーバ側と同じ規則。片方だけ緩めない。 */
export function sanitizeRedirectTo(candidate: string | null | undefined): string {
  if (!candidate) return LANDING
  if (!candidate.startsWith('/')) return LANDING
  // `//evil.example` はプロトコル相対 URL。ブラウザは外部として解決する。
  if (candidate.startsWith('//')) return LANDING
  // `/\evil.example` を外部として解決するブラウザがある。
  if (candidate.startsWith('/\\')) return LANDING
  if (candidate.includes('\r') || candidate.includes('\n')) return LANDING
  if (candidate.length > MAX_LENGTH) return LANDING
  return candidate
}

/**
 * 未サインインのときに送るログイン画面の URL。
 *
 * 着地（`/`）から来たときは行き先を付けない（サインイン後に着地へ送るのは既定の振る舞い）。
 */
export function signInPathFor(location: { pathname: string; search?: string }): string {
  const here = sanitizeRedirectTo(`${location.pathname}${location.search ?? ''}`)
  // 前に入った入口（テナント）へ戻す（ADR-0064）
  const login = loginPathOf(rememberedTenant())
  if (here === LANDING) return login
  return `${login}?${REDIRECT_TO_PARAM}=${encodeURIComponent(here)}`
}
