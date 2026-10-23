/** 画面右下の簡易トースト通知。 */
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

import { currentOutage } from '../services/maintenance'

interface Toast {
  id: number
  kind: 'success' | 'error'
  text: string
}

interface ToastValue {
  notify: (kind: Toast['kind'], text: string) => void
}

const ToastContext = createContext<ToastValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const notify = useCallback((kind: Toast['kind'], text: string) => {
    // 前段が閉じている間の失敗は、メンテナンスの画面が伝える（ADR-0067）
    if (kind === 'error' && currentOutage()) return
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev, { id, kind, text }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 4000)
  }, [])

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.kind}`}>
            {toast.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used within ToastProvider')
  return value
}
