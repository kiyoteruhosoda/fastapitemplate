import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { AppUpdatePrompt } from './components/AppUpdatePrompt'
import { MaintenanceGate } from './components/MaintenanceScreen'
import { ToastProvider } from './components/ToastNotification'
import { I18nProvider } from './i18n'
import './index.css'
import { watchForUpdate } from './services/appUpdate'
import {
  checkService,
  currentOutage,
  subscribeOutage,
  watchLazyLoadFailures,
} from './services/maintenance'
import { loadUiSettings, type UiSettings } from './services/uiSettings'
import { AuthProvider } from './store/AuthContext'
import { ThemeProvider } from './theme'

function render(settings: UiSettings) {
  const container = document.getElementById('root')
  if (!container) throw new Error('#root not found in index.html')

  createRoot(container).render(
    <StrictMode>
      <I18nProvider settings={settings}>
        <ThemeProvider settings={settings}>
          <AuthProvider>
            <ToastProvider>
              {/* The new-version notice is shown at the very top on every screen (ADR-0106).
                  Placed before the screen so the banner sits above the header. */}
              <AppUpdatePrompt watch={watchForUpdate} />
              <BrowserRouter>
                <App />
              </BrowserRouter>
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </I18nProvider>
    </StrictMode>,
  )
}

/**
 * The under-maintenance / stopped screen (ADR-0080 §10).
 *
 * ⚠ **Rendered in a root separate from the app**, so it can still show even if a lazily
 * loaded component is missing and the app tree crashes. The app screen is only hidden, not
 * removed, so on return everything comes back as it was, including half-entered input. The root
 * is created the first time the app closes (rendered in the language at that time).
 */
function watchOutage(settings: UiSettings) {
  const app = document.getElementById('root')
  let mounted = false
  const sync = () => {
    const closed = currentOutage() !== null
    if (app) app.hidden = closed
    if (!closed || mounted) return
    mounted = true
    const container = document.createElement('div')
    container.id = 'maintenance-root'
    document.body.append(container)
    createRoot(container).render(
      <StrictMode>
        <I18nProvider settings={settings}>
          <MaintenanceGate check={checkService} />
        </I18nProvider>
      </StrictMode>,
    )
  }
  subscribeOutage(sync)
  sync()
}

watchLazyLoadFailures()

// Fetch the default language and theme before rendering. Switching after fetching would flash
// the wrong language/colours on first paint. If the fetch fails, render with the defaults.
void loadUiSettings().then((settings) => {
  watchOutage(settings)
  render(settings)
})
