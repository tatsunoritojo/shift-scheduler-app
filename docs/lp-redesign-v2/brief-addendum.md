# ブリーフ追補 — ブランド刷新へのピボット

**作成**: 2026-04-23 / 東城 × Claude（PM 補佐）
**対象**: `brief.md` への追加・上書き事項
**優先度**: `brief.md` 本体と矛盾する箇所は本ドキュメントが優先する

---

## 1. 背景 — 方針転換の理由

Phase 1 成果物（ウォームペーパー + 朱）を受領後、**LP と App UI（濃紺 + 青アクセント）の視覚的乖離** が実運用上の問題として顕在化した。

- CTA から App へ遷移した瞬間、ブランドが破綻する
- Phase 0 Q1 で「LP 内で App の青を捨てる」を承認したが、これは LP 単体の craft を優先した判断であり、ブランド整合性を犠牲にしていた
- 現在は Onedrop パイロット（〜2026-05-03）中で 12 名利用のみ。**ブランド移行コストが歴史的最小の時点**

→ この機会に **LP + App UI の両方を統一する新ブランドパレット** へピボットする。

---

## 2. 新ブランドパレット（確定）

| 役割 | 名称 | Hex（RGB） | CMYK |
|---|---|---|---|
| **メインカラー** | BRIGHTBLUE | `#00CCFF` | 100.20.0.0 |
| **アクセント** | YELLOW | `#FFE626` | 0.10.85.0 |

### 位置づけの明確化

新パレットは **「既存 LP / App の青系譜を継承しつつ、執行を craft 化する」** 方向である。

- 既存 LP `#3B82F6`（Tailwind blue）→ AI 臭、捨てる
- 既存 App `#1266D3`（濃紺 + 青）→ Tailwind デフォルト起源、捨てる
- **新 `#00CCFF`（BRIGHTBLUE）** → シアン寄りの鮮烈な青、craft で差別化可能。青というブランドシグナル自体は継承

この位置づけにより、本件は「前回の朱ディレクションの否定」ではなく **「LP 外のブランド意思決定による新制約」** として扱う。

### 配色方針の候補（ClaudeDesign 判断に委ねる）

| 案 | 構造 | 雰囲気 |
|---|---|---|
| **①地=白/paper + BRIGHTBLUE メイン + YELLOW アクセント** | 明度高・読みやすい | 編集誌面系 |
| **②地=BRIGHTBLUE + 白文字 + YELLOW スパーク** | 強烈・記憶に残る | Blue Note / RISO 系 |
| **③地=墨/ink + BRIGHTBLUE 主 + YELLOW サブ** | 硬質・夜間誌面 | モード系 |

明朝タイポは継続。②③は紙面感の温度差が出る可能性あり — ClaudeDesign 提案を待つ。

---

## 3. `brief.md §5` 禁止リストの更新

### 削除する項目（色関連）

以下は **「青回避」という過剰な NG」** だったため削除する：

- ~~`#3B82F6`（Tailwind blue-500、既存 LP のプライマリ）の使用禁止~~
- ~~紫 → 青、青 → シアンのグラデーション禁止~~（グラデ自体は緩和、ただし「意味なく使う」は引き続き禁止）
- ~~定型的な「IT プロダクト色」（`#6366f1` インディゴ、`#8b5cf6` バイオレット等）禁止~~

### 維持する禁止項目（色以外は全て継続）

- lucide アイコンの線画多用
- 絵文字の使用
- システムフォントのみで済ませる
- 挑発型ヘッドライン
- 形容詞シリーズ（「シンプル、パワフル、美しい」）
- 星 5 つ偽レビュー
- 3 カラム均等 Features グリッド
- Pain → Solution テンプレ二項対立
- ストック写真・汎用 3D イラスト
- グラスモーフィズム
- スマホフレーム使い回し

### 新規追加する禁止項目

- **BRIGHTBLUE を Tailwind の青（`#3B82F6`）と混同する配色**（近い明度のブルー 2 色併用など）
- **YELLOW を警告色として使う**（`YELLOW` はブランドアクセント、注意喚起 UI は別途 `#9B2F23` 系）
- **BRIGHTBLUE の多階調グラデーション**（単色使用の規律を保つ。グラデが必要なら`BRIGHTBLUE → paper` の明度遷移のみ許可）

---

## 4. スコープ拡張 — App UI への波及

本件は LP だけでなく App UI 全体の色再塗装を伴う：

| 対象 | ファイル | 工数見積 |
|---|---|---|
| 色変数基盤 | `static/css/common.css` | 0.5 日 |
| Worker UI | `static/css/worker.css` | 0.5-1 日 |
| Admin UI | `static/css/admin.css` | 1 日（最も色依存が強い） |
| Owner UI | `static/css/owner.css` | 0.5 日 |
| Master / その他 | `static/css/master.css` 他 | 0.5 日 |

**計 3-4 日工数**。LP リリース直後〜1 週間以内に App 刷新を完了する計画。

ClaudeDesign の本フェーズでのスコープ：**LP のみ**。ただし LP で定義する色変数（`--accent` 等）は App 移植前提で命名・設計してほしい。

---

## 5. Phase 1 成果物の扱い

Phase 1 成果物 `phase-1-landing-v2.html` は **構造 craft は保持、色のみ差し替え** で再利用可能。

### 保存する（色替え不要）
- hinge セル「05/14 火」motif
- 7×5 グリッドの Hero / 接続部再利用設計
- scroll-timeline + IntersectionObserver フォールバック実装
- 9 秒 Hero アニメの timing（wish hatch → chip → hinge zoom）
- タイポグラフィ（Shippori Mincho / Zen Kaku Gothic New / JetBrains Mono / Fraunces）
- レイアウト規律（余白、罫線、masthead、asymmetric grid）

### 差し替える
- `:root` の色変数 9 本 → 新パレットへ
- 透過 rgba ハードコード 10 箇所
- スクショの再塗装方針（Phase 2 で朱系→BRIGHTBLUE 系に変更）

---

## 6. 新 Open Questions

ClaudeDesign の再提案で決めたい点：

| # | 質問 | 備考 |
|---|---|---|
| 1 | 配色方針 ①②③ のどれを軸にするか | 紙面感の継続は ①、印象強度は ②③ |
| 2 | YELLOW の役割 | 純粋アクセント / データ可視化 / リンク hover / etc |
| 3 | hinge セル「05/14 火」のハイライト色 | 旧 = 朱、新 = BRIGHTBLUE or YELLOW のどちら |
| 4 | Hero 組成アニメの wish hatch 色 | 朱のハッチ → BRIGHTBLUE or YELLOW のどちら |
| 5 | 明朝タイポは継続でよいか | BRIGHTBLUE + 明朝 は Blue Note 系で成立するが、Sans-serif 化も可能 |

---

## 7. 期待する納品

1. 新 Phase 0 提案書（HTML 1 本、editorial magazine 形式を踏襲）
2. 新 palette での Hero コンセプトスケッチ
3. 上記 5 つの Open Questions への既定値
4. Phase 1 成果物のどこを保持し、どこを差し替えるかの明示
