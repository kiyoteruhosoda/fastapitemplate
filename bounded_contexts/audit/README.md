# audit — 記録と検証

「何が起きたか」を記録し、後から検証できるようにするコンテキスト。2 種類の記録を扱う。

| 記録 | テーブル | 残すもの | 閲覧 scope |
|---|---|---|---|
| 監査ログ | `audit_log` | **誰が**何をしたか（ログイン・管理操作・設定変更） | `audit:view` |
| アプリログ | `log` | **システムが**何をしたか（リクエスト・警告・例外） | `log:view` |

どちらの行にも同じ `requestId` が入る。片方で見つけた ID をもう一方の絞り込みに入れると、
1 リクエストの記録を両側から突き合わせられる。設計判断は
`docs/decisions/ADR-0013-audit-log.md`。

## 構成

```
domain/          監査イベントの種別・結果・対象と、検索条件・ページ・保持期間の
                 値オブジェクト。永続化のインターフェース
                 （収集用・書き込み用・検索用・削除用の Protocol）
application/     ユースケース（イベントの組み立て、まとめ書き、2 種類の検索、
                 選択肢一覧、期限切れログの削除）
infrastructure/  audit_log の SQLAlchemy モデルと、両テーブルのリポジトリ実装
presentation/    API ルーター・スキーマ・依存の組み立て・書き込みミドルウェア・
                 掃除の定期実行の配線
```

## 監査イベントの書き込みタイミング

記録は 2 段階に分かれている（ADR-0013）。

1. **処理の途中**: ルーターが `RecordAuditEvent.execute()` を呼ぶ。イベントを
   組み立ててリクエストの控え（`PendingAuditEvents`）に積むだけで、**DB を触らない**。
2. **リクエストの処理が終わってから**: `AuditRecordingMiddleware` が控えを取り出し、
   `WriteAuditEvents` が別トランザクションでまとめて書く。

途中で書かない理由は 2 つ。

- **失敗したログインを残すため。** リクエストのセッションで書くと、401 の
  ロールバックで最も記録したいイベントが消える。
- **SQLite で書き込みロックと競合しないため。** `db.flush()` を通る操作では
  リクエストのセッションが書き込みロックを握っており、別コネクションからの INSERT は
  `database is locked` になる。

ミドルウェアは**素の ASGI**（`BaseHTTPMiddleware` ではない）。FastAPI は `get_db` の
commit をレスポンス送出の後に行うため、`call_next` が戻った時点ではまだセッションが
開いている。`await self.app(...)` なら下流を最後まで待てる。

## 書き込みの責務

**監査ログはこのコンテキストが書く。** ルーターが操作の直後に
`RecordAuditEvent.execute()` を呼ぶ。

**アプリログはこのコンテキストが書かない。** 全レイヤーが `logging` 経由で書く横断的
関心事なので、書き込みは `shared/kernel/logging` の `DbLogHandler` に残してある。ここが
持つのは**閲覧のための検索**だけ。

## 監査イベントを新しく記録するとき

1. `domain/entities/audit_event.py` の `AuditEventType` に値を**末尾へ追加**する
   （`<名詞>.<過去形の動詞>`）。既にある値は変えない。DB に入る安定キーで、
   変えると過去の行が引けなくなる（`tests/unit/domain/test_audit_event.py` が値を固定する）。
2. 操作対象の種別が新しいなら `domain/value_objects/audit_target.py` の
   `AuditTargetType` にも追加する。
3. 記録したいルーターに `audit: AuditRecorderDep` を足し、操作の直後に呼ぶ。

```python
audit.execute(
    AuditEventType.USER_DELETED,
    target=AuditTarget.of(AuditTargetType.USER, user_id),
)
```

失敗も記録する場合は結果を明示し、`reason` に分類を入れる。

```python
audit.execute(AuditEventType.LOGIN_FAILED, AuditResult.FAILURE, reason="invalid_password")
```

「誰が」「どこから」は渡さない。認証依存関数とミドルウェアが `contextvars` に載せた値を
`Depends` が拾う（`presentation/dependencies.py`）。

**実行者が入るのは認証済みのリクエストだけ。** 未認証で叩ける操作（ログイン失敗・
パスワードリセット）は「誰がやったか」が分かっていない。分かっているのは「誰に対しての
操作か」なので、そちらを `target` に入れる。持ち主を `actor_user_id` に据えると、
第三者が起こしたイベントが本人の操作として残ってしまう（ADR-0013）。

## 記録するときの制約

- **PII を渡さない。** メールアドレス・ユーザー名・パスワード・トークン・設定値は
  記録しない。`reason` には「変更した項目名」（`fields=is_active`・`keys=LOG_LEVEL`）や
  「失敗の分類」（`invalid_password`）を入れる。
- **`reason` は 255 文字、`target_id` は 64 文字**で切られる（リポジトリが切り詰める）。
  一覧を載せる場合は組み立て側でも上限を意識する。
- **記録は本処理と別トランザクション**で行う。ログイン失敗のようにリクエストが
  ロールバックされても残る。逆に、commit 時に失敗した操作の成功行が残り得る。
- **記録の失敗は本処理を落とさない。** 失敗はアプリログへ `ERROR` で出る。
- **`execute()` を呼んでも即座には書かれない**（リクエスト終了時にまとめて書く）。
  同じリクエスト内で監査ログを読み返すテストを書かないこと。

## 検索

どちらの検索も条件を AND で積み、新しい順に 1 ページ返す（総件数付き）。件数の上限は
`domain/value_objects/log_page.py`（既定 100・最大 500）。

前方一致・部分一致の入力に含まれる `%` `_` `\` はエスケープする。利用者の入力は
「文字列」でありパターンではないため（`%` 1 文字で全件一致にならない）。

期間の境界はタイムゾーン付きでも受け取り、UTC の naive へ揃えてから比較する
（`shared/kernel/timestamps.to_naive_utc`）。保存値が UTC naive のため。

絞り込みの選択肢（ログレベル・監査イベント種別・結果・対象種別）は
`GET .../filters` が返す。列挙をフロントエンドへ写して二重管理しないため。

## 保持期間と掃除

両テーブルとも保持日数を設定でき、期限を過ぎた行は常駐スレッドが定期的に消す
（ADR-0021）。**既定はどちらも `0` ＝ 削除しない。**

| 設定キー | 対象 |
|---|---|
| `LOG_RETENTION_DAYS` | `log` |
| `AUDIT_LOG_RETENTION_DAYS` | `audit_log` |

- キーを分けてあるのは、アプリログを削る運用が監査記録を巻き込まないようにするため。
- 設定は掃除のたびに読み直す（保存すれば次の周回から効く。再起動は要らない）。
- 削除は主キーで小分けにし、1 塊ごとにトランザクションを閉じる。まとめて 1 文で
  消すと、リクエストの処理を待たせるほど長く書き込みロックを握る。
- `0` と負の日数は同じ「削除しない」扱い（打ち間違いで直近の行まで消さない）。
- 定期実行は `presentation/log_retention.py` が組み立てる。テスト時は起動しないので、
  掃除そのものを見るときは `purge_expired_logs_once()` を直接呼ぶ。

運用者向けの手順は `docs/OPERATIONS.md`「古いログを自動で消したいとき」。

## API

| エンドポイント | 用途 |
|---|---|
| `GET /api/admin/audit-logs` | 監査ログの検索 |
| `GET /api/admin/audit-logs/filters` | 監査ログの絞り込み選択肢 |
| `GET /api/admin/logs` | アプリログの検索 |
| `GET /api/admin/logs/filters` | アプリログの絞り込み選択肢 |

リクエスト・レスポンスの仕様は Swagger UI（`/docs`）が正本。画面側の仕様と操作手順は
`frontend/README.md`（S13・S14）。
