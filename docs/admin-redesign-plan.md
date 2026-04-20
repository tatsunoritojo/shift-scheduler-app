# 管理者画面 再設計プラン v2（実装着手版）

策定日: 2026-04-19
版: v2

## 0. この版の位置づけ

本書は、管理者画面の再設計を段階的かつ後方互換を維持しながら実装するための着手仕様である。
初版で整理された背景・設計方針・フェーズ構成は妥当であるため踏襲しつつ、実装上の解釈ブレを防ぐために以下を追加で明文化する。

- 判定定義
- API契約
- UI状態保持ルール
- フェーズ順の見直し
- 自動割当アルゴリズムの制約優先順位

## 1. 非機能要件

### 1-1. 後方互換

- 既存組織では新機能はすべて OFF を初期値とする
- 新機能OFF時、既存UI・既存APIレスポンスの互換性を維持する
- 既存のシフト作成・承認・同期・欠員補充のフローを壊さない

### 1-2. リリース方針

- 各フェーズは独立デプロイ可能とする
- DBマイグレーションを伴う変更は、機能トグル有効化前に本番投入可能な形にする
- フロントエンドは段階導入とし、初期段階では `admin-app.js` への追記を許容する

### 1-3. 性能

- ダッシュボード初回表示: 2秒以内目標
- auto-fill 下書き生成: 5秒以内目標
- 集計系APIは対象期間単位で完結し、N+1を避ける

## 2. 用語定義・判定定義

### 2-1. 最低出勤

「最低出勤」は、ワーカーごとに週単位で評価する。

**週の定義**
- 週の開始は組織ローカルタイムの月曜日 00:00
- 1期間が複数週にまたがる場合、週ごとに評価する

**カウント対象**
- `count_drafts = true` の場合: draft / confirmed を含む
- `count_drafts = false` の場合: confirmed のみ
- キャンセル済み・削除済みは含めない

**評価単位**
- `unit = count`: その週の勤務回数
- `unit = hours`: その週の勤務時間
- `unit = both`: 両方を満たしたときのみ達成

**適用モード**
- `mode = disabled`: 評価しない
- `mode = org_wide`: 組織共通の閾値を使用
- `mode = per_member`: メンバー個別の閾値を使用。個別値が null の場合は org_wide を継承

### 2-2. 最終出勤

- 対象ワーカーの最新勤務日を返す
- 集計対象は `count_drafts` と同じルールに従う
- `lookback_periods` は「前の何期間まで遡るか」を意味する
- 遡及しても存在しない場合は null

### 2-3. 同レベル重複

- `level_system.enabled = true` かつ `overlap_check.enabled = true` のときのみ評価
- `scope = same_tier` は「同一時間帯に同一 `level_key` のメンバーが2名以上割り当てられている状態」を指す
- これは警告であり、禁止制約ではない
- 自動割当では soft constraint、手動割当では警告表示のみ

### 2-4. 充足率

- その日または期間における「必要人数に対して埋まった人数の割合」
- 算式: `assigned_slots / required_slots`
- required が 0 の場合は null とし、UIでは「—」表示

### 2-5. 要対応

ダッシュボードの「要対応」は以下の優先順位で並べる。

1. 承認待ち期間
2. 未提出メンバー
3. 未割当スロット
4. 最低出勤未達メンバー
5. 最終出勤超過メンバー
6. 同レベル重複警告
7. カレンダー同期エラー
8. 欠員補充未応答

## 3. データモデル

### 3-1. `Organization.settings_json`

初版の構造を採用する。ただし、以下のデフォルト補完ロジックを `organization_settings.py` に持たせる。

- `level_system.enabled` = false
- `level_system.tiers` = []
- `overlap_check.enabled` = false
- `overlap_check.scope` = "same_tier"
- `min_attendance.mode` = "disabled"
- `min_attendance.unit` = "count"
- `min_attendance.count_drafts` = true
- `min_attendance.lookback_periods` = 1
- `ai.enabled` = false

### 3-2. `OrganizationMember` 追加カラム

- `level_key`: VARCHAR(32) nullable
- `min_attendance_count_per_week`: INTEGER nullable
- `min_attendance_hours_per_week`: FLOAT nullable

### 3-3. `Organization` 追加カラム

- `ai_pseudonym_salt`: BYTEA nullable

### 3-4. バリデーション

- `level_key` は tier 一覧に存在する key のみ許可
- `tiers[].key` は組織内一意
- `min_attendance_count_per_week >= 0`
- `min_attendance_hours_per_week >= 0`

## 4. DTO / APIレスポンス契約

### 4-1. `OrganizationMember.to_dict()` 拡張

以下を追加する。

```json
{
  "level_key": "senior",
  "min_attendance_count_per_week": 1,
  "min_attendance_hours_per_week": null
}
```

### 4-2. 既存スケジュールAPIの拡張方針

既存 `GET /api/admin/periods/{id}/schedule` は維持し、重い集計は opt-in にする。

**リクエスト**

```
GET /api/admin/periods/{id}/schedule?include_insights=1
```

**追加レスポンス**

```json
{
  "insights": {
    "worker_stats": [
      {
        "user_id": 12,
        "level_key": "senior",
        "last_worked_at": "2026-04-10",
        "days_since_last_worked": 9,
        "weekly_count": 1,
        "weekly_hours": 4.5,
        "min_attendance_met": false
      }
    ],
    "overlap_warnings": [
      {
        "date": "2026-04-20",
        "slot": "18:00-20:00",
        "level_key": "senior",
        "user_ids": [12, 18]
      }
    ]
  }
}
```

### 4-3. ダッシュボードAPI命名

既存 `/api/admin/dashboard/overview` との衝突を避けるため、新規の管理ホーム系は以下とする。

- `GET /api/admin/home/summary`
- `GET /api/admin/home/year-timeline`
- `GET /api/admin/home/action-items`
- `GET /api/admin/home/upcoming`
- `GET /api/admin/home/statistics`

### 4-4. 自動割当API

- `POST /api/admin/periods/{id}/auto-fill`
- レスポンスは保存済み draft ではなく、まず preview を返す
- 管理者の確認後に「下書きとして保存」する二段階でもよいが、初版では簡略化のため即 draft 保存を許容する

## 5. UI状態保持ルール

### 5-1. タブ状態

- 最後に開いていたメインタブを `localStorage` に保存
- 期間選択状態も保存
- ダッシュボードからシフト管理へ遷移した場合、対象期間IDがあれば優先選択する

### 5-2. アンカー遷移

ダッシュボードの要対応項目クリック時は、以下の形式で遷移する。

```
/admin?tab=shift-management&period_id=123&panel=warnings
```

### 5-3. 再読込ルール

- タブ切替時に毎回フル再初期化しない
- 未ロードタブのみ初回ロード
- 明示的な更新ボタンか、操作成功後のみ再取得

## 6. フェーズ構成（v2）

### Phase A: 設定基盤 + DTO整備

**目的**

レベル / 最低出勤 / 重複チェックを設定として保存できるようにし、以後の画面で使える状態にする。

**作業**

- マイグレーション追加
- `organization_settings.py` 新設
- 設定API追加
- `OrganizationMember.to_dict()` 拡張
- 設定UI追加
- テスト追加

**受け入れ基準**

- 設定保存後にリロードしても保持される
- 無効な `level_key` は保存できない
- tier削除時、使用中メンバーがいれば削除不可または明示確認
- APIレスポンスに追加DTOが反映される

---

### Phase B: 割当判断情報の可視化

**目的**

既存のシフト構築画面上で、割当判断に必要な情報を追加表示する。

**作業**

- `attendance_stats.py` 新設
- `schedule?include_insights=1` 実装
- 日付詳細ポップアップに以下追加
  - レベルバッジ
  - 最終出勤表示
  - 最低出勤未達表示
  - 同レベル重複タイムライン警告
- 右側バーに「要注意メンバー」追加

**受け入れ基準**

- 設定OFF時、既存画面と見た目・挙動が変わらない
- 設定ON時のみ追加情報が出る
- 最終出勤と最低出勤判定が一貫している

---

### Phase C: IA土台追加（大改修前の器だけ入れる）

**目的**

全面再編の前に、`admin.html` の中に新しい情報構造の器を作る。

**作業**

- タブ名だけ先行変更
  - ダッシュボード
  - シフト管理
  - メンバー
  - 設定
- ただし内部実装は既存コンポーネント流用
- `admin-dashboard.html` は作らず、`admin.html` 内に新タブ領域として差し込む
- 状態保持を導入

**受け入れ基準**

- 既存機能が壊れない
- 新タブ構造で遷移できる
- period / builder の状態が保持される

---

### Phase D: ダッシュボード実装

**目的**

ログイン直後に、やるべきこと・現在地・次の期間を把握できる画面を提供する。

**構成**

- 年間タイムライン
- 健全性サマリー
- 要対応リスト
- 直近カレンダー
- 次期間見通し
- 統計

**API**

- `GET /api/admin/home/summary`
- `GET /api/admin/home/year-timeline`
- `GET /api/admin/home/action-items`
- `GET /api/admin/home/upcoming`
- `GET /api/admin/home/statistics`

**受け入れ基準**

- ログイン時の初期表示がダッシュボードになる
- 要対応から対象画面へ遷移できる
- ダッシュボードだけで「今どこを見るべきか」が分かる

---

### Phase E: IA本再編 + JS分割

**目的**

巨大化した `admin-app.js` と情報過多UIを整理する。

**作業**

- shift-management を独立モジュール化
- members, settings, dashboard を分割
- 右側バーの責務整理
- 旧タブ名・旧DOM参照の削除

**受け入れ基準**

- 主要フローに回帰がない
- タブ切替で状態が壊れない
- モバイルでも最低限操作可能

---

### Phase F: ルールベース自動割当

**目的**

AIなしで「管理者が直しやすい draft」を生成する。

**制約優先順位**

**Hard constraints**
1. 営業時間外に割り当てない
2. 必要人数上限を超えない
3. 同一人物の重複時間帯勤務を禁止
4. 明示的な勤務不可希望には割り当てない

**Soft constraints**
1. 最低出勤未達者を優先
2. 週間勤務時間が少ない者を優先
3. 同レベル重複を避ける
4. 直近出勤者への偏りを避ける

**作業**

- `auto_fill.py` 新設
- preview 兼 draft 生成API
- UIに「自動割当」追加
- 生成理由の簡易表示
  - 例: 最低出勤未達のため優先
  - 例: 同レベル重複回避のため別枠へ配置

**受け入れ基準**

- 数秒以内に生成される
- hard constraint を破らない
- soft constraint はスコアとして説明可能

---

### Phase G: AI提案

**目的**

過去パターンを踏まえた提案を生成する。ただし最終決定は管理者が行う。

**作業**

初版の方向性を踏襲する。ただし以下を追加する。

- 使用モデル名は設定値化し、コードに直書きしない
- 実名・メール・電話番号は送信禁止
- 外部送信データ定義書を別紙で作成
- ログ保存期間と削除方針を運用文書に明記
- **OFF の組織からは送信ゼロ** を統合テストで保証

**受け入れ基準**

- オプトインでのみ有効
- 管理者承認前に確定されない
- 送信ペイロードに直接識別子が含まれない

## 7. テスト方針

### 7-1. 単体テスト

- `test_organization_settings.py`
- `test_attendance_stats.py`
- `test_schedule_insights.py`
- `test_admin_home_api.py`
- `test_auto_fill.py`
- `test_ai_pseudonym.py`

### 7-2. 回帰観点

- 既存管理画面タブ遷移
- 期間作成
- シフト編集
- 承認
- 同期
- 欠員補充

### 7-3. 手動確認

- `python wsgi.py`
- 新機能OFF組織 / ON組織の両方で確認
- `localStorage` が壊れた場合の初期化動作確認

## 8. 実装順の厳守事項

- Phase A 完了前に B 以降へ入らない
- Phase C は器だけ。新規ページ分岐は作らない
- Phase D 完了前に `admin-app.js` の大規模分割をしない
- Phase F 完了前に G に入らない
- 各Phaseごとに feature flag で切り戻し可能にする

## 9. このv2で削るもの

初版から、以下は一旦後ろ倒しにする。

- `admin-dashboard.html` の独立ページ化
- 早い段階での `admin-app.js` 全面分割
- AI提案のモデル固定
- E-1段階での複雑すぎる制約充足最適化

## 更新履歴

- 2026-04-19: v1 策定
- 2026-04-19: v2（実装着手版）へ改訂 — 判定定義・API契約・UI状態保持・フェーズ順見直し・制約優先順位を明文化。`admin-dashboard.html` 独立ページ化と admin-app.js 全面分割を後ろ倒し。Phase順を A/設定 → B/可視化 → C/IA器 → D/ダッシュボード → E/IA本再編 → F/ルール自動割当 → G/AI に再編
