/**
 * 前段（edge）が「閉じている」と答えたことの受け取り（ADR-0080 §10）。
 *
 * edge は計画メンテナンスの宣言があるホストへの要求すべてに 503 を返し、ブラウザ以外
 * （`fetch` の既定の Accept）には JSON を返す:
 *
 *   {"error": "service_unavailable", "reason": "maintenance", "until": "…Z",
 *    "message": "<理由>", "title": "<見出し>", "body": "<本文>"}
 *
 * 上流（このアプリ）が居ないだけのときは `reason: "stopped"`。
 *
 * ⚠ **画面の移動では edge のメンテナンス画面は見えない。** Service Worker が手元の
 * index.html を返すため（`navigateFallback`）。そこで API の応答でアプリ内の画面へ
 * 切り替える。ここはその状態（閉じているか・何と言われたか）だけを持つ。
 *
 * ⚠ アプリ自身のエラーは `{"detail": {"error": …}}` で、上の形（最上位に `error` と
 * `reason`）とは混ざらない。上の形でない 503 は「閉じている」とは扱わない。
 */

export type OutageReason = 'maintenance' | 'stopped'

/** edge が閉じていると答えた内容。文言の無い欄は null（古い edge には title・body が無い）。 */
export interface Outage {
  reason: OutageReason
  title: string | null
  body: string | null
  /** 閉じた理由（宣言の `--reason`）。 */
  message: string | null
  /** 戻りの見込み（ISO 8601、UTC）。 */
  until: string | null
}

/** 確かめ直しの結果。`unknown` は届かない・別の失敗で、閉じているとも開いたとも言えない。 */
export type ServiceState = 'open' | 'closed' | 'unknown'

const SERVICE_UNAVAILABLE = 503

/**
 * 確かめ直しに叩く口。認証が要らず軽い、起動時にも読む画面の設定。
 * ⚠ 道は何でもよい（edge は宣言のあるホストの道すべてを閉じる）。
 */
export const PROBE_PATH = '/api/ui/settings'

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function isOutageReason(value: unknown): value is OutageReason {
  return value === 'maintenance' || value === 'stopped'
}

/** 503 の応答の本文から、edge が閉じていると答えたものだけを取り出す。 */
export function outageFrom(status: number, payload: unknown): Outage | null {
  if (status !== SERVICE_UNAVAILABLE || !payload || typeof payload !== 'object') return null
  const body = payload as Record<string, unknown>
  if (body.error !== 'service_unavailable' || !isOutageReason(body.reason)) return null
  return {
    reason: body.reason,
    title: text(body.title),
    body: text(body.body),
    message: text(body.message),
    until: text(body.until),
  }
}

type Listener = () => void

let current: Outage | null = null
/**
 * 遅れて読み込む部品の失敗から閉じたと分かったとき、開いたら呼ぶ読み込み直し
 * （欠けた部品は読み込み直さないと戻らない）。
 */
let reloadOnReopen: (() => void) | null = null
const listeners = new Set<Listener>()

function sameOutage(a: Outage | null, b: Outage | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function publish(next: Outage | null): void {
  if (sameOutage(current, next)) return
  current = next
  listeners.forEach((listener) => {
    listener()
  })
}

/** いま閉じているか（閉じていなければ null）。 */
export function currentOutage(): Outage | null {
  return current
}

export function subscribeOutage(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** edge が閉じていると答えた。 */
export function reportOutage(outage: Outage): void {
  publish(outage)
}

/** 開いたと分かった。部品が欠けたまま描かれている画面なら読み込み直す。 */
export function reportReopened(): void {
  const wasClosed = current !== null
  publish(null)
  const reload = reloadOnReopen
  if (wasClosed && reload) {
    reloadOnReopen = null
    reload()
  }
}

/**
 * 閉じているかを確かめ直す。答えは状態へ反映する（届かないときは変えない）。
 *
 * ⚠ 保存された答えを使わない（edge も no-store を付けるが、念のため）。
 */
export async function checkService(): Promise<ServiceState> {
  let response: Response
  try {
    response = await fetch(PROBE_PATH, { cache: 'no-store', credentials: 'same-origin' })
  } catch {
    return 'unknown'
  }
  if (response.ok) {
    reportReopened()
    return 'open'
  }
  const outage = outageFrom(response.status, await response.json().catch(() => null))
  if (!outage) return 'unknown'
  reportOutage(outage)
  return 'closed'
}

/**
 * 遅れて読み込む部品（動的 import の JS・CSS）が読めなかったとき、閉じているかを確かめる。
 *
 * edge は JS・CSS にも 503（JSON）を返すので、閉じている間に画面を移ると部品が欠ける。
 * 閉じているならメンテナンスの画面を出し、戻ったら読み込み直す。**ただの失敗なら
 * 何もしない**（エラーは今までどおり投げられる。`preventDefault` しない）。
 *
 * Vite は読み込みの失敗を `vite:preloadError` で知らせる。
 */
export function watchLazyLoadFailures(
  target: Window = window,
  reload: () => void = () => {
    window.location.reload()
  },
): () => void {
  const onFailure = (): void => {
    void checkService().then((state) => {
      if (state === 'closed') reloadOnReopen = reload
    })
  }
  target.addEventListener('vite:preloadError', onFailure)
  return () => {
    target.removeEventListener('vite:preloadError', onFailure)
  }
}

/** 試験用: 状態を初めに戻す。 */
export function resetOutageForTests(): void {
  current = null
  reloadOnReopen = null
  listeners.clear()
}
