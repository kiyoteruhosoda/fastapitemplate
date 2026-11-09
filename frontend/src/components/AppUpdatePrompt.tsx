/**
 * 「新しい版があります」の知らせ（ADR-0080 §7・出す場所は ADR-0106）。
 *
 * 新しい版が待機したときだけ画面のいちばん上に帯で出し、押されたら再読み込みする。
 * 帯はどの画面にも出し（ログイン画面にはヘッダーが無いので、ヘッダーの中ではなく
 * その上に置く）、下へ送っても上に残す。サインイン後の画面ではヘッダーが帯の真下に
 * 付くよう、帯の高さを CSS 変数 `--update-bar-height` で渡す（折り返すと高さが変わる）。
 *
 * トーストや画面の下に浮かぶ知らせは使わない ——数秒で消えたり本文に紛れたりして、
 * 見落とした利用者は古い版のまま使い続けることになる。
 *
 * 見張り方（`services/appUpdate.ts`）は引数で受け取る。Service Worker を登録する
 * 副作用をこの部品から切り離し、試験では偽の見張りを渡せるようにするため。
 */
import { useEffect, useRef, useState } from 'react'

import { useI18n } from '../i18n'
import type { ApplyUpdate, WatchForUpdate } from '../services/appUpdate'
import { ActionButton } from './ActionButton'

export function AppUpdatePrompt({ watch }: { watch: WatchForUpdate }) {
  const { t } = useI18n()
  const [apply, setApply] = useState<ApplyUpdate | null>(null)
  const [applying, setApplying] = useState(false)
  const barRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // useState は関数を「遅延初期化」と解釈するので、関数そのものを入れるときは
    // 関数を返す関数を渡す。
    watch((applyUpdate) => {
      setApply(() => applyUpdate)
    })
  }, [watch])

  // 帯の高さをヘッダーの貼り付く位置へ渡す。帯が消えたら 0 に戻す。
  useEffect(() => {
    const bar = barRef.current
    if (!apply || bar === null) return
    const root = document.documentElement
    const publish = () => {
      root.style.setProperty('--update-bar-height', `${String(bar.offsetHeight)}px`)
    }
    publish()
    // jsdom には ResizeObserver が無い。高さは最初に 1 回渡してあるので、見張れなくても足りる。
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(publish)
    observer?.observe(bar)
    return () => {
      observer?.disconnect()
      root.style.removeProperty('--update-bar-height')
    }
  }, [apply])

  if (!apply) return null

  return (
    <div ref={barRef} className="update-bar" role="status">
      <span className="update-bar-text">{t('update.available')}</span>
      {/* 押してから画面が入れ替わるまでに間があるので、押せたことを見せる
          （ADR-0080 §5）。 */}
      <ActionButton
        type="button"
        className="update-bar-button"
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
