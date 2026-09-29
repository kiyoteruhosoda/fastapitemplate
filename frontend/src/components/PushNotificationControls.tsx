/**
 * プロフィールの「この端末への通知」（ADR-0047）。
 *
 * 購読はブラウザ（端末）ごとなので、ここでの操作は**いま開いている端末だけ**に効く。
 * 扱えない・送れない設定のときは、押せないボタンを並べず理由だけ書く。
 */
import { useEffect, useState } from 'react'

import { useI18n } from '../i18n'
import { errorMessageKey } from '../services/api'
import {
  disablePush,
  enablePush,
  pushState,
  pushSupported,
  type PushState,
} from '../services/webPush'
import { ActionButton } from './ActionButton'
import { useToast } from './ToastNotification'

export function PushNotificationControls() {
  const { t } = useI18n()
  const { notify } = useToast()
  const [state, setState] = useState<PushState | null>(pushSupported() ? null : 'unsupported')
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!pushSupported()) return
    pushState()
      .then(setState)
      .catch(() => {
        setState('unavailable')
      })
  }, [])

  const run = async (action: () => Promise<PushState>) => {
    setPending(true)
    try {
      setState(await action())
    } catch (error) {
      notify('error', t(errorMessageKey(error)))
    } finally {
      setPending(false)
    }
  }

  if (state === null) return <p className="hint">{t('common.loading')}</p>
  if (state === 'unsupported' || state === 'unavailable' || state === 'denied') {
    return <p className="hint">{t(`push.${state}`)}</p>
  }
  return (
    <div className="push-controls">
      <p>{t(state === 'on' ? 'push.on' : 'push.off')}</p>
      <ActionButton
        type="button"
        className={state === 'on' ? undefined : 'button-primary'}
        pending={pending}
        onClick={() => {
          void run(state === 'on' ? disablePush : enablePush)
        }}
      >
        {t(state === 'on' ? 'push.disable' : 'push.enable')}
      </ActionButton>
    </div>
  )
}
