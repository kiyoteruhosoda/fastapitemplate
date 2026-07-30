import { useEffect, useState } from 'react'

import { useI18n } from '../i18n'
import { api } from '../services/api'

interface Permission {
  id: number
  code: string
}

export function PermissionsPage() {
  const { t } = useI18n()
  const [permissions, setPermissions] = useState<Permission[]>([])

  useEffect(() => {
    void api.get<Permission[]>('/api/admin/permissions').then(setPermissions)
  }, [])

  return (
    <div className="card">
      <h1>{t('permissions.title')}</h1>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Code</th>
            </tr>
          </thead>
          <tbody>
            {permissions.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td>
                  <code>{p.code}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
