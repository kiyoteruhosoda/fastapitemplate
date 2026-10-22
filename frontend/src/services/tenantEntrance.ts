/**
 * テナントごとの入口（`/t/<slug>/login`。ADR-0061 決定 8・ADR-0064）。
 *
 * テナントが 1 つだけの環境では、入口に名前を付けなくてよい（`/login`）。複数あるときは、
 * テナントの利用者はそのテナントの入口から入る。入った入口を覚えておき、サインアウトや
 * 期限切れのあとはそこへ戻す。
 *
 * ⚠ **覚えるのは使い勝手のためだけ。** 権限には関わらない（入口を書き換えても、入れるのは
 * そのテナントの利用者だけ）。読めない・書けないブラウザでは覚えずに共通の入口へ戻す。
 */

const STORAGE_KEY = 'signInTenant'

export function rememberTenant(tenant: string | undefined): void {
  try {
    if (tenant) window.localStorage.setItem(STORAGE_KEY, tenant)
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // 覚えられなくても入れる
  }
}

export function rememberedTenant(): string | undefined {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? undefined
  } catch {
    return undefined
  }
}

/** 入口の画面の経路。 */
export function loginPathOf(tenant: string | undefined): string {
  return tenant ? `/t/${encodeURIComponent(tenant)}/login` : '/login'
}

/** パスワードを忘れたときの画面の経路（入口と同じテナント）。 */
export function forgotPasswordPathOf(tenant: string | undefined): string {
  return tenant ? `/t/${encodeURIComponent(tenant)}/forgot-password` : '/forgot-password'
}
