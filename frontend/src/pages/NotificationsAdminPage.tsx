/**
 * お知らせの配信（ADR-0047。要 `notification:send`）。
 *
 * 上で書いて送り、下に送った記録（何人に配り、何人が読んだか）を並べる。
 * 出す場所（ベル・画面上部・端末への通知）は複数選べる。宛先は全員・グループ・個人の
 * どれか 1 つ。**送った時点の顔ぶれに配る**ので、あとからグループに入った人には届かない。
 */
import { useEffect, useState, type FormEvent } from 'react'

import { ActionButton } from '../components/ActionButton'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import {
  notificationsApi,
  type AudienceKind,
  type AudienceOptions,
  type Channel,
  type SentNotification,
} from '../services/notifications'

const CHANNELS: Channel[] = ['bell', 'banner', 'push']
const AUDIENCE_KINDS: AudienceKind[] = ['all', 'group', 'user']

export function NotificationsAdminPage() {
  const { t, locale } = useI18n()
  const { notify } = useToast()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [link, setLink] = useState('')
  const [channels, setChannels] = useState<Channel[]>(['bell'])
  const [audienceKind, setAudienceKind] = useState<AudienceKind>('all')
  const [targetId, setTargetId] = useState('')
  const [options, setOptions] = useState<AudienceOptions>({ groups: [], users: [] })
  const [pushEnabled, setPushEnabled] = useState(false)
  const [sent, setSent] = useState<SentNotification[]>([])

  const reload = () => notificationsApi.sent().then(setSent)

  useEffect(() => {
    void reload()
    void notificationsApi.audiences().then(setOptions)
    // 端末への通知は、サーバーが送れる設定のときだけ選ばせる。
    void api
      .get<{ enabled: boolean }>('/api/notifications/push')
      .then((config) => {
        setPushEnabled(config.enabled)
      })
      .catch(() => {
        setPushEnabled(false)
      })
  }, [])

  const toggleChannel = (channel: Channel) => {
    setChannels((current) =>
      current.includes(channel) ? current.filter((c) => c !== channel) : [...current, channel],
    )
  }

  const audienceLabel = (item: SentNotification) => {
    const { kind, target_id: id } = item.audience
    if (kind === 'group') {
      const group = options.groups.find((g) => g.id === id)
      return t('notifications.audience.groupOf', { name: group?.name ?? `#${String(id)}` })
    }
    if (kind === 'user') {
      const user = options.users.find((u) => u.id === id)
      return t('notifications.audience.userOf', { name: user?.username ?? `#${String(id)}` })
    }
    return t('notifications.audience.all')
  }

  const [send, sending] = usePendingAction(async (e: FormEvent) => {
    e.preventDefault()
    try {
      const result = await notificationsApi.send({
        title,
        body,
        link_url: link.trim() || null,
        channels,
        audience: {
          kind: audienceKind,
          target_id: audienceKind === 'all' ? null : Number(targetId),
        },
      })
      notify('success', t('notifications.sent', { count: result.recipient_count }))
      setTitle('')
      setBody('')
      setLink('')
      await reload()
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  })

  const targets =
    audienceKind === 'group'
      ? options.groups.map((g) => ({
          id: g.id,
          label: t('groups.withCount', { name: g.name, count: g.member_count }),
        }))
      : options.users.map((u) => ({ id: u.id, label: `${u.username} <${u.email}>` }))

  return (
    <>
      <div className="card">
        <h1>{t('notifications.title')}</h1>
        <form className="dialog-form notification-form" onSubmit={send}>
          <label>
            {t('notifications.field.title')}
            <input
              value={title}
              maxLength={200}
              required
              onChange={(e) => {
                setTitle(e.target.value)
              }}
            />
          </label>
          <label>
            {t('notifications.field.body')}
            <textarea
              value={body}
              maxLength={2000}
              rows={4}
              onChange={(e) => {
                setBody(e.target.value)
              }}
            />
          </label>
          <label>
            {t('notifications.field.link')}
            <input
              value={link}
              maxLength={1000}
              placeholder="/items"
              onChange={(e) => {
                setLink(e.target.value)
              }}
            />
          </label>
          <p className="hint">{t('notifications.field.linkHint')}</p>

          <fieldset className="chip-choice">
            <legend>{t('notifications.field.channels')}</legend>
            {CHANNELS.map((channel) => (
              <label key={channel} className="chip-option">
                <input
                  type="checkbox"
                  checked={channels.includes(channel)}
                  disabled={channel === 'push' && !pushEnabled}
                  onChange={() => {
                    toggleChannel(channel)
                  }}
                />
                {t(`notifications.channel.${channel}`)}
              </label>
            ))}
            {!pushEnabled && <p className="hint">{t('notifications.pushNotConfigured')}</p>}
          </fieldset>

          <fieldset className="chip-choice">
            <legend>{t('notifications.field.audience')}</legend>
            {AUDIENCE_KINDS.map((kind) => (
              <label key={kind} className="chip-option">
                <input
                  type="radio"
                  name="audience"
                  checked={audienceKind === kind}
                  onChange={() => {
                    setAudienceKind(kind)
                    setTargetId('')
                  }}
                />
                {t(`notifications.audience.${kind}`)}
              </label>
            ))}
            {audienceKind !== 'all' && (
              <label>
                {t(
                  audienceKind === 'group'
                    ? 'notifications.field.group'
                    : 'notifications.field.user',
                )}
                <select
                  value={targetId}
                  required
                  onChange={(e) => {
                    setTargetId(e.target.value)
                  }}
                >
                  <option value="">{t('notifications.field.choose')}</option>
                  {targets.map((target) => (
                    <option key={target.id} value={target.id}>
                      {target.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </fieldset>

          <div className="dialog-actions">
            <ActionButton
              type="submit"
              className="button-primary"
              pending={sending}
              disabled={channels.length === 0}
            >
              {t('notifications.send')}
            </ActionButton>
          </div>
        </form>
      </div>

      <div className="card">
        <h2>{t('notifications.history')}</h2>
        {sent.length === 0 ? (
          <p className="hint">{t('notifications.historyEmpty')}</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('notifications.field.sentAt')}</th>
                  <th>{t('notifications.field.title')}</th>
                  <th>{t('notifications.field.channels')}</th>
                  <th>{t('notifications.field.audience')}</th>
                  <th>{t('notifications.field.read')}</th>
                </tr>
              </thead>
              <tbody>
                {sent.map((item) => (
                  <tr key={item.notification.id}>
                    <td>{new Date(item.notification.sent_at).toLocaleString(locale)}</td>
                    <td>{item.notification.title}</td>
                    <td>
                      {item.notification.channels
                        .map((c) => t(`notifications.channel.${c}`))
                        .join(' / ')}
                    </td>
                    <td>{audienceLabel(item)}</td>
                    <td>
                      {t('notifications.readOf', {
                        read: item.read_count,
                        total: item.recipient_count,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
