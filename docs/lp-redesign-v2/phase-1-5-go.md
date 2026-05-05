# ClaudeDesign 宛 — Phase 1.5 GO 指示

以下をそのままコピペで ClaudeDesign に渡す。

---

## プロンプト本文（ここから下をコピペ）

Phase 0 Rev 2 提案、受領 & レビューしました。**全面承認、Phase 1.5 GO** です。

### 採択された決定（§07 Open Questions の既定値 5 問すべて採用）

1. **配色方針**: 方向② 地=BRIGHTBLUE + 白紙面ゾーン + YELLOW spark（量比 青地 50% / 白紙 35% / YELLOW 3% / 墨 12%）
2. **YELLOW の役割**: 純粋アクセント + hinge motif のみ、総面積 3% 以下
3. **hinge ハイライト**: YELLOW 抜き（セルそのものを塗る）
4. **wish hatch**: 白 `#F5F3EC` · 30° · 透過 0.85
5. **明朝タイポ**: 継続、青地上で weight 600→700 に光量補正

### Heritage swap map（§06）も承認

- 構造 craft は 1 行も変えない（9s ループ、4 段 axis、7×5 grid、hinge 位置、scroll-timeline、タイポ本数）
- 変わるのは `:root` 色変数 9 本 / 透過 rgba 10 箇所 / Mincho weight の 3 箇所のみ
- Color token の命名刷新（`--brand`、`--brand-deep`、`--brand-ink`、`--spark`、`--warn`）は App 移植前提で OK
- AA コントラスト検証の具体数値付きに感謝

### Phase 1.5 で依頼する成果物

**`landing-v2.html`（BRIGHTBLUE patch 適用版）** を 1 HTML で納品してください：

- `:root` の色変数を新トークンに swap
- 透過 rgba 10 箇所を色相変更
- Mincho weight を青地上で 700 に昇格
- Hero 組成アニメ・接続部 A・Scene 1 ワイヤ は Phase 1 の挙動を維持

提案書の見積通り **0.5 日以内** で大丈夫です。

### 参考メモ（判断は任せる、ClaudeDesign 側で決めて OK）

以下 3 点、軽微な確認事項。**明示的な指示を出さないので、あなたの判断で進めてください**：

1. **hinge セルの日付** — Phase 1 実装は `05/14 火曜`、Phase 0 Rev 2 提案は `04/14 火曜`。どちらで統一しても OK（整合が取れれば良い）
2. **YELLOW 総面積 3% 以下の検証** — 規律として掲げた数値。実装後に目視で超えていれば chip の高さ等で調整
3. **App 移植キット（Deliverable 2）の着手タイミング** — 提案では「LP 確定後」だが、Phase 2 と並行着手したい場合は Phase 1.5 納品時に変数定義だけ先行してくれても歓迎

### Phase 2 予告

Phase 1.5 承認後は、Phase 2 で **1ヶ月体験 Scene 1〜6 の本実装** + **機能深掘りセクション** に進みます。そのタイミングで、ブリーフ §3 で核としていた **Google-native セキュリティ訴求**（「データが Google に残る / ベンダーロックなし」）の配置を相談させてください。機能深掘りセクションのどこかで 1 枠使う想定です。

### 納期

特に急ぎではありません。品質優先。完成したら HTML 一式で送ってください。

質問があれば作業前に投げてください。

---

## プロンプト末尾（ここから上をコピペ終わり）
