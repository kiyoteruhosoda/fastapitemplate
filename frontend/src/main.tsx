import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { ToastProvider } from './components/ToastNotification'
import { I18nProvider } from './i18n'
import './index.css'
import { loadUiSettings, type UiSettings } from './services/uiSettings'
import { AuthProvider } from './store/AuthContext'
import { ThemeProvider } from './theme'

function render(settings: UiSettings) {
  const container = document.getElementById('root')
  if (!container) throw new Error('#root が index.html に見つかりません')

  createRoot(container).render(
    <StrictMode>
      <I18nProvider settings={settings}>
        <ThemeProvider settings={settings}>
          <AuthProvider>
            <ToastProvider>
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

// 言語・テーマの既定値は描画前に取得する。取得後に切り替えると、初回表示で
// 一瞬だけ違う言語・配色が見えてしまう。取得に失敗しても既定値で描画する。
void loadUiSettings().then(render)
