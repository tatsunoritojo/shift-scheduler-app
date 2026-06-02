# OAuth verification / shifree.com 移行 handoff

**基準日: 2026-05-31**

このファイルは Phase 1 バッチ1（公開文書整備 + DB 監視ツール追加）と、その後のドメイン移行 + Google Cloud Console 設定までの累積記録。次セッションは Step L から再開する。

## Phase 1 バッチ1（既完了）

- ブランチ: `feature/oauth-verification-phase1-batch1`
- コミット: `53f2fe9`
- push 済み: `origin/feature/oauth-verification-phase1-batch1`
- PR: 未作成
- 内容: privacy.html / terms.html の noindex 削除・最終更新日更新・相互リンク・Limited Use の機械学習禁止行追加、landing.html の誇張数値撤去 + Limited Use 明示、scripts/db_monitor.py 新設、scripts/README.md 新設、tmp_prod_inspect.py 削除

## ドメイン方針の確定（経緯）

- 当初 B案 `shifree.tatsunoritojo.com` で進めたが、対外印象（個人ドメイン）の懸念で**白紙化**
- 案 C（独自ドメイン取得）へ転換し、Cloudflare Registrar で `shifree.com` を取得（$10.46/year）
- 採用ドメイン: **`shifree.com`**（apex メイン、www は 307 リダイレクト）
- `shifree.tatsunoritojo.com` は採用しない方針に変更

## 今回完了した外部設定

- Vercel に `shifree.com` を Production として設定
- `www.shifree.com` は `shifree.com` へ 307 redirect
- `shifree.vercel.app` は段階移行用に残置
- `shifree.tatsunoritojo.com` は削除済み
- Cloudflare DNS（`shifree.com` ゾーン）で apex CNAME / www CNAME / Search Console TXT を設定
- Cloudflare DNS（`tatsunoritojo.com` ゾーン）は Phase 1 開始前の状態へ復帰
- Google Search Console で `shifree.com` ドメインプロパティを追加し、所有確認済み

## Google Cloud Console / OAuth 同意画面（Branding）

更新済み。

- Application home page: `https://shifree.com/lp`
- Privacy policy: `https://shifree.com/privacy`
- Terms of service: `https://shifree.com/terms`
- Authorized domains:
  - `shifree.com` を追加
  - `shift-scheduler-app-9ksb.onrender.com` を削除
  - `shifree.vercel.app` は段階移行中のため残置
  - `www.googleapis.com` は由来不明のため保留

## OAuth Client ID

OAuth 2.0 Client ID（`shift-scheduler-app`, client ID 先頭 `739906304418-m6bv...`）側で以下を更新済み。

- JavaScript origins は空のまま維持（過去から空で運用されているため、不要な変更を入れない方針）
- Redirect URI から Render 旧URIを削除
- Redirect URI に新ドメイン用2件を追加
  - `https://shifree.com/auth/google/callback`
  - `https://shifree.com/auth/google/callback-link`
- Redirect URI に旧Vercel用2件を残置
  - `https://shifree.vercel.app/auth/google/callback`
  - `https://shifree.vercel.app/auth/google/callback-link`

## 現在の公開ステータス

- OAuth consent screen はまだ Testing
- Production publish はまだ行っていない
- OAuth verification submission もまだ行っていない
- `GOOGLE_REDIRECT_URI` / CORS関連のVercel環境変数確認は未実施
- Phase 2 コード変更も未実施

## 次回開始地点

次回は以下の順で進める。

1. `git status` 確認
2. handoff 内容確認
3. **Step L: Vercel 環境変数の現状確認**
   - `GOOGLE_REDIRECT_URI`
   - CORS関連環境変数
   - BASE_URL / APP_URL / PUBLIC_URL などURL系変数があれば確認
4. **Phase 2 コード変更**
   - `landing.html` の canonical / OGP / Twitter URL を `https://shifree.com/lp` または適切な新URLへ更新
   - `shifree.vercel.app` のハードコードをGrep
   - `app/config.py` やredirect URI生成ロジックを確認
   - 必要なら `shifree.com` への切替対応
5. **新ドメインで動作確認**
   - `https://shifree.com/lp`
   - `https://shifree.com/privacy`
   - `https://shifree.com/terms`
   - Googleログイン
   - callback
   - callback-link
6. 問題なければ Testing → In production を検討
7. OAuth verification 用の scope justification とデモ動画シナリオを作成

## 残課題（メモ）

- OAuth Client ID 一覧で `shift-scheduler-app` に⚠️警告アイコンが出ていた件: Render redirect URI 削除でほぼ解消されたはず。次回ログイン確認時に再確認
- `www.googleapis.com` が Authorized domains に入っている件: 由来不明、verification 申請時に Google から指摘があれば削除
- `shifree.vercel.app` 系の Vercel ドメイン / Redirect URI / Authorized domains からの最終削除: 新ドメインで動作完全確認後、別ステップで実施

## 注意

- `shifree.vercel.app` はまだ削除しない
- Vercel環境変数を確認する前に `GOOGLE_REDIRECT_URI` を変更しない
- OAuth consent screen を In production にする前に、新ドメインでログイン動作確認を行う
- Phase 2 コード変更は次セッションで行う
- `docs/incident-2026-04-26-handoff.md` などOAuthと無関係な差分は混ぜない
- OAuth Client ID 設定の伝播は5分〜数時間。新ドメインでのログイン動作確認は十分時間を置いてから

## OAuth verification の背景（参考）

- 問題の根: テストモードのOAuth consent screenでは calendar スコープを含む場合 refresh token が **7日で失効**（公式: https://developers.google.com/identity/protocols/oauth2 — Refresh token expiration）
- 既存テスターの実害: schedule 11 で種具歩乃花さんの 4枠が `CREDENTIALS_EXPIRED`、未試行 7枠もタイムアウト疑い
- 根本解決: OAuth consent screen を「In production」へ変更 + sensitive scope の verification 提出
- 段階分け:
  - Step M-1: Testing → In production（refresh token 7日失効を解消するが、未認証アプリ警告と scope 制限は残る可能性）
  - Step M-2: verification submission（数週間〜1〜2ヶ月の審査）

## 暫定運用策（verification 完了まで）

- 優先1: scripts/db_monitor.py（完了）
- 優先2: Worker マイシフト表示（Phase 2 の後半で設計）
- 優先3: Admin 同期失敗バナー（Phase 2 のさらに後）

## Phase 2 + env 切替（2026-05-31 追記・完了）

Step L 以降を当日に実施。本番ドメインを `shifree.com` へ切替えて OAuth E2E まで成立させた。

### 完了したこと
- Phase 2 コード変更（コミット `7aa39a8`）: `config.py` に `BASE_URL` env 配線、`reminder_service.py` の fallback を `shifree.com` 化、`landing.html`（canonical/OGP/Twitter/JSON-LD）/ `sitemap.xml` / `robots.txt` / `README.md` の公開URLを `shifree.com` 化
- PR #43 を main に **squash merge**（squash commit `e3b778fd11c3ed230770f1cb13032bbfac8defa5`）→ Vercel production 自動デプロイ
- Vercel production env を `shifree.com` 系へ切替（CLI `vercel env`、`printf '%s'` で投入）
  - `GOOGLE_REDIRECT_URI=https://shifree.com/auth/google/callback`
  - `CORS_ALLOWED_ORIGINS=https://shifree.com`
  - `BASE_URL=https://shifree.com`
- 本番再デプロイ（CLI `vercel --prod`）→ 最新 deploy id `dpl_D9zbe66T4oS4oCeaJvhXq3n63PuN` / state READY / commit `e3b778f`
- `shifree.com` 起点の **OAuth E2E 成功**（callback 着地・state エラーなし）
- 自動検証: `/lp` `/privacy` `/terms` が 200、OAuth 開始の `redirect_uri` に改行 `%0A` 混入なし
- Preview / Development の env を復元（Preview は Dashboard 手動）
  - `GOOGLE_REDIRECT_URI`（Preview/Dev）= `https://shifree.vercel.app/auth/google/callback`
  - `CORS_ALLOWED_ORIGINS`（Preview/Dev）= `https://shifree.vercel.app`
- `vercel env ls` で3環境の最終スコープ確認済み

### 失敗と是正（次回のための教訓）
- `echo "..." | vercel env add` は **末尾改行を値に混入**させ、`GOOGLE_REDIRECT_URI` に `%0A` が付いて `redirect_uri_mismatch` 必至だった → `printf '%s'` で再投入・再デプロイして是正
- `vercel env rm GOOGLE_REDIRECT_URI production` が、全環境同値で束ねられた変数を削除し **Preview / Development まで巻き込んで消失** させた → 後から復元
- Preview env は CLI 非対話実行で `git_branch_required` に詰まり、`--value ... --yes` でも「全 Preview ブランチ」指定が通らない → **Dashboard 手動で All Preview Branches 指定**して復元（Sensitive は OFF）

### Preview/Dev の値方針（判断の記録）
- Preview デプロイは動的 URL で配信されるため、`shifree.com` でも `shifree.vercel.app` でも Preview 上の OAuth は実質成立しない（パリティ用の値）
- 当初計画どおり **案1（`shifree.vercel.app`）** で復元。将来 vercel.app を畳む段階で Preview/Dev もまとめて見直す

### 残タスク（次セッション）
1. reminder リンク生成先が `shifree.com` になることの確認
2. `shifree.vercel.app` → `shifree.com` の domain redirect 設計・実施（旧ドメイン起点ログインの救済）
3. 旧 `shifree.vercel.app` の最終整理（Vercel domain / GCP Redirect URI / Authorized domains）
4. Testing → In production（refresh token 7日失効の本丸解消）
5. OAuth verification submission（scope justification / デモ動画シナリオ / sensitive scope 審査）
6. Preview / Development を将来 `shifree.com` に寄せるか判断

### 注意
- production 切替後、旧 `shifree.vercel.app` 起点ログインはクロスドメイン state 不一致で失敗する想定（`SESSION_COOKIE_DOMAIN` 未設定でホスト別スコープ）。domain redirect で `shifree.com` へ寄せて解消する
- 作業ツリーの無関係差分（OAuth 作業に混ぜない）: `docs/incident-2026-04-26-handoff.md` / `docs/archive-from-shift-keisan-app/` / `docs/business/`

## reminder リンク調査 + domain redirect（2026-06-01 追記・完了）

### reminder / 通知リンク生成箇所の調査結果
- 自動リマインダー（cron、`reminder_service.py:120-121`）: `current_app.config.get('BASE_URL', 'https://shifree.com')` 由来 → 本番 **shifree.com 確定**
- admin 起点リンク3経路は `request.host_url` 由来（admin のアクセスドメイン依存）:
  - `api_admin.py:506` 手動の期間公開通知（`submit_url`→`/worker`）
  - `api_admin.py:1160-1161` 招待メール（`invite_url`→`/auth/invite/{token}`）
  - `api_admin.py:1338` 欠員通知（`vacancy_service.py:190-191` の accept/decline URL）
- メールテンプレート（`app/templates/emails/*.html`）は変数のみ・ドメイン直書きなし
- 旧ドメイン（`shifree.vercel.app` / `onrender.com`）のハードコードはコードに無し（`CLAUDE.md` の記述のみ＝意図的保全）
- 残論点: admin が旧 `shifree.vercel.app` を使うと host_url 経由でリンクも vercel.app を指す → domain redirect で入口を寄せて低減（恒久対策は host_url→BASE_URL 統一＝残タスク）

### domain redirect（PR #45 / 完了）
- squash commit: `5c76f82c4037810371025a2b4ce6947b6a1035d3`
- 変更: `vercel.json` に host 条件付き redirect を追加
  - `source: /:path((?!api/).*)` / `has: host == shifree.vercel.app` / `destination: https://shifree.com/:path*` / `permanent: false`（307）
  - `/api/` 除外で cron・同一オリジン API を保護
- 本番 deploy: id `dpl_h7SqZLMPQRJxZdLUzJGSuCzDqu1i` / target production / state READY
- curl 実測（2026-06-01、すべてパス）:
  - `shifree.vercel.app/` `/lp` `/worker` → 307 → `shifree.com/...`（path 保持）
  - `/auth/invite/dummy-token?foo=bar` → 307 で `?foo=bar` 保持
  - `/vacancy/respond?token=dummy-token&action=accept` → 307 で `?token=...&action=accept` 保持
  - `/api/index` → 404（307 でない）＝ `/api/` 除外が機能
  - `shifree.com/` → 302 `/login`（相対） / `/lp` → 200 ＝ redirect loop なし
  - Preview URL（`shifree-<hash>` / `shifree-git-main-…`）→ 401（保護）で redirect されない＝host 完全一致のみ
- 効果: 旧ドメイン起点アクセスが入口で shifree.com に寄り、OAuth state 不一致リスク・admin 起点リンクの vercel.app 化リスクが低下

### 公式仕様の裏取り（Vercel）
- `redirects` は `rewrites`/`routes` より先に処理（vercel.com/docs/project-configuration/vercel-json）
- `has` の `type: host` 正式サポート（build-output-api の `HasField`）
- 負の先読み source は公式例あり（`"/:path((?!uk/).*)"`）
- `has` 条件はローカル `vercel dev` では効かない（＝Development 非対象）

### 残タスク（次セッション）
1. ~~Testing → In production~~ → **完了**（下記セクション参照）
2. OAuth verification submission
3. `api_admin.py` の host_url→BASE_URL 統一（防御的修正候補）
4. 旧 `shifree.vercel.app` の最終整理（In production・verification 安定後）
5. Preview/Dev を将来 shifree.com に寄せるか判断
6. cron 正常実行の観測（次回 09:00 UTC 発火を logs / cron 履歴で確認）

## Testing → In production（2026-06-02 追記・完了）

### 実施前の GCC 目視確認結果
- App name: `shifree`
- User type: External
- Publishing status: テスト中（Testing）
- Homepage: `https://shifree.com/lp` / Privacy: `https://shifree.com/privacy` / Terms: `https://shifree.com/terms`
- Authorized domains: `shifree.com` / `shifree.vercel.app` / `www.googleapis.com`
- OAuth user cap: 15人 / 100人上限（13人がテストユーザー、残り2人）
- Sensitive scopes（GCC 登録済み 3件）:
  - `https://www.googleapis.com/auth/calendar.events`（実施直前に追加登録。コード側では使用済みだが GCC 未登録だった）
  - `https://www.googleapis.com/auth/calendar.events.readonly`
  - `https://www.googleapis.com/auth/calendar.readonly`
- Restricted scopes: なし
- Redirect URIs（4件、handoff 記録と一致）:
  - `https://shifree.com/auth/google/callback`
  - `https://shifree.com/auth/google/callback-link`
  - `https://shifree.vercel.app/auth/google/callback`（残置）
  - `https://shifree.vercel.app/auth/google/callback-link`（残置）
- 旧 Render URI: なし（削除済み確認）
- Client ID 先頭: `739906304418-m6bv...`
- Client Secret: 2本有効（`****KXf0` 2025-07-23 / `****S76w` 2026-03-01）。古い方の無効化は別途検討

### DB ユーザー状況（実施前確認）
- 全ユーザー: 15（admin 1 / owner 1 / worker 13、全員 active）
- Google OAuth 連携: 15/15（全員 google_id・refresh_token あり）
- CREDENTIALS_EXPIRED エントリ: user_id=9（6件）/ user_id=12（1件、種さんと推定）
- Linked Calendar Accounts: 0（未使用）
- 組織数: 1

### Publish App 実施
- 実施日: 2026-06-02
- 操作: Google Auth Platform → 対象 → 「本番環境に push」をクリック
- 結果: Publishing status が **本番環境（In production）** に変更
- GCC 表示: 「アプリの検証が必要です。情報の設定が完了したら、審査のためにアプリを送信してください。」

### E2E 確認結果（Publish App 直後）
- `https://shifree.com` 起点 Google ログイン: **成功**（アカウント: `tatsunoritojo@gmail.com`）
- 未確認アプリ警告: **表示あり**（sensitive scope の verification 未完了のため。想定通り）
- refresh token 保存: **確認済み**（user_id=5 / role=owner / updated_at=2026-06-02 02:40 UTC / token=present）
- `shifree.vercel.app` → `shifree.com` redirect: **動作確認済み**
- OAuth user cap: 15/100（変化なし）

### 解消されたこと
- OAuth consent screen が Testing であることに起因する **refresh token 7日失効問題は In production 化により解消見込み**
- 7日後（2026-06-09 頃）に実際に失効しないことを経過観察で裏取りする

### 残タスク（次セッション以降）
1. **経過観察: 2026-06-09 頃に refresh token 失効しないことを実測確認**
2. Worker の Calendar Free/Busy 取得確認 / Admin の Calendar sync 確認
3. OAuth verification submission（scope justification / デモ動画 / sensitive scope 審査。目安 10営業日）
4. 未確認アプリ警告の解消（verification 完了後に自動消去）
5. `api_admin.py` の host_url→BASE_URL 統一（防御的修正候補）
6. `www.googleapis.com` が Authorized domains に残っている件の整理
7. 旧 `shifree.vercel.app` の最終整理（verification 安定後）
8. Client Secret 2本 → 古い方の無効化検討
9. cron 正常実行の継続観測
