/**
 * Return target of the app's login (S16. `/app/oauth2redirect`. ADR-0081 §1 / ADR-0081 §2).
 *
 * Normally Android hands it to the app via App Links, so this page does not appear. It appears
 * when opened on a PC, when the app is not installed, when the link verification
 * (assetlinks.json) is not done, and note: **when the in-app tab (Custom Tab) did not open the
 * app on an automatic navigation** (Chrome does not open another app on a navigation that does
 * not directly follow a user tap. ADR-0081 §2).
 * For the latter, when an authorization code is present, a **button that reopens the same URL**
 * is shown. Reopening with a tap makes Chrome hand it to the app. **Login does not continue here**
 * (only the app can redeem the authorization code; pressing it on a PC just returns to this page).
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
