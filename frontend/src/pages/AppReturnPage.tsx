/**
 * アプリのログインの戻り先（S16。`/app/oauth2redirect`。ADR-0045）。
 *
 * ふだんは Android が App Links でアプリへ渡すので、この画面は出ない。出るのは
 * PC で開いた・アプリが入っていない・結び付けの確認（assetlinks.json）が済んでいない
 * ときだけで、**ここではログインを続けない**（認可コードはアプリしか引き換えられない）。
 */
import { Link } from 'react-router-dom'

import { useI18n } from '../i18n'

export function AppReturnPage() {
  const { t } = useI18n()
  return (
    <main className="auth-page">
      <div className="card">
        <h1>{t('appReturn.title')}</h1>
        <p>{t('appReturn.body')}</p>
        <Link to="/">{t('appReturn.openWeb')}</Link>
      </div>
    </main>
  )
}
