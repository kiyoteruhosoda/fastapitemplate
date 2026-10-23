/**
 * メンテナンス中・停止中の画面（ADR-0067）。
 *
 * 前段（edge）が閉じていると答えている間、アプリの画面の代わりに出す。見出しと本文は
 * edge の宣言の文言を出し、無ければ（古い edge）既定の文にする。戻りの見込みは
 * 閲覧者の時間帯で描く。
 *
 * 1 分ごとと、タブが手前へ戻ったときに確かめ直す。開いたと分かれば状態が外れ、
 * 呼んだ側（`main.tsx`）がアプリの画面へ戻す。確かめ方は引数で受け取る（試験で偽物を
 * 渡すため）。
 */
import { useEffect, useState, useSyncExternalStore } from 'react'

import { useI18n } from '../i18n'
import { currentOutage, subscribeOutage, type Outage } from '../services/maintenance'
import { ActionButton } from './ActionButton'

/** 確かめ直す間隔。 */
export const RECHECK_INTERVAL_MS = 60 * 1000

type Check = () => Promise<unknown>

/** 戻りの見込みを閲覧者の時間帯で。読めない値なら出さない。 */
function formatUntil(until: string | null, locale: string): string | null {
  if (!until) return null
  const at = new Date(until)
  if (Number.isNaN(at.getTime())) return null
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(at)
}

function useRecheck(check: Check): [boolean, () => void] {
  const [checking, setChecking] = useState(false)

  const run = (): void => {
    setChecking(true)
    void check().finally(() => {
      setChecking(false)
    })
  }

  useEffect(() => {
    const timer = window.setInterval(() => {
      void check()
    }, RECHECK_INTERVAL_MS)
    const onVisible = (): void => {
      if (document.visibilityState === 'visible') void check()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [check])

  return [checking, run]
}

export function MaintenanceScreen({ outage, check }: { outage: Outage; check: Check }) {
  const { t, locale } = useI18n()
  const [checking, recheck] = useRecheck(check)
  const stopped = outage.reason === 'stopped'
  const until = formatUntil(outage.until, locale)

  return (
    <main className="maintenance-screen" role="alert">
      <div className="maintenance-card">
        <h1>{outage.title ?? t(stopped ? 'maintenance.stoppedTitle' : 'maintenance.title')}</h1>
        <p>{outage.body ?? t(stopped ? 'maintenance.stoppedBody' : 'maintenance.body')}</p>
        {outage.message && (
          <p className="maintenance-reason">
            {t('maintenance.reason', { reason: outage.message })}
          </p>
        )}
        {until && <p className="maintenance-until">{t('maintenance.until', { time: until })}</p>}
        <p className="maintenance-note">{t('maintenance.autoCheck')}</p>
        <ActionButton type="button" pending={checking} onClick={recheck}>
          {t('maintenance.checkNow')}
        </ActionButton>
      </div>
    </main>
  )
}

/** 閉じている間だけ画面を出す。 */
export function MaintenanceGate({ check }: { check: Check }) {
  const outage = useSyncExternalStore(subscribeOutage, currentOutage)
  if (!outage) return null
  return <MaintenanceScreen outage={outage} check={check} />
}
