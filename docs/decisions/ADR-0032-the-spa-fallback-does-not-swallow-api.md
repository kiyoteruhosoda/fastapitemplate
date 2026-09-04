# ADR-0032: SPA の受け皿は `/api/` を飲み込まない

- 日付: 2026-09-05
- 状態: 承認

## 文脈

`presentation/fastapi/routers/spa.py` は React Router の履歴モードのために
`GET /{path:path}` を catch-all で受け、実在しないパスへ `index.html` を返す。
このルーターは**フロントエンドを焼いてあるときだけ**（`frontend/dist` があるときだけ）
マウントされる。

結果、**存在しない API のパスが `200 OK` + `index.html` を返していた。**

```
GET /api/nonexistent  →  200, <!doctype html>...   （dist あり ＝ 本番）
GET /api/nonexistent  →  404, {"detail":"Not Found"} （dist なし ＝ 手元と CI）
```

厄介なのは**本番でだけ起きる**こと。Backend の CI はフロントエンドを焼かないので、
`tests/integration/api/test_request_logging.py` が `/api/nonexistent` → 404 を
確かめていても、その検証は**受け皿の載っていない世界**でしか働いていなかった。

## 決定

**受け皿に落ちた `/api/` 配下は 404 を返す。** 応答の形は `dist` の無いときと同じ
（FastAPI 既定の 404）にする。実在する成果物が `dist/api/…` に在れば、そちらが優先。

## 理由

- **呼んだ側は JSON を待っている。** HTML の 200 を返すと、クライアントは「成功した」と
  読んでからパースに失敗する。失敗の理由が 2 段ずれる。
- **同じアプリが環境で違う答えを返すのをやめる。** 「手元では 404、本番では 200」は、
  再現しない不具合の温床になる。
- 打ち間違えた API が SPA を返すのは、静かな帯域の無駄でもある（index.html は
  `no-cache` なので毎回落ちる）。

## 影響

- `tests/integration/api/test_spa.py` に、**dist を作った状態で**本物のアプリへ
  `/api/nonexistent` を投げる検証を足した。受け皿の取りこぼしは、この形でしか出ない。
- `/docs` や `/metrics` のような API 以外の経路は今までどおり受け皿へ落ちる
  （実在するルーターが先に応えるので、落ちるのは打ち間違えたときだけ）。
- 派生アプリは `git merge template/main` で取り込める。
