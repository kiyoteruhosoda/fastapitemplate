/**
 * 言語・テーマの選択。
 *
 * 広い画面ではヘッダーに、狭い画面ではナビゲーションのドロワーの中に出す
 * （ヘッダーに並べると 390px 幅で 3 段に折り返してしまうため）。どちらに出すかは
 * `index.css` が `.header-preferences` / `.sidebar-preferences` の表示で切り替える。
 */
import { LOCALE_LABELS, useI18n, type Locale } from '../i18n'
import { THEME_PREFERENCES, useTheme, type ThemePreference } from '../theme'

export function PreferenceControls() {
  const { t, locale, locales, setLocale } = useI18n()
  const { theme, setTheme } = useTheme()

  return (
    <>
      <select
        aria-label={t('common.language')}
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
      <select
        aria-label={t('common.theme')}
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
    </>
  )
}
