# シーケンス図集（業務利用者向け）

シフリー（shift-scheduler-app）の主要フローを「人間がシステムとどう関わるか」の切り口で図示したものです。各図は実装ファイル (`app/blueprints/`, `app/services/`) を根拠に作成しています。

## 構成

| # | ファイル | 対象 | 主要アクター |
|---|---|---|---|
| 00 | [overview.md](00-overview.md) | システム全体の俯瞰（最後に読むと整合する） | Worker / Owner / Admin / 招待者 / 外部サービス |
| 01 | [onboarding.md](01-onboarding.md) | 新規メンバーの参加（4経路） | 招待者 / 新規ユーザー / Google |
| 02 | [worker-monthly-flow.md](02-worker-monthly-flow.md) | Worker の月次サイクル | Worker |
| 03 | [owner-approval.md](03-owner-approval.md) | 承認プロセス（ON/OFF 分岐） | Admin / Owner |
| 04 | [admin-operation-cycle.md](04-admin-operation-cycle.md) | Admin のシフト運営サイクル | Admin / Worker / Owner |
| 05 | [calendar-sync-recovery.md](05-calendar-sync-recovery.md) | カレンダー同期失敗と復旧 | Admin / Worker / Google Calendar |
| 06 | [vacancy-request.md](06-vacancy-request.md) | 欠員募集 | Admin / 候補 Worker |
| 07 | [background-jobs.md](07-background-jobs.md) | Cron / 通知 / リマインダー | Vercel Cron / ユーザー（受信側） |

## 凡例

- **実線の矢印** — HTTP リクエスト、ユーザー操作、関数呼び出し
- **破線の矢印** — レスポンス、通知メール、コールバック
- **alt / opt / par** — 分岐・条件・並列
- **rect color** — 同一トランザクションや同一画面のまとまり

## 注意

- シーケンス図は「正常系＋主要分岐」を中心に描いています。細部のエラーハンドリング（DB 失敗時の rollback、audit log への記録など）は省略しています。
- エンドポイント名・関数名は実装時点のもの。`app/blueprints/` と `app/services/` が一次情報。
