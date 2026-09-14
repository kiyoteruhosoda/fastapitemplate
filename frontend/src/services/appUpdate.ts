/**
 * 新しい版が焼かれたことの検出（Service Worker の更新）。
 *
 * SPA は画面を描き替えるだけで再読み込みしないので、**デプロイしても開きっぱなしの
 * 端末は古い版のまま動き続ける**。Service Worker は新しい版を裏で取ってくるが、
 * 既に読み込まれた JavaScript を差し替える手段は持たない（差し替わるのは次の
 * 読み込みから）。そこで「新しい版が待機している」ことだけを画面へ伝え、
 * 入れ替え（＝再読み込み）は利用者が押したときに行う（ADR-0035）。
 *
 * ⚠ 待つだけでは気付けない。ブラウザが Service Worker の更新を確認するのは
 * **ページ遷移のとき**で、SPA の画面切り替えはページ遷移ではない。ここで
 * 定期的に・タブが手前へ戻ったときに確認を起こす。
 */
import { registerSW } from 'virtual:pwa-register'

/** 更新を確認する間隔。 */
export const UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000

/** 確認どうしの最短間隔（タブの出入りを繰り返しても頻繁には叩かない）。 */
const MIN_CHECK_GAP_MS = 60 * 1000

/**
 * 押してから、こちらの都合で再読み込みするまでの猶予。
 *
 * 通常は新しい Service Worker が制御を引き継いだ合図（`controllerchange`）で
 * workbox が再読み込みする。⚠ **まだ Service Worker に制御されていない画面**
 * ——この版を初めて開いた（登録された直後の）タブ——では合図が来ないので、
 * 押したのに何も起きないことになる。その取りこぼしを拾う。
 */
const RELOAD_FALLBACK_MS = 2000

/** 新しい版へ入れ替える（現在の画面を再読み込みする）。 */
export type ApplyUpdate = () => void

/** 新しい版が待機したときに呼ばれる。 */
export type UpdateReadyListener = (apply: ApplyUpdate) => void

/** 待機している新しい版を見張る。 */
export type WatchForUpdate = (onUpdateReady: UpdateReadyListener) => void

function scheduleChecks(registration: ServiceWorkerRegistration): void {
  let checkedAt = 0

  const check = (): void => {
    const now = Date.now()
    // 取得中・オフライン・直前に確認済みのときは起こさない。
    if (registration.installing || !navigator.onLine || now - checkedAt < MIN_CHECK_GAP_MS) return
    checkedAt = now
    void registration.update().catch(() => {
      // 確認できなくても画面には出さない（次の機会に取り直す）。
    })
  }

  setInterval(check, UPDATE_CHECK_INTERVAL_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') check()
  })
}

export const watchForUpdate: WatchForUpdate = (onUpdateReady) => {
  const updateSW = registerSW({
    onNeedRefresh() {
      onUpdateReady(() => {
        // 待機している Service Worker に skipWaiting を送る。再読み込みは
        // 制御が移った合図を受けて workbox が行う。
        void updateSW()
        window.setTimeout(() => {
          window.location.reload()
        }, RELOAD_FALLBACK_MS)
      })
    },
    onRegisteredSW(_swUrl, registration) {
      if (registration) scheduleChecks(registration)
    },
  })
}
