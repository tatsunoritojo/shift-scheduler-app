# ClaudeDesign 宛 — Phase 1 GO 指示

以下をそのままコピペで ClaudeDesign に渡す。Phase 0 提案を受領・承認済みの文脈を前提にしている。

---

## プロンプト本文（ここから下をコピペ）

Phase 0 提案をレビューしました。**全面承認、Phase 1 GO** です。

### 採択された決定

- 方向 B カスタム（ウォームペーパー + ディープインク + 朱 `#8B2E13`）× 明朝タイポで確定
- hinge セル「05/14 火曜」を LP 全体の motif として採用
- Open Questions 6 問、すべてあなたの既定値で承認
  1. 既存 UI の濃紺/青アクセントは LP 内では使わない（再塗装 OK）
  2. ロゴ「シ」マークは masthead 左に黒置換で小さく
  3. Hero コピー「月末が、少しだけ早く終わる。」採用
  4. 使い方動画は Section 2 末尾に lazy 埋め込み、Hero には使わない
  5. Admin/Owner 追加スクショは Phase 2 前に依頼（時期別途調整）
  6. 架空データ差し替えは ClaudeDesign 叩き台 → 発注側最終確定

### Phase 1 で依頼する成果物

Phase 0 提案 §07 の通り、**1 本の HTML** で以下 2 点の動作版を提出してください：

#### DELIVERABLE 01 — Hero（9 秒ループ・動作版）
- 7×5 Field グリッド
- 朱のハッチ（wish）、黒のチップ（assigned）、hinge セルのズーム枠
- CSS アニメーションのみ（JS は最小限）
- `prefers-reduced-motion` 対応
- SKIP ANIMATION ボタン付き
- 軽量（目標 ~40KB 以内）

#### DELIVERABLE 02 — 接続部 A（scroll-timeline 動作版）
- Hero → 1ヶ月体験 Scene 1 へのスクロール連動遷移
- hinge セル「05/14 火曜」から scale 進行で Scene 1 へハンドオフ
- `scroll-timeline` CSS を本命とし、IntersectionObserver フォールバック実装
- 1ヶ月体験 Scene 1 は **ワイヤ（要素の置き場所だけ）で OK**。完成は Phase 2

### 1ヶ月体験セクションの場面対応について（Phase 1 では参考情報）

接続部の scale story は 5 フレームで美しく閉じていますが、ブリーフ §6 の 1ヶ月体験 6 場面（月末 期間公開 / 提出期間 / 締切前 / 締切後 確定 / 確定 カレンダー反映 / 前日・欠員）との対応関係は Phase 2 で詰めます。Phase 1 の接続部 A は「Hero から Scene 1 へのハンドオフ」だけに集中してください。

### Phase 2-3 で改善したい点（Phase 1 blocker ではない）

- **Google-native セキュリティ訴求**: 「データが Google に残る = ベンダーロックなし」の訴求が Phase 0 では薄い。機能深掘りセクション（Section 2）でどこか 1 セクションを割いて扱う想定で、配置案を Phase 2 で提案してほしい

### 技術制約の再確認

- 最終納品先: `static/pages/landing-v2.html` + `static/css/landing-v2.css`（+ 任意で `static/js/landing-v2.js`）
- Phase 1 時点では単一 HTML ファイルで OK（後段で分離）
- CSP: インラインスクリプト最小化、外部依存は Google Fonts のみ
- パフォーマンス: LCP 2.5s、CLS 0.1 以内

---

納期の希望は特になし。品質を優先してください。できあがったら同じ形式（HTML 一式）で送ってもらえれば、こちらで受領 → レビューします。

質問があれば作業前に投げてください。

---

## プロンプト末尾（ここから上をコピペ終わり）
