# レビューノート — LP v2

ClaudeDesign 成果物に対する発注側の判断・承認・差し戻しを時系列で記録。

---

## 2026-04-23 · Phase 0 コンセプト提案 — 承認

**成果物**: `phase-0-proposal.html`（1172 行、HTML 編集誌面形式）

**方向性**: B カスタム（ウォームペーパー + ディープインク + 朱）× 明朝タイポ

**決定**: **全承認（Option A）**。6 Open Questions すべて ClaudeDesign 提案の既定値で採用。

### 承認した Open Questions 回答

| # | 回答 |
|---|---|
| 1. LP 内で濃紺/青アクセント廃止 | 廃止 OK |
| 2. ロゴ「シ」マーク出し方 | masthead 左に黒置換で小さく |
| 3. Hero コピー | 「月末が、少しだけ早く終わる。」で進行 |
| 4. 使い方動画 MP4 埋め込み | Section 2 末尾に lazy 埋め込み、Hero には使わない |
| 5. Admin/Owner 追加スクショ | Phase 2 前に 3 枚依頼（時期は別途調整） |
| 6. 架空データ差し替え分担 | ClaudeDesign 叩き台 → 発注側最終確定 |

### ウォッチ項目（Phase 2-3 で確認、Phase 1 blocker ではない）

- **Google-native セキュリティ訴求の強度** — ブリーフ §3 で核の差別化としたが、Phase 0 提案では Hero eyebrow の "GOOGLE CALENDAR · NATIVE" のみで扱いが軽い。機能深掘りセクション（Section 2）で扱い方を改善したい
- **1ヶ月体験 6 場面との対応** — 接続部 5 フレームは hinge セル中心の scale story で、ブリーフ §6 の 6 場面（月末 → 提出 → 締切 → 確定 → 前日 → 欠員）の扱いは Phase 2 で確認

### 特筆事項

- hinge セル「05/14 火曜」を LP 全体を横断する motif として採用 — ClaudeDesign 独自提案、採用
- 提案書自体が editorial magazine 形式で提出された — メタ craft として評価
- ブリーフ禁止リストを提案書内で struck-through 可視化 — 方向確認が明確

### 次フェーズ: Phase 1

Phase 0 提案 §07 の通り、以下 2 本を 1 HTML で受領予定：

- **DELIVERABLE 01**: Hero（9秒ループ・動作版）
- **DELIVERABLE 02**: 接続部 A（scroll-timeline、Hero → 1ヶ月体験 Scene 1）

---

## 2026-04-23 · Phase 1 成果物 受領

**成果物**: `phase-1-landing-v2.html`（1024 行）

- Hero 動作版（9 秒ループ、4 段 axis、CSS アニメ、prefers-reduced-motion 対応）
- 接続部 A（300vh sticky + scroll-timeline + IntersectionObserver フォールバック）
- 1ヶ月体験 Scene 1 ワイヤ
- CSS 変数で色が整理されている（`:root` 9 変数 + 透過 rgba 10 箇所のみハードコード）

→ 品質良好。ただし **ブランド整合性の問題** が発覚、色方針を再検討することに。

---

## 2026-04-23 · ブランド刷新方針へのピボット

**問題**: Phase 1 の朱 × ペーパー路線と App UI（濃紺 + 青アクセント）が乖離、CTA 遷移時のブランド破綻

**決定**: LP + App UI の両方を統一する新ブランドパレットへ（③方針）
- メイン: **BRIGHTBLUE `#00CCFF`**（CMYK 100.20.0.0）
- アクセント: **YELLOW `#FFE626`**（CMYK 0.10.85.0）

**理由**:
- Onedrop パイロット 12 名のみで移行コスト最小
- 既存 App の青（#1266D3）は Tailwind デフォルト起源、戦略的意味が薄い
- Phase 1 の構造 craft（hinge セル、7×5 grid、scroll-timeline、9 秒アニメ、明朝）は 7-8 割保存可能

**作成ドキュメント**:
- `brief-addendum.md` — ブリーフ上書き事項
- `phase-0-redo-prompt.md` — ClaudeDesign への再提案依頼

---

## 2026-04-23 · Phase 0 Rev 2 受領 — 承認

**成果物**: `phase-0-proposal-v2.html`（724 行、editorial magazine 形式）

**方向**: ② 地=BRIGHTBLUE + 白紙面ゾーン + YELLOW spark × 明朝（Blue Note / RISO 系譜）

**決定**: **全面承認（Option A）**。3 点の軽微な確認事項は ClaudeDesign 判断に委ね、Phase 1.5 GO。

### 承認した Open Questions 既定値

| # | 採用された既定値 |
|---|---|
| Q1 配色方針 | 方向② 青地 50% / 白紙 35% / YELLOW 3% / 墨 12% |
| Q2 YELLOW の役割 | 純粋アクセント + hinge motif のみ、総面積 3% 以下 |
| Q3 hinge ハイライト | YELLOW 抜き（セルそのものを塗る） |
| Q4 wish hatch | 白 `#F5F3EC` · 30° · 透過 0.85 |
| Q5 明朝タイポ | 継続、青地上で weight 600→700 に光量補正 |

### 特筆事項

- Color token の命名を App 移植前提に刷新: `--accent` → `--brand`、`--brand-deep`、`--brand-ink`、`--spark`、`--warn` 分離
- AA コントラスト検証済み（ink on paper 19:1 / brand-ink on brand 7.4:1 / ink on spark 14:1）
- Heritage swap map（§06）で保持/差し替え対象が行単位で明示
- Phase 1 成果物への色パッチのみで 0.5 日以内の作業見積
- Deliverable 2（App UI migration kit）を LP 確定後に別納品する計画

### 次フェーズ: Phase 1.5

色パッチ適用版 `landing-v2.html` を 1 本納品予定。構造・アニメ・スクロール挙動は 1 行も変えない前提。
