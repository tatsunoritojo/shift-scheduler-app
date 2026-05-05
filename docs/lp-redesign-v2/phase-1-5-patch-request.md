# ClaudeDesign 宛 — Phase 1.5 小修正依頼

Phase 1.5 成果物 (`landing-v2.html` · BRIGHTBLUE patch) を実機確認しました。**全体としては承認**ですが、2 箇所の小修正をお願いします。

## プロンプト本文（ここから下をコピペ）

Phase 1.5 実機確認完了、概ね承認です。明朝の圧と hinge セルの YELLOW が 1 秒印象として効いています。以下 2 点のみ修正をお願いします。

### 修正 1 — カレンダー右上の重なり

右上の列ヘッダー `日` と月ラベル `APR 2026 / 04` が物理的に重なっています。

対象 CSS:
```css
.field .lbl-days{ position:absolute; left:34px; right:16px; top:6px; ... }
.field .month-mark{ position:absolute; right:18px; top:4px; ... }
```

解決方法はお任せします。候補：
- 月ラベルを左肩（行ラベル W14 の上）に移す
- 月ラベルを下部 axis 行の隣に移す
- 列ヘッダーの右 16px を増やして月ラベル分の余白を確保

編集誌面の余白規律を保てる配置でお願いします。

### 修正 2 — ズームアニメのスクロール量を 1/3 に

接続部 A のスクロール距離が長すぎて離脱しそうになります。現状：

```css
.connector{ height: 300vh; }           /* desktop, scroll距離 200vh */
@media (max-width:860px){
  .connector{ height: 220vh; }         /* mobile, scroll距離 120vh */
}
```

スクロール距離を **1/3** に圧縮してください：

```css
.connector{ height: 167vh; }           /* desktop, scroll距離 67vh */
@media (max-width:860px){
  .connector{ height: 140vh; }         /* mobile, scroll距離 40vh */
}
```

スケール進行の JS (`scaleNum`/`frameNum` の表示切替閾値 0.12 / 0.35 / 0.6 / 0.84) はそのままで大丈夫です（比率計算なので自動追従）。

もし「1/3 だと速すぎて各フレームが読み取れない」と感じたら、**1/2 圧縮（220vh）に緩めても OK**です。あなたの craft 判断で調整してください。

### その他

- Footer の `<div><b>DIRECTION</b>Warm paper × Deep ink × 朱</div>` が Phase 1 のラベルのまま残っています。BRIGHTBLUE に更新してください（軽微）

ついでにで構いません。修正後は同じ `landing-v2.html` 形式で送ってください。

---

## プロンプト末尾（ここから上をコピペ終わり）
