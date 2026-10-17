/**
 * E2E で入る初期管理者。
 *
 * メールアドレスは `shared/domain/auth/master_data.py` の `DEFAULT_ADMIN_EMAIL`。
 * パスワードは playwright.config.ts が `ADMIN_INITIAL_PASSWORD` としてサーバーへ渡し、
 * マイグレーションがその値で初期管理者を作る（既定のパスワードには頼らない）。
 */
export const ADMIN = {
  email: 'admin@example.com',
  password: 'e2e-initial-admin-password',
} as const
