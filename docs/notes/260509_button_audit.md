# 全画面ボタン Audit Catalog

最終更新: 2026-05-09 / 対象: admin / worker / owner / master / vacancy / login / invite / no-organization / landing

## 1. 5 カテゴリの定義（再掲）

| カテゴリ | 用途 | 視覚 | hover 強度 |
|---|---|---|---|
| **primary** | 画面の主目的アクション | 青塗り | 強 (shadow + glow) |
| **secondary** | 編集・取得などのサブアクション | グレー枠 (中性) | 弱 |
| **state-warning** | 取り消し可能な状態変更（要注意） | オレンジ枠 | 中 |
| **state-positive** | 取り消し可能な復帰系 | 緑枠 | 中 |
| **destructive** | 取り消し不可 | 赤塗り（強調） | 強 |

特殊（5 カテゴリ外で残すもの）:
- `tab-btn` — タブナビゲーション（独自の active state あり）
- `logout-btn` — ヘッダー専用、Ghost 系（背景透明、テキストのみ）
- `google-btn` / `google-login-btn` — ブランド色固定
- size: `btn-xs` / `btn-sm` / 既定 / `btn-lg` を維持

## 2. ページ別 Audit

### 2.1 admin.html (43 件 + 動的)

#### Setup wizard (id 65-83)
| ボタン | 現状 | 提案 | 備考 |
|---|---|---|---|
| カレンダー接続テスト | btn-primary | **primary** | OK |
| スキップ（後で設定する） | btn-outline | **secondary** | OK |
| 保存してインポート開始 | btn-primary | **primary** | OK |
| 戻る | btn-outline | **secondary** | OK |

#### 同期キーワード (id 92)
| ボタン | 現状 | 提案 |
|---|---|---|
| 保存 (sync-keyword) | btn-outline + dirty-tracker | **primary** (dirty 時) / **secondary** (clean 時) |

⚠ dirty-tracker 連携: clean 時 secondary、dirty 時 primary に切替（既存の class-toggle ロジックそのまま流用、class 名のみ変える）

#### Calendar 連携 (id 116-117)
| ボタン | 現状 | 提案 |
|---|---|---|
| インポート（カレンダー→例外リスト） | btn-outline | **primary** | 主操作なので |
| エクスポート（設定→カレンダー） | btn-primary | **secondary** | 双方向で「主」が曖昧、両方 primary より片方下げる |

検討余地: 業務的にどちらを主にするか立憲さんに確認。今回はインポートを主と仮置き

#### プレビュー操作 (id 131-134)
| ボタン | 現状 | 提案 |
|---|---|---|
| OK → シフト期間を作成 | btn-primary | **primary** | OK |
| シフトを追加 | btn-outline | **secondary** | OK |
| シフトを削除 | btn-outline | **secondary** | 「削除」だが実は例外日リストへの遷移、destructive ではない |
| 時間を調整 | btn-outline | **secondary** | OK |

#### 設定タブ 各保存ボタン (162, 204, 223, 286, 309, 338, 349)
全て btn-outline + dirty-tracker (clean: outline / dirty: primary 切替)

| ボタン | 現状 | 提案 |
|---|---|---|
| 各「○○ を保存」(7 件) | btn-outline | **dirty 時 primary / clean 時 secondary** |

(レベル設定 / 重複チェック / 最低出勤 / 必要人数 / 承認プロセス / 営業時間 / リマインド / 同期キーワード)

#### Phase A レベル設定 (id 201)
| ボタン | 現状 | 提案 |
|---|---|---|
| 追加 (level tier) | btn-outline | **secondary** | OK |

#### Staffing (id 308)
| ボタン | 現状 | 提案 |
|---|---|---|
| 時間帯を追加 | btn-outline | **secondary** |

#### 期間タブ (id 414, 515 + 動的 row buttons)
| ボタン | 現状 | 提案 | 備考 |
|---|---|---|---|
| 作成 (新規期間) | btn-primary | **primary** | OK |
| アーカイブ済を表示へ移動 | btn-outline btn-sm | **secondary** btn-sm | OK |
| **(動的)** 文面 | btn-outline + inline padding | **secondary** | 役割: 編集 |
| **(動的)** 募集開始 | btn-primary + inline padding | **primary** | OK |
| **(動的)** 締切 | btn-warning + inline padding | **state-warning** | OK |
| **(動的)** リマインド | btn-outline + inline padding | **secondary** | 役割: 通知送信 |
| **(動的)** 案内DL | btn-outline + inline padding | **secondary** | 役割: 取得 |
| **(動的)** アーカイブ | btn-outline + inline padding | **state-warning** | ⚠ **要変更**: 状態変更 + 取消可、現状青で誤認 |
| **(動的)** 復元 | btn-outline + inline padding | **state-positive** | ⚠ **要変更**: 復帰系、緑で「戻す」を表現 |
| **(動的)** 完全削除 | btn-outline + **inline 赤色上書き** | **destructive** (赤塗り) | ⚠ **要変更**: 弱い見た目を強調へ。inline style 廃止 |

#### Builder (id 537-539, 562)
| ボタン | 現状 | 提案 |
|---|---|---|
| 保存 (schedule) | btn-outline + dirty-tracker | **dirty: primary / clean: secondary** |
| 承認申請 | btn-warning | **state-warning** | OK |
| 確定・カレンダー同期 | btn-success | **state-positive** OR **primary** | 検討: 「確定」は最終アクションなので primary でも可。緑塗り維持なら state-positive |
| 更新 (refresh-builder) | btn-outline btn-sm | **secondary** |

#### メンバー管理 (id 332, 444, 456-457, 472, 498)
| ボタン | 現状 | 提案 |
|---|---|---|
| メンバー管理タブへ (warning banner) | btn-outline btn-sm | **secondary** |
| 事業主を招待する | btn-primary | **primary** |
| コピー (招待 URL) | btn-primary | **secondary** | 「コピー」は補助操作 |
| 再生成 | btn-outline | **state-warning** | ⚠ 既存コードを無効化する操作なので注意系 |
| 招待コードを生成 (初回) | btn-primary | **primary** |
| 招待を作成 (個別) | btn-primary | **primary** |

#### 動的 row buttons (members / invitations / vacancy / change_log)
| ボタン | 現状 | 提案 |
|---|---|---|
| 取消 (招待) | btn-outline btn-sm | **state-warning** btn-sm | 招待を無効化 |
| 除外 (member) | btn-outline btn-sm | **state-warning** btn-sm | ⚠ 復活手段なし、destructive 寄りだが is_active=false 化なので state-warning |
| ロール変更 (member, select) | (form-control) | (form-control) | ボタンではないので対象外 |
| 欠員補充 (worker entry) | btn-outline btn-sm | **state-warning** btn-sm | 状態変更系 |
| キャンセル (vacancy) | btn-outline btn-sm | **state-warning** btn-sm | 募集を無効化 |
| 上へ / 下へ (level tier) | btn-outline btn-sm | **secondary** btn-sm |
| 削除 (level tier) | btn-outline btn-sm | **destructive** btn-sm | tier 削除はメンバー紐付け解除を伴う |
| 行削除 (staffing row) | btn-outline (icon-only) | **destructive** btn-sm |

#### Settings popup (動的)
| ボタン | 現状 | 提案 |
|---|---|---|
| 例外として保存 / 更新 | btn-primary | **primary** |
| 削除 (例外) | btn-danger | **destructive** | OK 既に正しい |

#### Share modal (id 604-606)
| ボタン | 現状 | 提案 |
|---|---|---|
| PNG で保存 | btn-primary | **primary** |
| PDF で保存 | btn-primary | **primary** | 2 つ並ぶので片方を secondary に下げる検討余地あり |
| メッセージをコピー | btn-outline | **secondary** |

#### Announcement modal (id 635-636)
| ボタン | 現状 | 提案 |
|---|---|---|
| 保存 | btn-primary | **primary** |
| キャンセル | btn-outline | **secondary** |

#### Vacancy / Confirm / Sync logs ダイアログ (動的)
| ボタン | 現状 | 提案 |
|---|---|---|
| 通知を送信 (vacancy dialog) | btn-primary | **primary** |
| キャンセル (vacancy dialog) | btn-outline | **secondary** |
| 閉じる (sync logs) | btn-outline | **secondary** |

---

### 2.2 worker.html (4 + 動的)

| ボタン | 現状 | 提案 |
|---|---|---|
| ログアウト | logout-btn (特殊) | **logout-btn** 維持 |
| 戻る | btn-outline | **secondary** |
| 計算設定トグル | calc-settings-toggle-btn (特殊) | 標準化検討、ただし独自挙動なので保留 |
| 提出 | btn-success btn-lg | **primary btn-lg** | 提出は worker の主目的、緑である必然性は低い |
| (動的) 適用 (calc settings) | btn-primary btn-sm | **primary** btn-sm |
| (動的) デフォルトに戻す | btn-outline btn-sm | **secondary** btn-sm |
| (動的) 解除 (linked calendar) | btn-unlink-cal (特殊) | **state-warning** btn-sm に統合検討 |
| (動的) 適用 / リセット (custom time) | btn-primary/outline btn-sm | **primary** / **secondary** |
| (動的) 全件カレンダー追加 | btn-primary btn-sm | **primary** |
| (動的) カレンダーに追加 (per shift) | btn-sm btn-primary | **primary** btn-sm |

---

### 2.3 owner.html (4)

| ボタン | 現状 | 提案 |
|---|---|---|
| ログアウト | logout-btn | **logout-btn** 維持 |
| 戻る | btn-outline | **secondary** |
| 承認 | btn-success | **primary** | 承認画面の主目的 |
| 差戻し | btn-danger | **state-warning** | ⚠ **要変更**: 取り消し不可ではないので destructive ではない |

---

### 2.4 master.html (16 + 動的)

| ボタン | 現状 | 提案 | 備考 |
|---|---|---|---|
| ログアウト | logout-btn | **logout-btn** 維持 |
| 詳細を見る (health alert) | btn-sm btn-outline + 白色 inline | **secondary** btn-sm (ヘッダー専用 variant 検討) |
| tab-btn (9 件) | tab-btn | **tab-btn** 維持 |
| 更新 (tasks/audit) | btn-outline btn-sm | **secondary** btn-sm |
| 今すぐタスク処理 | btn-primary btn-sm | **primary** btn-sm |
| ヘルスチェック実行 | btn-primary | **primary** |
| 実行 (SQL) | btn-primary | **primary** |
| (動的) 編集 | btn-outline btn-xs | **secondary** btn-xs |
| (動的) 無効化 (user) | btn-danger btn-xs | **state-warning** btn-xs | ⚠ **要変更**: is_active=false 化、復活可能 |
| (動的) 有効化 (user) | btn-success btn-xs | **state-positive** btn-xs |
| (動的) 状態変更 (period/schedule) | btn-outline btn-xs | **state-warning** btn-xs |
| (動的) 提出状況 / 同期詳細 / 詳細 | btn-outline btn-xs | **secondary** btn-xs |
| (動的) 再同期 | btn-primary btn-xs | **primary** btn-xs |
| (動的) リトライ (task) | btn-primary btn-xs | **primary** btn-xs |
| (動的) 修正 (health) | btn-danger btn-sm | **state-warning** btn-sm | health fix は復元系、destructive ではない |
| (動的) 代理提出（全日不可） | btn-danger btn-xs | **state-warning** btn-xs | ⚠ |
| (動的) 編集ダイアログ 保存 | btn-primary | **primary** |
| (動的) キャンセル / 閉じる | btn-outline | **secondary** |

---

### 2.5 公開・半公開ページ

| ページ / ボタン | 現状 | 提案 |
|---|---|---|
| login.html: Google ログイン | google-btn (特殊) | **google-btn** 維持（ブランド色固定） |
| invite.html: Google ログイン | google-login-btn (特殊) | **google-login-btn** 維持 |
| no-organization.html: 作成 | create-btn (特殊 1 件) | **primary** に統合（標準化メリット大） |
| no-organization.html: ログアウト | logout-btn (a 要素) | **logout-btn** 維持 |
| landing.html (6 件) | 範囲外（マーケ用 LP、別系統 CTA デザイン） | **対象外** |

⚠ landing.html はマーケ LP で独自デザイン体系。今回の見直しから除外する。

---

### 2.6 動的 modal / dialog (showConfirmDialog 経由)

`modules/ui-dialogs.js` の `showConfirmDialog(title, message, btnClass, btnLabel, ...)` が引数 `btnClass` を受け取り、呼出側が `btn-primary` / `btn-warning` / `btn-danger` を渡している。

呼出 24 箇所を確認:
- btn-primary: 18 件 (確認・実行系)
- btn-warning: 2 件 (招待コード再生成 / 締切)
- btn-danger: 4 件 (削除系: 例外削除 / メンバー除外 / 招待取消 / 完全削除)

提案:
- API は維持
- 呼出側で渡す class を **primary / state-warning / destructive** の 3 種に整理
- `state-warning` 用に新 class が必要

---

## 3. 変更による副次効果（要注意点）

### 3.1 `btn-success` を廃止する判断
緑塗りの `btn-success` は現状 `worker 提出` / `admin 確定・同期` / `master 有効化` で使用。
- worker 提出 → primary に統合（緑から青へ。worker の主目的なので青塗り強調が筋）
- admin 確定 → state-positive (緑枠) に変更検討、または primary
- master 有効化 → state-positive (緑枠)

`btn-success` (緑塗り) は実質「state-positive (緑枠)」に置き換える。

### 3.2 `btn-warning` を `state-warning` に置き換え
オレンジ塗り `btn-warning` は現状 `承認申請` / `締切` で使用。
オレンジ枠 `state-warning` に変える。塗り → 枠で軽くなるが、意味の明確化を優先。

### 3.3 `btn-outline` の意味的分裂
現状 29 件の outline が **secondary / state-warning / state-positive** の 3 系統に分裂する。class 自体は廃止 → secondary を default にする。

### 3.4 inline style 上書きの一掃
`style="color:#dc2626;border-color:#fca5a5"` (期間完全削除) と `style="border-color:#fff;color:#fff"` (master health alert) を削除し、CSS class で表現する。

### 3.5 dirty-tracker 連携
保存ボタンは clean/dirty で class を切り替える既存ロジック (`dirty-tracker.js`) を更新:
- clean 時: `btn-secondary`
- dirty 時: `btn-primary`

現状の `btn-outline` ↔ `btn-primary` のトグルから、`btn-secondary` ↔ `btn-primary` に変える。

---

## 4. 数値サマリ

| 提案カテゴリ | 推定件数 (静的+動的) |
|---|---|
| primary | 約 30 |
| secondary | 約 35 |
| state-warning | 約 12 |
| state-positive | 約 5 |
| destructive | 約 6 |
| 維持 (tab-btn / logout-btn / google-btn / etc) | 約 15 |

合計 ~100 件のボタン touch points。

---

## 5. 確定した判断（2026-05-09 立憲さん回答）

| 項目 | 決定 |
|---|---|
| Calendar 連携 (インポート/エクスポート) | **両方 primary** |
| Share modal PNG / PDF | **PNG primary / PDF secondary** |
| 確定・カレンダー同期 (builder) | **primary** (btn-success 緑塗りから青塗りへ変更) |
| owner.html 差戻し | **state-warning** (オレンジ枠、btn-danger 赤塗りから変更) |
| landing.html | **対象外** (マーケ LP の独自体系) |
| メンバー除外 / 招待取消 / vacancy キャンセル / 招待コード再生成 | **state-warning** |

## 6. 削除する旧 class

| 旧 class | → | 新 class |
|---|---|---|
| `btn-outline` | → | `btn-secondary` (大半) / `btn-state-warning` / `btn-state-positive` (個別判断) |
| `btn-success` (緑塗り) | → | `btn-primary` (主目的の場合) / `btn-state-positive` (状態変更の場合) |
| `btn-warning` (オレンジ塗り) | → | `btn-state-warning` (オレンジ枠) |
| `btn-danger` (赤塗り) | → | `btn-destructive` (rename) |

`btn-primary`, `btn-sm`, `btn-lg`, `btn-xs` は維持。
