/**
 * Per-tenant entry points (`/t/<slug>/login`; ADR-0079 §1 decision 8, ADR-0079 §4).
 *
 * With a single tenant the entry point needs no name (`/login`). With several, a tenant's users
 * sign in through that tenant's entry point. Remember the entry point used, and return there after
 * sign-out or expiry.
 *
 * WARNING: **Remembering it is for convenience only.** It has nothing to do with authorization
 * (even if the entry point is rewritten, only that tenant's users can sign in). Browsers that
 * can't read or write it don't remember and fall back to the shared entry point.
 */

const STORAGE_KEY = 'signInTenant'

export function rememberTenant(tenant: string | undefined): void {
  try {
    if (tenant) window.localStorage.setItem(STORAGE_KEY, tenant)
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Sign-in still works even if it can't be remembered
  }
}

export function rememberedTenant(): string | undefined {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? undefined
  } catch {
    return undefined
  }
}

/** Path of the entry-point screen. */
export function loginPathOf(tenant: string | undefined): string {
  return tenant ? `/t/${encodeURIComponent(tenant)}/login` : '/login'
}

/** Path of the forgot-password screen (same tenant as the entry point). */
export function forgotPasswordPathOf(tenant: string | undefined): string {
  return tenant ? `/t/${encodeURIComponent(tenant)}/forgot-password` : '/forgot-password'
}
