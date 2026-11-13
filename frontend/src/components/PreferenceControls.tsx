/**
 * Language and theme selection. Shown under "Display settings" on the profile page
 * (ADR-0080 §3).
 *
 * The choice is stored in the browser (localStorage) and is independent per device
 * (ADR-0080 §1).
 */
import { LOCALE_LABELS, useI18n, type Locale } from '../i18n'
import { THEME_PREFERENCES, useTheme, type ThemePreference } from '../theme'

export function PreferenceControls() {
  const { t, locale, locales, setLocale } = useI18n()
  const { theme, setTheme } = useTheme()

  return (
    <>
      <label>
        {t('common.language')}
        <select
          value={locale}
          onChange={(e) => {
            setLocale(e.target.value as Locale)
          }}
        >
          {locales.map((value) => (
            <option key={value} value={value}>
              {LOCALE_LABELS[value]}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('common.theme')}
        <select
          value={theme}
          onChange={(e) => {
            setTheme(e.target.value as ThemePreference)
          }}
        >
          {THEME_PREFERENCES.map((value) => (
            <option key={value} value={value}>
              {t(`theme.${value}`)}
            </option>
          ))}
        </select>
      </label>
    </>
  )
}
