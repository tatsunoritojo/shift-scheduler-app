# ClaudeDesign 宛 — Phase 2a-3 実装後解禁分のコピー微調整

Phase 2a 修正納品（Phase 2a-2 修正版）に組み込まれていなかった「実装後解禁待ちの論点」が、発注側の実装作業で揃いました。**Phase 2b に進む前に、最後の微調整を 1 周だけお願いします**。

## 状況

`docs/lp-redesign-v2/phase-2a-fix-request.md` で「実装後解禁待ち」と保留にしていた論点について、発注側で以下の対応が完了しました:

| 論点 | 当時の判定 | 現状 | 対応 |
|---|---|---|---|
| Scene 1 期間公開メール演出 + 募集文面 | 実装中 (B) | 実装完了 | PR #24 マージ済 |
| Scene 1 カレンダー画像 / PDF | 実装予定 (C) | **既存実装で成立** | `openShareModal` + html2canvas/jsPDF が以前から動いていた |
| Scene 2 Google Cal 連動 | 実装中 (A) | **既存実装で成立** | `worker-app.js` + `shift-calculator.js` の `calculateAvailableSlots` で動いていた（fact レビューミスで未実装と判定していた） |
| Scene 4 必要枠 × 希望者 | 実装中 (D) | 実装完了（部分） | PR #26 マージ済。**ただし不足/充足の色判定は次フェーズ送り**（時間帯別の精緻計算が必要なため、現状はバッジ情報表示のみ） |
| Hero eyebrow `GOOGLE CALENDAR · NATIVE` | A に依存 | A 既存成立で OK | Hero コピーそのまま使える |

つまり **実装側は全部解禁**、コピーは概ね現状で整合している状態です。残るのは Scene 4 の不足判定の言い回しだけが「半成立」なので、そこを微調整する依頼です。

---

## プロンプト本文（ここから下をコピペ）

Phase 2a 全 5 修正の納品ありがとうございました。発注側の実装も全完了し、保留にしていた論点も全部解禁できる状態になっています。**Phase 2b に進む前に、最後の小さな微調整を 1 周だけお願いします**。

### 背景

「実装後解禁待ち」とお伝えしていた以下の論点が解禁されました:

- Scene 1 mail-card の演出 → 実装側で期間公開メール送信を実装したので、現状コピーで成立
- Scene 1 IMG/PDF artefact → 既に実装されている機能だったことが判明（PNG/PDF ダウンロード機能あり）。現状コピーで成立
- Scene 2 Google Cal 連動全体 → 既に実装されている機能だったことが判明（Worker UI で `calculateAvailableSlots` が予定を除外）。現状コピーで成立
- Scene 4 必要人数 → 実装側で StaffingRequirement テーブルを追加、「必要 N」バッジが日別に表示される。**ただし「足りない/余っている」の自動判定は次フェーズ**

### 修正 1 — Scene 4 の充足判定の言い回しを後退（必須）

**問題**: Scene 4 scene-lede「必要人数と希望者数が、同じ画面に重なって見える。**足りないコマ、余ってるコマ、ひと目でわかる**。」

**実装の事実**:
- 必要人数は時間帯ごと（曜日 × 時間帯ごと）に設定可能
- ただし日別バッジは「のべ人数」を集計表示する単純実装。例: 月 09-13=2 + 月 13-22=3 を 1 人が通しでカバーすると assigned=1 になり「不足」と誤判定するため、**色判定は意図的に保留している**
- 時間帯別の精緻な過不足判定は次フェーズで実装予定

**修正案**:

| 対象 | 現状 | 修正後 |
|---|---|---|
| scene-lede | 「必要人数と希望者数が、同じ画面に重なって見える。**足りないコマ、余ってるコマ、ひと目でわかる**。」 | 「必要人数と希望者数が、同じ画面に重なって見える。**配置した枠と必要数が並んで表示される**。」 |
| scene-body の 2 行目 | 「『この日にこの人を入れたら通院日と被る』も、その場で警告する」 ※ 既に削除済 | （削除済のままで OK） |

「ひと目でわかる」は強い断言になっているので「並んで表示される」程度のフラットな表現に。色判定で自動的に過不足を出す機能は次フェーズで揃えます。

### 修正 2 — Scene 2 INPUT/OUTPUT chip を実装に合わせる（軽微）

**現状**:
- chip 「INPUT 既存の Google 予定 / OUTPUT 勤務可能な時間帯のみ」

**実装の事実**:
- Worker UI のタイムラインは緑（勤務可能）+ 赤（既存予定）+ 橙（バッファ）の **4 色併記**。「予定が画面から消える」のではなく「予定は赤で見えるが、勤務可能候補からは自動的に外れる」が正確な動作

**修正案**（craft 判断で OK 不要）:

`OUTPUT 勤務可能な時間帯のみ` → `OUTPUT 自動算出された勤務可能時間` か `OUTPUT 予定を避けた勤務可能時間`

ただし、既存コピー「最初から出てこない」とは整合（候補からは外れる）。INPUT/OUTPUT chip だけの微調整なので、ClaudeDesign 側で残すか変えるかは craft 判断に委ねます。

### 修正不要 — そのまま使える箇所

確認のため、以下は **触らなくて OK** です:

- Scene 1 全体（mail-card + IMG/PDF artefact + INPUT 募集文面 chip）
- Scene 2 scene-h「Google カレンダーにもう予定が入っている時間は、最初から出てこない」
- Scene 5 Google-native 伏線（既に追記済）
- Hero eyebrow `GOOGLE CALENDAR · NATIVE`
- Connector A / B
- Functional stub

### Footer ラベル更新

```
<b>PHASE</b>01 + 02a + 02a-3 — 全 Scene の実装乖離対応完了
<b>NEXT</b>Phase 2b — 機能深掘り + Google-native 訴求 + Footer 仕上げ
```

### Phase 2b について

この最終微調整の納品をもって Phase 2a を完全クローズし、Phase 2b（機能深掘り + Google-native 訴求 + Footer 仕上げ）の方向性議論に入りたいです。Phase 2b の指示は別途送ります。

修正は同じ `landing-v2.html` 形式で送ってください。納期は急ぎません、品質優先で。

---

## プロンプト末尾（ここから上をコピペ終わり）

---

## 発注側メモ（次セッション向け）

- 修正 1（Scene 4 言い回し後退）は LP の虚偽訴求を防ぐため **必須**
- 修正 2（Scene 2 chip）は craft 判断、ClaudeDesign 側で適否を判断してもらう
- 実機ブラウザでの確認は ClaudeDesign 側で完了させる前提（発注側は受領後に fact レビューで通せば OK）

## 関連コミット（参考）

| 機能 | PR | コミット |
|---|---|---|
| 期間公開メール + 募集文面 (B) | [#24](https://github.com/tatsunoritojo/shift-scheduler-app/pull/24) | `df0ef09` |
| Worker Free/Busy シーケンス図追記 | [#25](https://github.com/tatsunoritojo/shift-scheduler-app/pull/25) | `93bdb2c` |
| 必要人数管理 (D) | [#26](https://github.com/tatsunoritojo/shift-scheduler-app/pull/26) | `c9ef105` |
