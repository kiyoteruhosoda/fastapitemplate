/**
 * サインイン後の画面の外枠（ヘッダー・ナビゲーション・本文・フッター）。
 *
 * 狭い画面ではサイドバーを開閉式のドロワーにする。開閉状態はここが持ち、
 * ヘッダーのメニューボタン・オーバーレイ・ナビゲーションのリンクから閉じられる。
 * 画面幅の判定は CSS のメディアクエリ側（`index.css`）に任せ、ここでは
 * `data-open` 属性だけを切り替える（広い画面ではサイドバーは常に見えている）。
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import { Footer } from './Footer'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

export function AppLayout({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false)
  const { pathname } = useLocation()

  const closeNav = useCallback(() => {
    setNavOpen(false)
  }, [])

  const toggleNav = useCallback(() => {
    setNavOpen((open) => !open)
  }, [])

  // 画面が切り替わったらドロワーを閉じる（ページ内のボタンによる遷移も含む）。
  useEffect(() => {
    setNavOpen(false)
  }, [pathname])

  // Esc で閉じる（外部キーボードを付けた端末・広い画面から縮めた場合のため）。
  useEffect(() => {
    if (!navOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [navOpen])

  return (
    <div className="layout">
      <Header navOpen={navOpen} onToggleNav={toggleNav} />
      <div className="layout-body">
        <Sidebar open={navOpen} onClose={closeNav} />
        {/* ドロワーの外側をタップして閉じるための覆い。読み上げ・キーボードからは
            ドロワー内の閉じるボタンと Esc で閉じられるため、支援技術には出さない。 */}
        {navOpen && (
          <div
            className="nav-overlay"
            data-testid="nav-overlay"
            aria-hidden="true"
            onClick={closeNav}
          />
        )}
        <main className="content">{children}</main>
      </div>
      <Footer />
    </div>
  )
}
