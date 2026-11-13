/**
 * Maintenance / outage screen (ADR-0080 §10).
 *
 * Shown instead of the app while the front tier (edge) reports that it is closed. The heading
 * and body use the text from edge's declaration, falling back to default text when absent
 * (older edge). The expected return time is rendered in the viewer's time zone.
 *
 * Rechecks every minute and when the tab comes back to the foreground. Once it is known to be
 * open the state clears and the caller (`main.tsx`) switches back to the app. The check is
 * passed in as an argument (so tests can pass a fake).
 */
import { useEffect, useState, useSyncExternalStore } from 'react'

import { useI18n } from '../i18n'
import { formatMediumWithLocalZone } from '../services/localTime'
import { currentOutage, subscribeOutage, type Outage } from '../services/maintenance'
import { ActionButton } from './ActionButton'

/** Recheck interval. */
export const RECHECK_INTERVAL_MS = 60 * 1000

type Check = () => Promise<unknown>

/** Expected return time in the viewer's time zone (with the zone). Omitted if unparsable. */
function formatUntil(until: string | null, locale: string): string | null {
  if (!until) return null
  const at = new Date(until)
  if (Number.isNaN(at.getTime())) return null
  return formatMediumWithLocalZone(at, locale)
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

/** Renders the screen only while closed. */
export function MaintenanceGate({ check }: { check: Check }) {
  const outage = useSyncExternalStore(subscribeOutage, currentOutage)
  if (!outage) return null
  return <MaintenanceScreen outage={outage} check={check} />
}
