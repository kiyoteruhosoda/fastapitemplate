/**
 * 「新しい版があります」の知らせ（ADR-0035）。
 *
 * 新しい版が待機したときだけ画面の下に出し、押されたら再読み込みする。トーストは
 * 数秒で消える通知なので使わない ——見ていない間に出て消えると、利用者は古い版の
 * まま使い続けることになる。
 *
 * 見張り方（`services/appUpdate.ts`）は引数で受け取る。Service Worker を登録する
 * 副作用をこの部品から切り離し、試験では偽の見張りを渡せるようにするため。
 */
import { useEffect, useState } from 'react'

import { useI18n } from '../i18n'
import type { ApplyUpdate, WatchForUpdate } from '../services/appUpdate'
import { ActionButton } from './ActionButton'

export function AppUpdatePrompt({ watch }: { watch: WatchForUpdate }) {
  const { t } = useI18n()
  const [apply, setApply] = useState<ApplyUpdate | null>(null)
  const [applying, setApplying] = useState(false)

  useEffect(() => {
    // useState は関数を「遅延初期化」と解釈するので、関数そのものを入れるときは
    // 関数を返す関数を渡す。
    watch((applyUpdate) => {
      setApply(() => applyUpdate)
    })
  }, [watch])

  if (!apply) return null

  return (
    <div className="update-prompt" role="status">
      <span className="update-prompt-text">{t('update.available')}</span>
      {/* 押してから画面が入れ替わるまでに間があるので、押せたことを見せる
          （ADR-0022）。 */}
      <ActionButton
        type="button"
        className="button-primary"
        pending={applying}
        onClick={() => {
          setApplying(true)
          apply()
        }}
      >
        {t('update.reload')}
      </ActionButton>
    </div>
  )
}
