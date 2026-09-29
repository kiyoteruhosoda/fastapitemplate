# ADR-0048: スマホアプリの最新版は、サーバーが配布面の latest.json を読んで返す

- 日付: 2026-09-29
- 状態: 承認
- 関連: [ADR-0045](ADR-0045-the-app-signs-in-to-assay-directly.md) / [ADR-0047](ADR-0047-notifications-reach-people-by-bell-banner-and-web-push.md) /
  photonest ADR-0079（元の実装）/ 課題 task.nolumia.com #9

## 文脈

flutterbase から作るアプリは Play ストアを通らず、署名済みの APK を配布面（Garage の `artifacts`
バケット。人は share.nolumia.com から取る）に置いて配っている。端末は新しい版が出たことを知る手段を
持たないので、古い版のまま使われ続ける。Web（PWA）には「新しい版があります」の知らせが既にある
（ADR-0035）が、アプリには無い。

photonest は 2026-09-27 にこれを解いた（photonest ADR-0079 / photonestapp ADR-0038）。
課題 #9 で、同じものを雛形にも入れることになった。

## 決定

photonest の `app_release` コンテキストをそのまま持ち上げる。

1. **サーバーが `latest.json` を読み、`GET /api/app-release/latest` でアプリへ返す。** 返すのは版（`1.53.0`）・
   ビルド番号（`356`。`version` の `+` の後ろ）・入手先の URL・焼いた時刻だけ。新旧はアプリが自分の
   ビルド番号と比べて決める。
2. **読むのは S3 の API（boto3）で、鍵は `artifacts` の読み取りだけを持つ専用のもの。** 秘密は値ではなく
   ファイルの場所（`APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE`）で持つ。
3. **認証だけで、scope は要求しない。** 関門は `AppOrWebPrincipalDep`（アプリの assay のトークンで通る）。
4. **読めなくてもエラーにしない。** 設定が無い・配布面が落ちている・書式が崩れている、のどれでも
   `{"latest": null}`。読めなかったときだけ記録に残す。
5. **答えはプロセスの中で 5 分覚える**（読めなかったときは 1 分）。読みに行くのは同時に 1 本だけ。

## 理由

- 配布手順（deploy-repo の `bin/flutter-release.sh`）が既に `latest.json` を書いている。版を別の場所へ
  書き込ませる案（デプロイがサーバーへ版を送る）は、正本が 2 つになる。
- アプリが配布面を直接読む案は、配布面が SSO の後ろにあるので使えない。
- photonest と同じ形にしておけば、どちらで直したものも持ち運べる。

## 影響

- 設定 7 つ（`APP_RELEASE_S3_*` と `APP_RELEASE_DOWNLOAD_URL`）。読む先が 1 つでも空なら何もしない
  ので、アプリを配らない派生は取り込んでも振る舞いが変わらない。
- 依存に `boto3` が増えた。
- ⚠ 比べる番号は `pubspec.yaml` の `version` の `+N`。配布手順は APK をコミット数でビルド番号付けして
  焼くので、`+N` をコミット数と揃えておかないと新旧を取り違える（photonest で指摘済み）。
- アプリ側の知らせ（画面上部のバナー、「閉じる」はその版だけ）は flutterbase が持つ。
