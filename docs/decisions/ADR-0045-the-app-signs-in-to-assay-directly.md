# ADR-0045: Android アプリは assay に直接ログインし、API は assay のアクセストークンを受け取る（任意の機能）

- 日付: 2026-09-27
- 状態: 承認
- 関連: ADR-0028（`Authorization` ヘッダーも受け付ける）、ADR-0036（停止の通知）、ADR-0041（アクセストークンの検証）、
  foodexpiryweb の ADR-0047（この ADR の元）、nolumiadeck の ADR-0114（画面からプロジェクトを作る）、
  assay の ADR-0033 / ADR-0042 / ADR-0054 / ADR-0056

## 文脈

deck の画面から「Web と、それを相手にする Android アプリ（flutterbase 型）」の対を作れるように
する（2026-09-27、持ち主の依頼）。Android アプリは API を叩くためのトークンが要るが、この SPA は
トークンを httpOnly Cookie でしか配らない（ADR-0028）ので、**アプリがトークンを手に入れる入口が無い**。

foodexpiryweb（この雛形の派生）が同じ問題を 2026-09-17 に解いている（同アプリの ADR-0047）。
アプリは assay の public client として直接ログインし、API は assay のアクセストークンを
`client_id` で見分けて受け取る。これを**雛形の任意の機能**として持ち上げる。

assay の前提（2026-09-17 に確かめたもの）:

- redirect URI は http / https しか登録できない（独自スキームは 400）
- 人のログインで出るアクセストークンの `aud` は常に `{issuer}/userinfo`（宛名を載せられない）
- public client ＋ PKCE（S256 必須）、`offline_access` でリフレッシュトークン、
  アクセストークンは JWT（RS256、`typ: at+jwt`）で寿命 300 秒

## 決定

1. **戻り先は App Links**（`https://<このホスト>/app/oauth2redirect`）。このアプリが
   `/.well-known/assetlinks.json` を配る（中身は `ANDROID_APP_PACKAGE` と `ANDROID_APP_CERT_FINGERPRINTS`）。
   戻り先を PC などで開いたときのために、案内の画面 S16（`/app/oauth2redirect`）を置く。
2. **API は `Authorization: Bearer` で来た assay のアクセストークンを、次をすべて満たすときだけ受け取る。**
   署名が assay の JWKS で検証でき `typ` が `at+jwt`／`iss` が `OIDC_ISSUER`、`aud` が
   `{OIDC_ISSUER}/userinfo`、期限内／⚠ **`client_id` が `APP_CLIENT_IDS` に載っている**／
   `sub_type` が無い（機械のトークンではない）／停止の記録（ADR-0036）に当たらない。
3. **受け付けるのは「アプリから叩いてよい」と宣言したルータだけ。** その印は依存関数
   `AppOrWebPrincipalDep`（`bounded_contexts/identity_federation/presentation/app_bearer.py`）。
   雛形では例として `GET /api/app/me` の 1 本だけに付ける。派生は自分の業務の口に付ける。
4. 利用者は `(iss, sub)` の結び付きで引き、無ければ SSO のログインと同じ規則で作る・寄せる
   （userinfo を 1 回引く）。**権限は毎回 DB から引く**（assay のトークンには載っていない）。
5. ⚠ **3 つの設定は環境変数だけ**（`APP_CLIENT_IDS` / `ANDROID_APP_PACKAGE` /
   `ANDROID_APP_CERT_FINGERPRINTS`）。管理画面（DB の設定）からは変えられない。
6. ⚠ **どれも空なら何もしない。** assetlinks は 404、assay のトークンは 1 本も受けない
   （`AppOrWebPrincipalDep` を付けた口も Web のトークンだけになる）。既存の派生に影響しない。

## 理由

- **App Links は Android での推奨の形**（RFC 8252 の「主張した https の戻り先」）。独自スキームは
  他のアプリが同じスキームを名乗って認可コードを横取りできる。
- **`aud` の代わりに `client_id` で受け取りを決める。** 人のトークンに宛名が載らないので、
  `aud` では「どのアプリ宛てか」が分からない。assay の ADR-0033 も「業務の認可はリソースサーバが
  `client_id` / `sub` で決める」としている。
- **設定を画面から変えさせない。** `APP_CLIENT_IDS` を誤って足すと、別のクライアント宛ての
  トークンがこのアプリの API を通る。assetlinks を書き換えられると、別のアプリに認可コードを渡す
  宣言になる。載せる値は配る人（deploy-repo の宣言、deck の作成）が決める。
- **受け付ける口を宣言したルータに絞る。** 管理・アカウント・トークンの出し直しまで開けると、
  盗まれたアプリのトークンで入れる範囲がむやみに広がる。
- **雛形では既定で閉じる。** 設定が空なら何も変わらないので、この機能を使わない派生は
  取り込んでも振る舞いが変わらない。

## 影響

- 設定が 3 つ増える（環境変数のみ）。CLAUDE.md の「設定は 3 ファイル」の**例外**で、
  既定値と管理画面の定義には載せない（決定 5）。
- ⚠ **assay の名簿から外しても、アプリのリフレッシュトークンは止まらない**（assay の判定は
  認可コードの発行時だけ）。すぐ止めたいときは assay で利用者を止めるか、この口座を無効にする。
- ⚠ **30 日ごとに再ログインになる**（assay のリフレッシュトークンは使っても延びない）。
- 初めてアプリから来た利用者には userinfo を 1 回引く。assay が落ちていると、その人の初回だけ失敗する。
- foodexpiryweb は同じ実装を先に持っている。取り込むときは、向こうの ADR-0047 と重なる。
