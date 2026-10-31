/**
 * 二要素認証の登録（ADR-0093）。登録が要るログインでは、どの経路を開いてもこの画面だけが出る。
 *
 * 確定したらトークンを更新する。サーバーは更新のときに登録待ちかを決め直すので、これで権限が戻る。
 */
import { ActionButton } from '../components/ActionButton'
import { AppMark } from '../components/AppMark'
import { TwoFactorControls } from '../components/TwoFactorControls'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api } from '../services/api'
import { useAuth } from '../store/AuthContext'

export function TwoFactorSetupPage() {
  const { t } = useI18n()
  const { refreshMe, logout } = useAuth()

  const onEnabled = async () => {
    await api.post('/api/auth/refresh')
    await refreshMe()
  }
  const [signOut, signingOut] = usePendingAction(logout)

  return (
    <div className="auth-page">
      <div className="card">
        <AppMark size={44} />
        <h1>{t('security.setupTitle')}</h1>
        <p className="hint">{t('security.setupHint')}</p>
        <TwoFactorControls onEnabled={onEnabled} />
        <div>
          <ActionButton type="button" pending={signingOut} onClick={signOut}>
            {t('security.setupSignOut')}
          </ActionButton>
        </div>
      </div>
    </div>
  )
}
