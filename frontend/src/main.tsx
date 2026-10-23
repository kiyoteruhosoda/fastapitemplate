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
              {/* 新しい版の知らせは画面に関わらず出す（ADR-0035）。 */}
              <AppUpdatePrompt watch={watchForUpdate} />
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </I18nProvider>
    </StrictMode>,
  )
}

/**
 * メンテナンス中・停止中の画面（ADR-0067）。
 *
 * ⚠ **アプリとは別の root に描く。** 遅れて読み込む部品が欠けてアプリの木が落ちても
 * 出せるようにするため。アプリの画面は消さずに隠すだけなので、戻ったときは入力の途中も
 * 含めてそのまま戻る。root は初めて閉じたときに作る（そのときの言語で描く）。
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

// 言語・テーマの既定値は描画前に取得する。取得後に切り替えると、初回表示で
// 一瞬だけ違う言語・配色が見えてしまう。取得に失敗しても既定値で描画する。
void loadUiSettings().then((settings) => {
  watchOutage(settings)
  render(settings)
})
