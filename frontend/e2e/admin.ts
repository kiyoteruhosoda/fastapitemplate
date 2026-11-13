/**
 * The initial admin used to sign in during E2E.
 *
 * The email is `DEFAULT_ADMIN_EMAIL` in `shared/domain/auth/master_data.py`.
 * playwright.config.ts passes the password to the server as `ADMIN_INITIAL_PASSWORD`, and the
 * migration creates the initial admin with it (the default password is not relied on).
 */
export const ADMIN = {
  email: 'admin@example.com',
  password: 'e2e-initial-admin-password',
} as const
