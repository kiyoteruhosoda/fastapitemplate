# ADR-0028: トークンは httpOnly Cookie だけに置き、応答本文で配らない

- 日付: 2026-09-04
- 状態: 提案

## 文脈

バックエンドは access トークンを **httpOnly Cookie** に載せている
（`set_access_token_cookie`）。ところがフロントエンドは同じトークンを
**localStorage にも保存し**、`Authorization` ヘッダーで送っている
（`frontend/src/services/api.ts`）。httpOnly にした意味が localStorage 側で
打ち消されており、二重管理でもある。

**refresh トークンも localStorage にある。** これは長命で、しかも発行済みトークンを
失効させる手段が無い（T5 が未着手）。つまり **XSS 1 発の被害が「セッション 1 つ」では
なく「期限切れまで止められない長期資格情報」**になる。

課題を「Cookie 一本か、ヘッダー一本か」の二択として書いていたが、**この立て方が
間違っていた**。危ないのは API が `Authorization` ヘッダーを受け付けることではなく、
**JS から読める場所にトークンを置くこと**である。ヘッダーを受け付ける仕様そのものは、
Swagger UI・curl・CI から叩くために価値がある。決めるべきは「**SPA がどこに持つか**」
の一点になる。

SSO を足した（ADR-0025）ことでトークンを発行する経路は 3 本になった
（パスワード / パスキー / SSO の券の引き換え）。**3 本とも既に Cookie を載せている**
ので、Cookie 側の配線は揃っている。

## 決定

**SPA はトークンを持たない。** access / refresh とも httpOnly Cookie で運ぶ。

1. **`localStorage` からトークンを消す。** `setTokens` / `hasTokens` を廃し、
   ログイン済みかどうかは `GET /api/auth/me` の成否で決める。
2. **refresh トークンも httpOnly Cookie にする**（`SameSite=Lax`、経路は
   `/api/auth/refresh` に絞る）。`POST /api/auth/refresh` は本文にトークンを取らない。
3. **トークンを応答本文で配らない。** ログイン・更新・SSO の引き換えは、いずれも
   Cookie を載せるだけにする（`TokenResponse` から `access_token` /
   `refresh_token` を落とす）。
4. **API は `Authorization` ヘッダーも受け付け続ける。** Cookie が無ければヘッダーを
   見る、の順。既にトークンを持っている呼び出し元（他アプリ・CI）のため。
5. **CSRF は `SameSite=Lax` + 二重送信トークン。** 更新系（POST / PUT / PATCH /
   DELETE）にだけ必須とし、読み取りには求めない。

## 理由

- **応答本文に載せたままでは httpOnly が意味を持たない。** これが決め手である。
  Cookie は自動で送られるので、XSS は `POST /api/auth/refresh` を叩くだけでよく、
  **新しい access トークンを応答本文から読める**。「Cookie に入れたが本文でも返す」は
  攻撃者にとって localStorage と変わらない。持ち出せなくするには、**本文から消す**
  ところまで行く必要がある。
- **ヘッダーを塞ぐ必要は無い。** XSS が奪うのは「保管された値」であって「ヘッダーを
  送る能力」ではない。ヘッダーを受け付け続けても、SPA が値を持たなければ盗る対象が
  無い。Swagger UI は同一オリジンなのでブラウザの Cookie がそのまま付き、
  curl も CI も Cookie を扱える。**受け付ける口を減らすより、配る場所を減らす**ほうが
  効く。
- **refresh を先に守る。** access は寿命が短いが refresh は長い。失効の手段が無い
  （T5）以上、盗られたときの差が大きい。**T12 と T5 は独立した話ではない** ——
  失効が入るまでの間、持ち出させないことが唯一の防御になる。
- **`SameSite=Lax` だけでは足りない。** Lax は別サイトからの POST を止めるが、
  同一サイト扱いになる相手（サブドメインを取られた場合など）は止めない。更新系に
  トークンを 1 つ足す費用は小さい。読み取りにまで求めないのは、costs が UI 全体に
  及ぶわりに守るものが無いため（読み取りの CSRF は結果を攻撃者が読めない）。
- **いま決めるのが安い。** 発行経路は既に 3 本とも Cookie を載せており、消す側
  （localStorage）だけが残っている。経路がこれ以上増えてからやると差分が広がる。

## 影響

- **API の互換が壊れる。** `TokenResponse` から `access_token` / `refresh_token` が
  消える（SSO の `SsoSessionResponse` も `redirect_to` だけになる）。**この
  テンプレートから作った既存のアプリは、フロントエンドを同じ形に直すまで動かない。**
- **Swagger UI の Authorize ボタンは使わなくなる。** ブラウザでログインしていれば
  Cookie が付くのでそのまま叩ける。手元で `curl` を使うときは `-c` / `-b` で
  Cookie を扱う（`docs/OPERATIONS.md` に手順が要る）。
- **CSRF トークンの配り方を決める必要がある。** Cookie に出して同送させる（二重送信）
  か、`GET /api/auth/me` の応答に載せるか。二重送信のほうが状態を持たずに済む。
- **ログアウトの意味が変わらない点に注意。** Cookie を落としてもサーバー側の JWT は
  有効なままで、これは今も同じ（失効は T5）。今回の変更で良くなるのは
  「**持ち出されなくなる**」ことであって、「止められる」ことではない。
- `frontend/README.md` の記述（トークンの持ち方）と `docs/ARCHITECTURE.md` の
  認証の節を更新する。
- ADR-0002（JWT による認証）の方式そのものは変えない。置き場所だけの決定である。
