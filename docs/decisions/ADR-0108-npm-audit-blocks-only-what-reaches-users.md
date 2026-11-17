# ADR-0108: npm の弱点の検査で止めるのは、利用者に届く部品だけにする

- 日付: 2026-11-17
- 状態: 承認（task #1097）

## 文脈

2026-11-17、picomatch（GHSA-fc5q-39xc-vjpf・high・最新版まで全部が対象で直した版なし）がビルドと試験の道具（vite・vitest など）の
中だけで `npm audit --audit-level=high` を落とし、main を赤くした。picomatch は画面のファイルにも本番のサーバーにも入らない。
持ち主の判断で、全リポジトリの npm の検査を「届く部品は止める・道具は知らせるだけ」に揃える。

## 決定

deploy-repo の ADR-0003 に従う。`security-audit.yml` の npm を 2 段にする（`npm audit --audit-level=high --omit=dev` で止め、
道具を含む全部は警告を出すだけで緑のまま）。

道具経由で利用者に届く部品: vite-plugin-pwa が入れる workbox（ページの `workbox-window`＝`virtual:pwa-register`、Service Worker に入る `workbox-core`・`workbox-precaching`・`workbox-routing`）。`dependencies` に書いて止める段に入れた

## 理由

deploy-repo の ADR-0003 を見る。

## 影響

- 画面で新しく使う部品が `devDependencies` の道具経由で届くものなら、`dependencies` にも書く（書かないと止める段から漏れる）
