/**
 * アプリのログインの戻り先（S16。`/app/oauth2redirect`。ADR-0045 / ADR-0046）。
 *
 * ふだんは Android が App Links でアプリへ渡すので、この画面は出ない。出るのは
 * PC で開いた・アプリが入っていない・結び付けの確認（assetlinks.json）が済んでいない
 * ときと、⚠ **アプリの中のタブ（Custom Tab）が自動の移動ではアプリを開かなかったとき**である
 * （Chrome は利用者のタップの直後でない移動では、ほかのアプリを開かない。ADR-0046）。
 * 後者のために、認可コードが付いているときは**同じ URL をもう一度開くボタン**を出す。
 * タップで開き直せば、Chrome がアプリへ渡す。**ここではログインを続けない**
 * （認可コードはアプリしか引き換えられない。PC で押しても同じ画面に戻るだけ）。
 */
import { Link, useLocation } from 'react-router-dom'

import { useI18n } from '../i18n'

export function AppReturnPage() {
  const { t } = useI18n()
  const { search } = useLocation()
  const query = new URLSearchParams(search)
  const handingBack = query.has('code') && query.has('state')
  return (
    <main className="auth-page">
      <div className="card">
        <h1>{t('appReturn.title')}</h1>
        {handingBack ? (
          <>
            <p>{t('appReturn.tapToReturn')}</p>
            <p>
              <a className="button-primary" href={window.location.href}>
                {t('appReturn.returnToApp')}
              </a>
            </p>
          </>
        ) : null}
        <p>{t('appReturn.body')}</p>
        <Link to="/">{t('appReturn.openWeb')}</Link>
      </div>
    </main>
  )
}
