# ClaudeDesign 宛 — Phase 2a 積み残し修正 + 実装乖離コピー差し替え

Phase 2a-2 納品ありがとうございます。**Phase 2b に進む前に、Phase 2a-1/2a-2 の積み残し修正をお願いします**。

以下をそのままコピペで ClaudeDesign に渡す。

---

## プロンプト本文（ここから下をコピペ）

Phase 2a-2 納品、受領しました。Scene 3-6 + Connector B + Functional stub の構造、Scene 5 オーバーラップ修正まで含めて確認しています。**ただし Phase 2b に進む前に、Phase 2a-1/2a-2 の積み残し修正をお願いします**。

### 背景

発注側でコードベースとシーケンス図を読み直したところ、複数の Scene のコピーが実装と乖離していることが判明しました。LP として虚偽訴求になりかねないので、craft の話ではなく fact レベルの修正です。判定は発注側で済ませてあります。

戦略:
- **コピー差し替えで済む箇所** → 今回お願いする 5 点
- **実装で対応する箇所** → 発注側で実装作業中。完成後に Phase 2a-3 として再依頼します

---

### 修正 1 — Phase 1.5 patch の積み残し（Cloudflare + Footer）

前回の修正依頼が Phase 1.5 patch 版に反映されないまま 2a-1/2a-2 まで来ていました。改めて。

**(a) Cloudflare email 難読化の除去**

Scene 1 mail-card の以下要素を削除:
```html
<span class="mc-from">店長 東城 &lt;<a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="...">[email&#160;protected]</a>&gt;</span>
```
+ ファイル末尾の `<script data-cfasync="false" src="/cdn-cgi/scripts/.../cloudflare-static/email-decode.min.js">` も削除。

書き換え:
```html
<span class="mc-from">店長 東城 &lt;tencho-tojo@example.com&gt;</span>
```

ダウンロード経路で Cloudflare が自動挿入したものなので、ClaudeDesign の意図ではないと理解しています。

**(b) Footer ラベル更新**

現状:
```
<b>PHASE</b>01 — Hero + Connector A
<b>DIRECTION</b>Paper × Ink × BRIGHTBLUE + YELLOW spark
<b>NEXT</b>Phase 2 — Scene 01 – 06
```

更新後:
```
<b>PHASE</b>01 + 02a — Hero + Connector A + Scene 01–06 + Connector B
<b>DIRECTION</b>Paper × Ink × BRIGHTBLUE + YELLOW spark
<b>NEXT</b>Phase 2b — 機能深掘り + Google-native 訴求 + Footer 仕上げ
```

---

### 修正 2 — Scene 3 リマインド頻度のコピー差し替え

**問題**: 「締切 24h / 6h 前」の二段階トリガーは未実装。実装は Vercel Cron 制約で 1/day 固定、リマインダーは「**締切前日 09:00 に未提出者へ 1 通**」のみ。

**修正箇所**:

| 対象 | 現状 | 修正後 |
|---|---|---|
| chip | `TRIGGER 締切 24h / 6h 前` | `TRIGGER 締切前日の朝` |
| roster-foot | `次回 06h 前 17:59 → 自動送信` | `明朝 09:00 まで未提出なら自動送信` |
| roster-list 内の `<i>17:00</i>` 表示 | リマインド済 17:00 | 削除 or `09:00`（前日朝の cron 起動時刻に揃える） |
| scene-body | 24/6h を匂わせる文 | 「未提出者だけに自動でリマインド」「Admin は督促を書かなくていい」は事実なので残す |

時刻表示を `09:00` に統一すれば、運用の事実と矛盾しない上に「朝届く」体験として craft も保てます。

---

### 修正 3 — Scene 4 のドラッグ削除 + 個人カレンダー衝突警告削除

**問題 A**: 「ドラッグで配置」は未実装（admin-app.js に drag/drop ハンドラなし）。  
**問題 B**: Admin が Worker 個人 Google カレンダーとの衝突をその場で警告する機能は未実装。さらに発注側判断として「シフトに同じ時間帯複数名入る」のが普通の運用なので、衝突警告は訴求としても弱い。

**修正箇所**:

| 対象 | 現状 | 修正後 |
|---|---|---|
| scene-body | 「**ドラッグで配置**、Worker 名をクリックで割り当て。」 | 「Worker 名をクリックで割り当てる。集めた希望と必要枠が、同じ画面に並ぶ。」 |
| scene-body 後半 | 「『この日にこの人を入れたら通院日と被る』も、その場で警告する」 | **削除** |
| chip | `WARN 個人カレンダー衝突` | **削除**（chip 自体を抜く、または別の事実 chip に差し替え） |
| assign-foot | warn-cell `! 渡辺さんを 17:00 に配置すると、Google カレンダーの「通院 18:30」と重なります` | **削除**。代わりに「**集めた希望が、必要枠の隣に並ぶ。**」程度の静かな fact 一行に |

ただし右側 cands の `<span class="warn-tag">通院 18:30</span>` は **残しても OK**。これは Worker が希望提出時のメモ欄に書いたもの、という解釈で読めます（実装の `ShiftSubmission.notes` フィールドに該当）。

---

### 修正 4 — Scene 6 配信ロジックのコピー差し替え

**問題**: 実装は Admin が候補リストから選び、選んだ候補全員に **並列メール送信**。先着順で確定（race condition guard あり）、残りの候補は「すでに補充済み」案内に切り替わる。「希望者 → 空き枠保持者」の 2 段階配信、「1 通だけ届く」は事実誤認。

**修正箇所**:

| 対象 | 現状 | 修正後 |
|---|---|---|
| scene-h | 「体調不良。欠員の連絡が、夜に届く。」 | そのまま OK（事象の描写なので） |
| scene-lede | 「穴の空いたコマだけ、出られる人に通知が飛ぶ。」 | 「Admin が**候補を絞って打診**。希望提出済みの中から、その日の勤務時間が少ない人を優先。」 |
| scene-body | 「希望者 → 空き枠保持者 順に、選択的に届く。全員に一斉通知して気まずくしない。」 | 「**最初に応答した人で確定**。残りの候補者には『すでに補充済み』と静かに切り替わる。」 |
| chip | `SCOPE 希望者 → 空き枠保持者` | `SCOPE 希望提出者から週時間少ない順` |
| chip | `RESULT 翌朝に解消済` | そのまま OK |
| phone-caption | 「1 通だけ届く。**希望と空きの両方を持っている人**から順番に。」 | 「**最初に届いた人で確定**。週時間が少ない人を優先して、Admin が候補を選ぶ。」 |

phone notif スタックの演出（シフリーだけ primary、Google カレ/LINE は dim）は **そのまま残す**。「他のアプリの通知に埋もれない」という craft は意味的に正しいので。pn-body の「あなたは**空きあり**」は **削除**（Google Cal 空き判定ロジックは実装にないため）。

---

### 修正 5 — Scene 5 に Google-native 伏線を 1 行追加（craft 強化）

実装と一致しているので大きな修正は不要ですが、Functional stub に進む前の伏線として 1 行欲しい。

**追加位置**: Scene 5 scene-foot の直前 or `gcal-foot` の `legend-note` の隣  
**追加コピー（叩き台）**: 「**データはずっと、各自の Google アカウントの中。シフリーの中ではない。**」

これは Phase 2b の Google-native 訴求の入口になります。Functional stub には既にスロット予約済とのこと、次フェーズで本格回収する想定。

---

### 実装後解禁待ちの論点（今回は触らないでください）

以下は発注側で実装作業中。完成次第、**Phase 2a-3 として追加修正依頼を投げます**。今は現状コピーのまま放置で OK。

| 論点 | 状態 | LP 該当箇所 |
|---|---|---|
| Scene 1 期間公開メール演出 + 募集文面チップ | 実装中 (B) | mail-card 全体, `INPUT 期間 1 回 / 募集文面` |
| Scene 1 カレンダー画像 / PDF | 実装予定 (C) | `IMG · PNG` / `PDF · A4` artefact |
| Scene 2 Google Cal 重複チェック全体 | 実装中 (A) | scene-h, scene-lede, scene-body, overlap visualisation, INPUT/OUTPUT chip |
| Scene 4 必要枠 × 希望者表示 | 実装中 (D) | `必要 03 / 希望 05`, slot-title `枠`, `VIEW 必要枠 × 希望者` chip |
| Hero eyebrow `GOOGLE CALENDAR · NATIVE` | (A) に依存 | Hero 部 |

これらに手を入れると、実装完了後に再修正が必要になるので **触らないでください**。

---

### Phase 2b について

Phase 2b（機能深掘り + Google-native 訴求 + Footer 仕上げ）の方向性は **このコピー差し替え納品後に**改めて議論したいです。Phase 2a の積み残しが片付いた状態で次に進む方が craft が乱れません。

修正は同じ `landing-v2.html` 形式で送ってください。納期は急ぎません、品質優先で。

質問・craft 判断の確認があれば作業前に投げてください。

---

## プロンプト末尾（ここから上をコピペ終わり）
