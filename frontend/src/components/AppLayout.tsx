/**
 * サインイン後の画面の外枠（ヘッダー・ナビゲーション・本文・フッター）。
 *
 * 狭い画面ではサイドバーを開閉式のドロワーにする。開閉状態はここが持ち、
 * ヘッダーのメニューボタン・オーバーレイ・ナビゲーションのリンクから閉じられる。
 * 画面幅の判定は CSS のメディアクエリ側（`index.css`）に任せ、ここでは
 * `data-open` 属性だけを切り替える（広い画面ではサイドバーは常に見えている）。
 *
 * 開いているあいだヘッダーと本文はオーバーレイの下に隠れる。キーボードだけが
 * そこへ到達できると「見えない要素を操作している」状態になるため、開いたら
 * フォーカスをドロワーへ移し、Tab をドロワー内に閉じ込め、閉じたらメニュー
 * ボタンへ戻す（ADR-0011）。
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import { Footer } from './Footer'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), select:not([disabled]), input:not([disabled])'

function focusableIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
}

/** Tab / Shift+Tab の移動先を *container* の中に折り返す。 */
function keepFocusInside(container: HTMLElement, event: KeyboardEvent): void {
  const items = focusableIn(container)
  const first = items.at(0)
  const last = items.at(-1)
  if (first === undefined || last === undefined) return

  const active = document.activeElement
  const outside = !(active instanceof Node) || !container.contains(active)
  const leavingBackwards = event.shiftKey && (active === first || outside)
  const leavingForwards = !event.shiftKey && (active === last || outside)
  if (!leavingBackwards && !leavingForwards) return

  event.preventDefault()
  ;(leavingBackwards ? last : first).focus()
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false)
  const { pathname } = useLocation()
  const toggleRef = useRef<HTMLButtonElement>(null)
  const navRef = useRef<HTMLElement>(null)
  // 「閉じた」ときだけフォーカスを戻すための記録（初期描画では動かさない）。
  const wasOpen = useRef(false)

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

  // 開いているあいだ: 先頭の操作へフォーカスを移し、Esc で閉じ、Tab を閉じ込める。
  useEffect(() => {
    const nav = navRef.current
    if (!navOpen || nav === null) return

    // ドロワーは閉じているあいだ `visibility: hidden`（= フォーカス不可）なので、
    // 開いた状態が描画される次のフレームまで待ってからフォーカスを移す。
    // このフレームを待たずに focus() を呼ぶとブラウザに無視される。
    const frame = requestAnimationFrame(() => {
      focusableIn(nav).at(0)?.focus()
    })

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false)
      else if (event.key === 'Tab') keepFocusInside(nav, event)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [navOpen])

  // 閉じたらメニューボタンへフォーカスを戻す（ドロワーは非表示になり、
  // フォーカスの置き場所が無くなるため）。
  useEffect(() => {
    if (navOpen) {
      wasOpen.current = true
      return
    }
    if (wasOpen.current) {
      wasOpen.current = false
      toggleRef.current?.focus()
    }
  }, [navOpen])

  return (
    <div className="layout">
      <Header navOpen={navOpen} onToggleNav={toggleNav} toggleRef={toggleRef} />
      <div className="layout-body">
        <Sidebar open={navOpen} onClose={closeNav} navRef={navRef} />
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
