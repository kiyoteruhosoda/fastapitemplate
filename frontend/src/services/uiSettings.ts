/**
 * Initial UI settings (language, theme).
 *
 * Receives the defaults the operator chose in the admin console from the server, and uses them as
 * initial values while the user hasn't chosen anything. Needed on pre-sign-in screens too, so
 * fetched once before authentication (`main.tsx`).
 */
import { outageFrom, reportOutage } from './maintenance'

export interface UiSettings {
  languages: string[]
  default_locale: string
  default_theme: string
}

/** Show the screen even if the server is unreachable. The fallback for that case. */
export const FALLBACK_UI_SETTINGS: UiSettings = {
  languages: ['en', 'ja'],
  default_locale: 'en',
  default_theme: 'system',
}

export async function loadUiSettings(): Promise<UiSettings> {
  try {
    const response = await fetch('/api/ui/settings')
    if (!response.ok) {
      // If the front tier is closed, start on the maintenance screen (ADR-0080 §10)
      const outage = outageFrom(response.status, await response.json().catch(() => null))
      if (outage) reportOutage(outage)
      return FALLBACK_UI_SETTINGS
    }
    return (await response.json()) as UiSettings
  } catch {
    return FALLBACK_UI_SETTINGS
  }
}
