/**
 * ログイン画面を開いたとき、IdP で入っていればボタンを押さずに入れる（ADR-0066）。
 *
 * 画面を描く前に `prompt=none` で IdP へ送り出す。入っていれば code が返ってふつうの SSO と
 * 同じ道で入り、入っていなければ IdP は画面を出さずに戻す（サーバーが `?sso_silent=declined`
 * を付けてログイン画面へ戻す）。
 *
 * 試さないとき（ループと、頼んでいない入り直しを防ぐ）:
 *
 * - **サインアウトした後**。サインアウトは既定で IdP の SSO を切らないので、試すとすぐに
 *   入り直してしまう。印は `localStorage`（ほかのタブで開いても試さない）
 * - **このタブで一度試した後**。印は `sessionStorage`
 * - ログイン画面に行き先（`redirect_to`）以外のもの（エラー・サインアウトの知らせ・試した印）が
 *   付いているとき
 *
 * どちらの印も、どの入口でも**入れたら消す**（次に期限が切れたときはまた試す）。
 *
 * ⚠ **印を書けないブラウザでは試さない。** 書けないまま試すと、戻ってきたときに試したことが
 * 分からず、行き来が止まらない。
 */
import { REDIRECT_TO_PARAM } from './returnTo'

const TRIED_KEY = 'ssoSilentTried'
const SIGNED_OUT_KEY = 'ssoSignedOut'

/** この画面の URL のクエリと印から見て、試してよいか（印は付けない）。 */
export function maySilentSso(params: URLSearchParams): boolean {
  for (const name of params.keys()) {
    if (name !== REDIRECT_TO_PARAM) return false
  }
  try {
    return !window.localStorage.getItem(SIGNED_OUT_KEY) && !window.sessionStorage.getItem(TRIED_KEY)
  } catch {
    return false
  }
}

/** 送り出す直前に「このタブで試した」印を付ける。付けられなければ偽（そのときは試さない）。 */
export function markSilentSsoTried(): boolean {
  try {
    window.sessionStorage.setItem(TRIED_KEY, '1')
    return window.sessionStorage.getItem(TRIED_KEY) === '1'
  } catch {
    return false
  }
}

/** サインアウトした。次にログイン画面を開いても試さない。 */
export function markSignedOut(): void {
  try {
    window.localStorage.setItem(SIGNED_OUT_KEY, '1')
  } catch {
    // 書けないブラウザでは、そもそも試さない（markSilentSsoTried）
  }
}

/** 入れた。印を消し、次に期限が切れたときはまた試す。 */
export function clearSilentSsoMarks(): void {
  try {
    window.localStorage.removeItem(SIGNED_OUT_KEY)
    window.sessionStorage.removeItem(TRIED_KEY)
  } catch {
    // 消せなくても入れている
  }
}
