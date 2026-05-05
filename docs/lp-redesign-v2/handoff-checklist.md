# ClaudeDesign 引き渡しチェックリスト

ClaudeDesign に作業を委託する前に、以下がすべて渡せる状態にあることを確認する。

---

## 1. ドキュメント

- [ ] `docs/lp-redesign-v2/brief.md` — 本体ブリーフ
- [ ] `docs/lp-redesign-v2/assets-and-context.md` — 素材・追加コンテキスト
- [ ] `docs/lp-redesign-v2/handoff-prompt.md` — ClaudeDesign に渡すプロンプト文面（本キットの隣に配置）

## 2. ブランド資産

- [ ] `static/icons/icon-512.svg`
- [ ] `static/icons/icon-192.svg`
- [ ] `static/icons/icon-512.png`
- [ ] `static/icons/icon-192.png`
- [ ] `static/icons/favicon-32.png`
- [ ] `static/icons/apple-touch-icon.png`

## 3. 実画面スクショ（差し替え前提）

- [ ] `docs/lp-redesign-v2/S__274219020_0.jpg` 〜 `S__274219028_0.jpg`（9 枚）

## 4. アンチパターン参照用（既存 LP）

- [ ] `static/pages/landing.html`
- [ ] `static/css/landing.css`

## 5. 補足資料（任意）

- [ ] `docs/sequence-diagrams/` — プロダクトの挙動を深く理解したい場合
- [ ] `20260316_Shifreeの使い方動画.mp4` — Hero アニメのコンセプト参考

---

## 共有方法の選択

| 方法 | 向いているケース |
|---|---|
| ZIP 一式で渡す | オフラインで作業させたいとき |
| 共有フォルダ（Drive 等） | バージョン管理したい・追加素材を随時足すとき |
| コピペ（ブリーフと主要スクショだけ） | ちょっとしたプロトタイプ依頼 |

---

## 渡した後の初動

1. ClaudeDesign から「Phase 0: コンセプト提案」が返ってくる
2. 東城さん × Claude（PM 補佐）で内容レビュー
3. 承認なら Phase 1（Hero + 接続部の実装）へ、修正なら方向すり合わせ

Phase ごとに小刻みにレビューする方針（brief.md §12）。
