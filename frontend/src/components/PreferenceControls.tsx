/**
 * 言語・テーマの選択。プロフィールページの「表示設定」に出す（ADR-0016）。
 *
 * 選択はブラウザ（localStorage）に保存され、端末ごとに独立する（ADR-0005）。
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
