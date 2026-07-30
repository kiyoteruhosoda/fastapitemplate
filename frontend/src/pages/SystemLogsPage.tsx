import { useEffect, useState } from 'react'

import { useI18n } from '../i18n'
import { api } from '../services/api'

interface LogEntry {
  id: number
  created_at: string
  level: string
  logger: string
  message: string
  request_id: string | null
  path: string | null
  status_code: number | null
}

export function SystemLogsPage() {
  const { t } = useI18n()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [level, setLevel] = useState('')

  useEffect(() => {
    const query = level ? `?level=${level}` : ''
    void api.get<LogEntry[]>(`/api/admin/logs${query}`).then(setLogs)
  }, [level])

  return (
    <div className="card">
      <h1>{t('logs.title')}</h1>
      <select
        value={level}
        onChange={(e) => {
          setLevel(e.target.value)
        }}
      >
        <option value="">ALL</option>
        <option value="INFO">INFO</option>
        <option value="WARNING">WARNING</option>
        <option value="ERROR">ERROR</option>
      </select>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Time (UTC)</th>
              <th>Level</th>
              <th>Logger</th>
              <th>Message</th>
              <th>requestId</th>
              <th>Path</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{log.created_at}</td>
                <td>{log.level}</td>
                <td>{log.logger}</td>
                <td>{log.message}</td>
                <td>
                  <code>{log.request_id}</code>
                </td>
                <td>{log.path}</td>
                <td>{log.status_code}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
