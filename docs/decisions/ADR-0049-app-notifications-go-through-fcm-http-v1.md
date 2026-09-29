# ADR-0049: スマホアプリへの通知は FCM（HTTP v1）で送り、鍵はファイルの場所で持つ

- 日付: 2026-09-29
- 状態: 承認
- 関連: [ADR-0045](ADR-0045-the-app-signs-in-to-assay-directly.md) / [ADR-0047](ADR-0047-notifications-reach-people-by-bell-banner-and-web-push.md) /
  flutterbase ADR-0010 / 課題 task.nolumia.com #59

## 文脈

ADR-0047 でお知らせの「端末への通知」を作ったが、届け先は Web Push（ブラウザ・PWA）だけだった。
flutterbase から作った Android アプリは、開いていないとベルにも気付けない。Android のアプリへ
通知を届ける経路は、事実上 Firebase Cloud Messaging（FCM）しかない。

## 決定

1. **「端末への通知」（`push`）は Web Push と FCM の両方へ送る。** 送れる設定になっているほうだけへ
   送り、どちらか 1 つでも送れれば管理画面で選べる（`PushChannels`）。宛先・本文は ADR-0047 のまま。
2. **アプリの登録トークンは `app_device_tokens` に持つ。** アプリはサインインのたび・起動のたびに
   `POST /api/notifications/device/register` し、サインアウトで `…/unregister` する。同じ端末で別の人が
   サインインし直したら、後の人の端末になる。FCM が `UNREGISTERED`（404）と答えたトークンは外す。
3. **送るのは FCM HTTP v1 を直接叩く。** `firebase-admin` は入れず、サービスアカウントの鍵で JWT を
   署名して（`pyjwt`）Google の OAuth でアクセストークンに換え（1 時間。プロセスで覚える）、
   `messages:send` へ POST する（`httpx`）。
4. **鍵は値ではなく場所で持つ**（`FCM_SERVICE_ACCOUNT_FILE`。Firebase のコンソールで作った JSON を
   そのまま置く）。空なら FCM へは送らず、アプリの登録も断る（`device_push_not_configured`）。
5. **中身は `notification`（題・本文）＋ `data`（`notification_id`・`url`）。** アプリは通知を押されたら
   `url` を開き、ベルを取り直す。

## 理由

- **HTTP v1 を直接（決定 3）**: やることは「署名して換える」「POST する」の 2 つで、既にある
  `pyjwt` と `httpx` で足りる。`firebase-admin` は `google-cloud-*` 一式を連れてきて、テンプレートの
  依存が大きく増える。旧 API（サーバーキー）は廃止済みで使えない。
- **トークンを Web Push の購読と分ける（決定 2）**: 中身（鍵の組 と 1 本のトークン）も、消える合図
  （410 と `UNREGISTERED`）も違う。1 つの表に詰めると列の半分が常に空になる。
- **登録は毎回（決定 2）**: FCM のトークンは端末側の都合で入れ替わる。「変わったときだけ」送る作りは
  取りこぼすと気付けない。毎回送れば、最後に届いたものが正になる（`updated_at` も更新する）。

## 影響

- 設定 1 つ（`FCM_SERVICE_ACCOUNT_FILE`）。空なら何もしない（既定）ので、アプリを配らない派生は
  取り込んでも振る舞いが変わらない。
- マイグレーション `0010_app_device_tokens`。
- ⚠ **Firebase のプロジェクトは人が作る**（コンソールで Android アプリを登録し、サービスアカウントの鍵を
  発行する）。手順は `docs/OPERATIONS.md`。アプリ側に渡す値（`--dart-define`）は flutterbase の文書。
- 通知の中身は Google を経由する。お知らせに秘密を書かない（Web Push は暗号化されるが FCM の
  `notification` は Google から読める）。
