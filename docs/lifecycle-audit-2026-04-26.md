# ライフサイクル監査レポート（2026-04-26）

## 背景

シフト期間の削除フロー検討時に、CRUD の網羅性とライフサイクルの開閉対称性を全体調査した。「作成はできるが削除・終了・解除の手段が用意されていない」リソース・操作を網羅的に洗い出した結果を記録する。

サブエージェントによる調査・本ドキュメント作成: 2026-04-26（feature/period-archive-delete ブランチ作業中）。

## 統計サマリ

| カテゴリ | 件数 |
|---|---|
| 完全に削除手段がないリソース | 7 |
| 開閉非対称な操作 | 5 |
| API 実装あり / UI 未実装 | 2 |
| 派生する整合性問題 | 9 |
| **合計** | **23** |

## 1. 完全に削除手段がないリソース（7件）

| リソース | モデル | 状況 | 影響 |
|---|---|---|---|
| **ShiftPeriod** | `app/models/shift.py:5` | ~~POST/PUT のみ、DELETE 欠落~~ → **対応済み（PR #16）** | 誤作成や不要期間の永久蓄積 |
| **ShiftSubmission** | `app/models/shift.py:41` | POST のみ | ワーカーの誤申告を取り下げ不可 |
| **ShiftSchedule** | `app/models/shift.py:110` | POST/PUT のみ | confirmed 後の破棄不可 |
| **ShiftScheduleEntry** | `app/models/shift.py:149` | DELETE 欠落 | エントリ単位の削除不可 |
| **ShiftSubmissionSlot** | `app/models/shift.py:77` | DELETE 欠落 | 提出後のスロット修正が実質不可 |
| **Reminder** | `app/models/reminder.py:5` | DELETE 欠落 | 誤送信記録が永続 |
| **ApprovalHistory** | `app/models/approval.py` | DELETE 欠落 | 誤承認の記録を取り消せない |

## 2. ライフサイクル非対称（5件）

| 操作 | 順方向 | 不足している逆方向 |
|---|---|---|
| ShiftPeriod ステータス遷移 | draft → open → closed → finalized（`api_admin.py:419`） | open → draft、closed → open、finalized → 任意への巻き戻し不可 |
| ShiftSchedule 確定 | confirm（`api_admin.py:606`） | confirmed → 任意への取消不可 |
| Schedule 承認申請 | submit_for_approval（`api_admin.py:576`） | 申請者側からの「申請取下げ」不可 |
| VacancyCandidate 通知 | send_vacancy_notifications（`vacancy_service.py:154`） | 通知送信後の admin 側からの取消不可 |
| 承認ワークフロー設定切替 | approval_required ON/OFF（`api_admin.py:1532`） | 既に pending_approval 中のスケジュールは切替後も pending のまま残留 |

## 3. バックエンドはあるが UI から呼べないもの（2件）

| エンドポイント | 期待される UI 配置 | 状況 |
|---|---|---|
| `DELETE /api/admin/vacancy/<id>` | シフト構築タブ → 急募一覧 → 取消ボタン | API 完備、JS にハンドラなし |
| `DELETE /api/worker/calendar-links/<id>` | ワーカーのカレンダー連携設定 | API はあるが worker-app.js から呼ばれている形跡が見当たらず |

## 4. 派生する整合性問題（9件）

1. **ShiftScheduleEntry 削除時の Google Calendar イベント残留** — エントリが消えても `calendar_event_id` の Google 側イベントは残る（`api_admin.py:606-750` 周辺、cleanup 処理欠如）
   - PR #16 で ShiftPeriod 削除時の cleanup は best-effort で対応済み
2. **OrganizationMember の論理削除からの復活手段なし** — `remove_member()` は `is_active=False` を立てるのみ（`api_admin.py:875`）。再有効化 API がないため、一時除外が実質永続化
3. **Reminder の重複送信防御なし** — 同一期間に対する重複送信が記録上残り、削除も不可
4. **ShiftPeriod の cascade='all, delete-orphan' 設定** — DELETE API がない時期は発火しないが、PR #16 以降は注意（テストでカスケード挙動を検証済み）
5. **AsyncTask の dead 状態からの復旧が master 限定** — `/api/master/tasks/<id>/retry` は master 権限必須。組織管理者は self-service できない（`api_master.py:342`）
6. **Organization.settings_json の値削除手段なし** — `set_setting()` で None や {} を入れて無効化するしかなく、変更履歴も残らない（`organization.py:35-41`）
7. **ShiftChangeLog は append-only** — 誤った vacancy_fill の change_log を取り消すエンドポイントなし（`vacancy.py:80-114`）
8. **OpeningHoursCalendarSync / SyncOperationLog の append-only 設計** — 誤同期の取消記録を残せない（`opening_hours.py:80-121`）
9. **InvitationToken は物理削除のみ** — soft-revoke（無効化フラグ）がないため「なぜ無効になったか」の文脈が消える

## 推奨される対応の優先度

### 既対応
- ✅ **ShiftPeriod 削除 + アーカイブ機能**（PR #16、本セッション）

### 高優先（運用事故リスク）
1. **OrganizationMember の論理削除からの復活 API** — 一時除外が事実上の永久除外になっている
2. **VacancyRequest cancel UI の実装** — API は完成。JS と UI ボタンを追加するだけ
3. **ShiftSchedule confirmed → 取消フロー** — 確定後に誤りが見つかった際の救済手段

### 中優先（業務フロー柔軟性）
4. **ShiftPeriod ステータスの巻き戻し** — open → draft、closed → open
5. **Schedule 承認申請の取り下げ** — pending_approval を draft に戻す
6. **ShiftSubmission の取り下げ** — ワーカーの誤申告対応

### 低優先（監査・観測性）
7. **Reminder / ChangeLog / SyncOperationLog の論理削除フラグ追加**
8. **InvitationToken の soft-revoke 化**
9. **AsyncTask の admin 権限への retry 開放**

## 設計指針（PR #16 での学び）

- **削除はアーカイブを必須経由**（フェールセーフ）
- 関連データの cleanup は **手動**（cascade に乗らないものを明示的に削除）
- 外部連携（Google Calendar 等）は **best-effort**（DB 削除を妨げない）
- 削除前の影響範囲を **事前提示**（件数内訳）
- AuditLog に **削除前スナップショット + cleanup サマリ** を記録
- 状態遷移は **冪等**（同状態への再実行で no-op）

## 次セッションへの申し送り

このリストから個別に PR 化していく場合、各項目は 1 PR 単位を想定。優先度の高い順に着手する場合の所要見積:
- OrganizationMember 復活 API: 半日
- VacancyRequest cancel UI: 半日
- ShiftSchedule confirmed 取消: 1〜2 日（影響範囲が広い）

立憲さんの判断で進めてください。
