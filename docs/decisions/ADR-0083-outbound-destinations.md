# ADR-0083: 利用者が渡した宛先へは、確かめてからつなぐ

- 日付: 2026-10-30
- 状態: 承認

## 文脈

Web Push の購読の送り先（`endpoint`）は利用者が送ってくる URL で、お知らせを出すとサーバーがそこへ POST する。
検査は「`https://` で始まり 1000 字以内か」だけだったので、ログインした人なら誰でも、サーバーから宅内や
クラスタの内側（`https://127.0.0.1:8000/`・同じ namespace の `https://db:3306/`・ホストの管理の口）へ
送らせられた。応答で購読が消えるかどうかで、宛先の反応も外から探れた（task #738。stg で届くのを確かめた）。

派生アプリにも同じ形の穴がある（imggen のモデルの URL。task #739）。派生アプリごとに確かめ方を書くと
ばらつくので、雛形に部品を 1 つ置いて写す。

## 決定

1. 宛先の確かめは `shared/kernel/outbound_destination.py` の 1 か所に置く。
   - `check_https_url(url, allowed_host_suffixes=None)`: 名前を引かずに形を見る。https・ポート 443・利用者情報なし。
     全世界向けでない IP の直書きと、内側にしか無い名前（1 語の Service 名・`.svc`・`.cluster.local`・`.local` など）は断る。
     `allowed_host_suffixes` を渡すとそのホストとその下だけ受け取る。
   - `ensure_public_host(host, port)`: 名前を引き、どれか 1 つでも全世界向けでないアドレスなら断る。つなぐ直前に呼ぶ。
     転送（3xx）を追うときは、転送のたびに両方をやり直す（NolumiaScheduler の `http_fetcher.py` と同じ）。
2. Web Push の送り先は、**ブラウザの通知サービスのホスト（FCM・Mozilla・WNS・Apple）の 443 だけ**受け取る
   （`PUSH_SERVICE_HOST_SUFFIXES`。WBS・Tracker・Scheduler と同じ表）。外れたら `invalid_push_endpoint`。

## 理由

- 送り先が決まっているもの（Web Push）は許可リストが最も固い。名前を引かないので、試験も外の DNS に頼らない。
- 送り先が決まっていないもの（任意の公開 URL を取りに行く）は許可リストにできないので、名前を引いて確かめる。
  形の確かめだけだと、公開の名前が内側のアドレスを指す（DNS で付け替える）場合を通してしまう。
- 名前を引いてからつなぐまでの付け替え（DNS rebinding）までは防がない。防ぐには接続先のアドレスを固定する
  仕組みが要り、今の脅威（名簿に載った人）に対して重い。

## 影響

- 派生アプリ（belongings・toeic・fnbox・imggen）へ同じ部品と購読の検査を写す。
- 通知サービスが新しいホストを使い始めたら、表に足すまで購読が `invalid_push_endpoint` で断られる。
- 既に登録された購読の行は消さない（送る口では確かめていない）。宛先が内側の行が残っていれば手で消す。
