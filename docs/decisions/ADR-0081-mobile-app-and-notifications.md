# ADR-0081: スマホアプリと通知

- 日付: 2026-10-30
- 状態: 承認
- 統合した ADR: 旧 ADR-0045（§1）・旧 ADR-0046（§2）・旧 ADR-0047（§3）・旧 ADR-0048（§4）・旧 ADR-0049（§5）（2026-10-30 に統合。元の文面は git の履歴にある）

## 文脈

deck から「Web と、それを相手にする Android アプリ（flutterbase 型）」の対を作れるようにする（2026-09-27）。
アプリには API を叩くトークン・新しい版の知らせ・通知が要り、派生には管理画面から利用者へ知らせを送る手段が
要る（課題 task.nolumia.com #9・#59）。元の実装は foodexpiryweb の ADR-0047（アプリのログイン）と
photonest の ADR-0079（版の知らせ）。⚠ アプリ向けの機能（§1・§4・§5）は**設定が空なら何もしない**ので、
アプリを配らない派生は取り込んでも振る舞いが変わらない。

## 決定

### §1 Android アプリは assay に直接ログインし、API は assay のアクセストークンを受け取る

SPA はトークンを httpOnly Cookie でしか配らない（ADR-0076 §4）ので、アプリは assay の public client
（PKCE は S256、`offline_access` でリフレッシュトークン）として直接ログインする。assay の redirect URI は
http / https だけ、人のアクセストークンの `aud` は常に `{issuer}/userinfo`、トークンは JWT（RS256、
`typ: at+jwt`）で寿命 300 秒。

1. **戻り先は App Links**（`https://<このホスト>/app/oauth2redirect`）。このアプリが
   `/.well-known/assetlinks.json` を配る（中身は `ANDROID_APP_PACKAGE` と `ANDROID_APP_CERT_FINGERPRINTS`）。
   PC などで開いたときのために案内の画面 S16（`/app/oauth2redirect`）を置く（§2）。
2. **`Authorization: Bearer` の assay のアクセストークンは、次をすべて満たすときだけ受け取る。**
   `iss` が登録済みで有効なテナントの発行者（ADR-0079 §4 決定 2）／その JWKS で署名が検証でき `typ` が
   `at+jwt`／`aud` が `{iss}/userinfo`、期限内／⚠ **`client_id` が `APP_CLIENT_IDS` に載っている**
   （テナントをまたいで 1 つの一覧）／`sub_type` が無い（機械のトークンではない）／停止の記録
   （ADR-0077 §3）に当たらない。
3. **受け付けるのは「アプリから叩いてよい」と宣言したルータだけ。** 印は依存関数 `AppOrWebPrincipalDep`
   （`bounded_contexts/identity_federation/presentation/app_bearer.py`）。雛形では例の `GET /api/app/me`
   と §3 決定 5・§4 決定 3 の口に付ける。派生は自分の業務の口に付ける。
4. 利用者は `(iss, sub)` の結び付きで引き、無ければ SSO のログインと同じ規則で作る・寄せる
   （userinfo を 1 回引く）。**権限は毎回 DB から引く**（assay のトークンには載っていない）。
5. ⚠ **3 つの設定は環境変数だけ**（`APP_CLIENT_IDS` / `ANDROID_APP_PACKAGE` /
   `ANDROID_APP_CERT_FINGERPRINTS`）。管理画面（DB の設定）からは変えられない。
6. ⚠ **どれも空なら何もしない。** assetlinks は 404、assay のトークンは 1 本も受けない
   （`AppOrWebPrincipalDep` を付けた口も Web のトークンだけになる）。

### §2 戻り先の案内ページは、認可コードが付いていれば「タップで開き直す」ボタンを出す

Chrome は、利用者のタップの直後でない移動（ログイン後の自動の戻り）ではほかのアプリを開かず、
アプリの中のタブ（Custom Tab）で案内ページを表示してしまう（2026-09-28、ssotrialapp で確認）。

1. 案内ページ（S16）は、URL に `code` と `state` が付いていれば、**同じ URL をもう一度開くボタン**
   （「アプリに戻ってログインを終える」）を出す。タップで開き直すので、Chrome が App Links どおりアプリへ渡す。

### §3 お知らせは管理画面から送り、ベル・画面上部・端末への通知で届ける

1. **`notification` コンテキストを置く。** お知らせ 1 通は「中身（題・本文・行き先）」「出す場所
   （`bell` / `banner` / `push`、複数可）」「宛先（`all` / `group` / `user` のどれか 1 つ）」で決まる。
   送る権限は `notification:send`。宛先は送る人のテナントの中だけ（ADR-0079 §1）。
2. **送った時点の顔ぶれで配る。** 宛先を展開して `notification_deliveries` に 1 人 1 行書き、既読・閉じたかを
   そこに持つ。あとからグループに入った人には届かず、抜けた人の手元からも消えない。止められた利用者には配らない。
3. **グループを持つ（`user_groups` / `user_group_members`、`group:manage`）。** 権限は持たず「誰と誰か」を
   束ねるだけ。ロールと同じく `shared` に置く。名前の一意はテナントの中（ADR-0079 §2 決定 7）。
4. **端末への通知（`push`）は Web Push（VAPID）と FCM（§5）へ送る。** Web Push の鍵は場所
   （`WEB_PUSH_VAPID_PRIVATE_KEY_FILE`）で持ち、公開鍵は秘密鍵から導く。暗号化と署名は `pywebpush` に
   任せるが、⚠ `py_vapid` の `from_file` は使わず鍵は自分で読む（読めなければ「送れない」と記録に残す）。
   送るのは応答の後（`BackgroundTasks`、自分のセッションを開く）。404 / 410 と答えた購読は外す。
   購読の `endpoint` は sha256 を別の列に持ってそちらを一意にする。
5. **本人の口（`/api/notifications`）はアプリからも叩いてよい**（`AppOrWebPrincipalDep`）。
6. **行き先はこのアプリの中のパス（`/items`）か `http(s)://` だけ。** `javascript:` や `//host` は断る。

### §4 スマホアプリの最新版は、サーバーが配布面の latest.json を読んで返す

アプリは Play ストアを通らず、署名済みの APK を配布面（Garage の `artifacts` バケット。人は
share.nolumia.com から取る）で配る（Web の知らせは ADR-0080 §7）。photonest の `app_release` を持ち上げる。

1. **サーバーが `latest.json` を読み、`GET /api/app-release/latest` で返す。** 返すのは版（`1.53.0`）・
   ビルド番号（`356`。`version` の `+` の後ろ）・入手先の URL・焼いた時刻だけ。新旧はアプリが比べる。
2. **読むのは S3 の API（boto3）で、鍵は `artifacts` の読み取りだけを持つ専用のもの。** 秘密は場所
   （`APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE`）で持つ。
3. **認証だけで、scope は要求しない。** 関門は `AppOrWebPrincipalDep`。
4. **読めなくてもエラーにしない。** 設定が無い・配布面が落ちている・書式が崩れている、のどれでも
   `{"latest": null}`。読めなかったときだけ記録に残す。
5. **答えはプロセスの中で 5 分覚える**（読めなかったときは 1 分）。読みに行くのは同時に 1 本だけ。

### §5 スマホアプリへの通知は FCM（HTTP v1）で送り、鍵はファイルの場所で持つ

1. **`push` は Web Push と FCM のうち送れる設定のほうへ送り、どちらか 1 つでも送れれば管理画面で選べる**
   （`PushChannels`）。宛先・本文は §3 のまま。
2. **アプリの登録トークンは `app_device_tokens` に持つ。** アプリはサインインのたび・起動のたびに
   `POST /api/notifications/device/register`（`updated_at` も更新）し、サインアウトで `…/unregister` する。
   同じ端末で別の人がサインインし直したら後の人の端末になる。`UNREGISTERED`（404）のトークンは外す。
3. **FCM HTTP v1 を直接叩く。** `firebase-admin` は入れず、サービスアカウントの鍵で JWT を署名して
   （`pyjwt`）Google の OAuth でアクセストークンに換え（1 時間。プロセスで覚える）、`messages:send` へ
   POST する（`httpx`）。
4. **鍵は場所で持つ**（`FCM_SERVICE_ACCOUNT_FILE`。Firebase のコンソールで作った JSON をそのまま置く）。
   空なら FCM へは送らず、アプリの登録も断る（`device_push_not_configured`）。
5. **中身は `notification`（題・本文）＋ `data`（`notification_id`・`url`）。** アプリは押されたら `url` を開き、
   ベルを取り直す。

## 理由

### §1

- **App Links**（RFC 8252 の「主張した https の戻り先」）: 独自スキームは他のアプリが同じスキームを
  名乗って認可コードを横取りできる。
- **`aud` ではなく `client_id` で決める**: 人のトークンに宛名が載らない。assay の ADR-0033 も業務の認可は
  リソースサーバが `client_id` / `sub` で決めるとしている。
- **設定を画面から変えさせない**: `APP_CLIENT_IDS` を誤って足すと別のクライアント宛てのトークンが通り、
  assetlinks を書き換えると別のアプリに認可コードを渡す宣言になる。値は配る人（deploy-repo・deck）が決める。
- **口を宣言したルータに絞る**: 管理・アカウント・トークンの出し直しまで開けると、盗まれたアプリの
  トークンで入れる範囲が広がる。

### §2

- 開くのはいま開いている URL そのもので、認可コードは PKCE でアプリしか引き換えられない。移動を起こす
  のは assay と Chrome でアプリ側では直せず、戻り先の画面はこちらが持っている。
- 採らなかった案: Chrome の Auth Tab へ移る——正しい方向だが AppAuth / flutter_appauth の対応が要る。別に検討する。

### §3

- **送った時点で配る**: 誰に送り何人が読んだかを後から数えられる。読むたびに展開すると、グループを
  編集した時点で過去の配信の意味が変わる。想定の規模（数十〜数百人）なら行数は問題にならない。
- **グループを新設**: ロールは「何ができるか」で、束ねるためにロールを増やすと権限の表が汚れる
  （2026-09-29 に利用者が選んだ）。
- **`from_file` を使わない**: ファイルが無いと**黙って新しい鍵を作って書き出し**、配った公開鍵と違う鍵で
  署名してすべての購読が静かに届かなくなる。
- **`endpoint` に直接一意制約を張らない**: 数百文字あり MariaDB の索引の長さを超える。

### §4

- 配布手順（deploy-repo の `bin/flutter-release.sh`）が既に `latest.json` を書いている。デプロイが版を
  サーバーへ送る案は正本が 2 つになり、アプリが配布面を直接読む案は配布面が SSO の後ろにあるので使えない。
- photonest と同じ形なら、どちらで直したものも持ち運べる。

### §5

- **HTTP v1 を直接**: 既にある `pyjwt` と `httpx` で足り、`firebase-admin` は `google-cloud-*` 一式を連れてくる。
  旧 API（サーバーキー）は廃止済み。
- **Web Push の購読と表を分ける**: 中身（鍵の組 と 1 本のトークン）も、消える合図（410 と
  `UNREGISTERED`）も違う。
- **登録は毎回**: トークンは端末側の都合で入れ替わる。毎回送れば最後に届いたものが正になる。

## 影響

### §1

- 3 つの設定は CLAUDE.md の「設定は 3 ファイル」の**例外**で、既定値と管理画面の定義には載せない。
- ⚠ **assay の名簿から外しても、アプリのリフレッシュトークンは止まらない**（assay の判定は認可コードの
  発行時だけ）。すぐ止めるには assay で利用者を止めるか、この口座を無効にする。
- ⚠ **30 日ごとに再ログインになる**（assay のリフレッシュトークンは使っても延びない）。
- 初回の userinfo のとき assay が落ちていると、その人の初回だけ失敗する。
- foodexpiryweb は同じ実装を先に持つ。取り込むときは向こうの ADR-0047 と重なる。

### §2

- タブの中で止まっても、利用者が 1 回タップすればログインが終わる。

### §3

- 画面: ヘッダーにベル、本文の上に上部の知らせ、プロフィールに「この端末への通知」、管理に
  「グループ管理」（S17）と「お知らせの配信」（S18）。
- 設定 `WEB_PUSH_VAPID_PRIVATE_KEY_FILE` / `WEB_PUSH_SUBJECT`。どちらかが空なら Web Push へは送らない
  （ベルと上部は動く）。鍵の作り方は `docs/OPERATIONS.md`。⚠ 鍵を替えると既存の購読はすべて届かなくなる。
- Service Worker に `public/push-sw.js` を `importScripts` で足した（生成物には手を入れない）。
- 依存に `pywebpush`（`py-vapid` / `http-ece` / `requests` / `aiohttp` が付いてくる）。
- 利用者を消すとき、グループの所属を明示的に外す（SQLite は外部キーの CASCADE を既定で効かせない）。

### §4

- 設定 7 つ（`APP_RELEASE_S3_*` と `APP_RELEASE_DOWNLOAD_URL`）。1 つでも空なら何もしない。依存に `boto3`。
- ⚠ 比べる番号は `pubspec.yaml` の `version` の `+N`。配布手順は APK をコミット数でビルド番号付けするので、
  `+N` をコミット数と揃えないと新旧を取り違える。
- アプリ側の知らせ（画面上部のバナー、「閉じる」はその版だけ）は flutterbase が持つ。

### §5

- 設定 `FCM_SERVICE_ACCOUNT_FILE`（既定は空）。マイグレーション `0010_app_device_tokens`。
- ⚠ **Firebase のプロジェクトは人が作る**（コンソールで Android アプリを登録し、サービスアカウントの鍵を
  発行する）。手順は `docs/OPERATIONS.md`、アプリに渡す値（`--dart-define`）は flutterbase の文書。
- ⚠ 通知の中身は Google を経由する。お知らせに秘密を書かない（FCM の `notification` は Google から読める）。
