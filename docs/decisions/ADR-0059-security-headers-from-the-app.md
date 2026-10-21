# ADR-0059: 守りのヘッダはアプリ自身が付ける

- 日付: 2026-10-21
- 状態: 承認

## 文脈

画面と API の応答に、CSP・`X-Frame-Options`・`Strict-Transport-Security`・`X-Content-Type-Options`・
`Referrer-Policy` のどれも付いていなかった。他のサイトが画面を透明な枠で重ねて押させる攻撃
（クリックジャッキング）を防げず、万一 XSS が入ったときに広がる範囲も大きい
（2026-10-21 の脆弱性確認、task #576）。

前段の nginx の設定は、アプリごとに deploy-repo の `k8s/<app>-<env>/20-config.yaml` へ写す。
確認では、試し場の写しが雛形（`deploy/k8s/20-config.yaml`）の `/metrics` の閉じ方すら写していなかった。

## 決定

`presentation/fastapi/middleware/security_headers.py` の `SecurityHeadersMiddleware` が、全部の応答に付ける
（いちばん外側に置き、CSRF で断った応答にも付ける）。

- `Content-Security-Policy: default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`
- `X-Frame-Options: DENY`・`X-Content-Type-Options: nosniff`・`Referrer-Policy: no-referrer`
- `Strict-Transport-Security: max-age=31536000` は `SESSION_COOKIE_SECURE` が有効なとき（https で配るとき）だけ
- `/docs`・`/redoc` は外の CDN からスクリプトを読むので、CSP だけ付けない
- 個別の応答が自分で付けたヘッダは上書きしない

## 理由

- アプリ自身が付ければ、雛形から起こしたアプリには写し忘れなく入る。nginx に書く形は写しが増えるたびに抜ける。
- 画面はインラインのスクリプトも外部の資源も使っていないので、`'self'` で縛れる。例外は二要素の QR コード
  （`data:` の画像）だけ。
- `Referrer-Policy: no-referrer` は、再設定のリンク（`?token=`）を開いた画面から URL を外へ漏らさないため。
- 採らなかった案: Cloudflare の設定で付ける。アプリの外の設定で、派生のアプリへ写らない。

## 影響

- 画面に外の資源（CDN のフォント・解析のスクリプトなど）を足すときは、CSP を広げる必要がある。広げずに
  足すと読み込みが断られる（E2E の見張りが CSP の違反で落とす）。
- `/docs`・`/openapi.json` は今までどおり外から見える（API の仕様は Swagger が唯一の出所という決めごと
  のため、閉じるかは別に決める）。
