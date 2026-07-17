import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'

export function AdminDashboardPage() {
  const { t } = useI18n()
  const { user } = useAuth()

  return (
    <div className="card">
      <h1>{t('dashboard.title')}</h1>
      <p>
        {user?.username} ({user?.email})
      </p>
      <p>
        API docs: <a href="/docs">/docs</a> / OpenAPI: <a href="/openapi.json">/openapi.json</a>
      </p>
    </div>
  )
}
