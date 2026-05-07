/**
 * Admin SPA の共有可変状態。
 *
 * 設計メモ: 旧 admin-app.js は `let X = ...` で 24 個のグローバル変数を宣言し、
 * 全関数からそれを直接読み書きしていた。リファクタリングで機能単位の ES module
 * に分割するためには複数モジュール間で同じ可変状態を共有する仕組みが必要だが、
 * `export let X = ...` は import 側からは read-only binding になり書き換えできない。
 * そのため state を単一オブジェクトに集約し、`state.X = ...` 形式で読み書きする。
 *
 * 各フィールドの初期値は旧宣言行のものをそのまま移管。意味は変えない（PR2 の主旨は
 * 振る舞い不変のリファクタリング）。
 */

export const state = {
    // === セッション・組織共有 ===
    currentUser: null,
    currentOrgName: '',

    // === シフト構築 (builder タブ) ===
    scheduleEntries: [],          // 編集中のシフト割当
    scheduleVersion: null,        // 楽観ロック: 最後に取得した updated_at
    submissionsData: [],          // 期間内の提出
    currentPeriod: null,          // 選択中の期間 { id, name, start_date, end_date }
    dayAggregatedData: {},        // dateStr -> 日次集約データ
    workersData: [],              // ワーカー一覧
    builderLoadGeneration: 0,     // 古い async response のガード
    adminCalendarEvents: [],      // Admin の Google Calendar イベント

    // === シフト期間 (periods タブ) ===
    periodsIncludeArchived: false, // アーカイブ表示トグル
    cachedPeriods: [],             // 期間一覧の最新スナップショット
    editingAnnouncementPeriodId: null, // 募集文面編集中の期間 ID

    // === 営業時間 (settings/opening-hours) ===
    openingHoursData: {},  // dateStr -> { start_time, end_time } | null
    exceptionsData: [],    // 例外日一覧
    lastPreviewRange: null, // インポートプレビューの範囲

    // === Calendar 同期 ===
    syncKeyword: '営業時間', // 同期判定キーワード（settings から読込）

    // === メンバー管理 ===
    membersTabLoaded: false,

    // === 共有モーダル (PNG/PDF 書き出し) ===
    shareModalData: null,  // { period, openingHours, exceptions }

    // === Phase A: レベル / 重複チェック / 最低出勤 設定 ===
    levelSystemState: { enabled: false, tiers: [] },
    overlapCheckState: { enabled: false, scope: 'same_tier' },
    minAttendanceState: {
        mode: 'disabled',
        unit: 'count',
        org_wide_count_per_week: 1,
        org_wide_hours_per_week: 8.0,
        count_drafts: true,
        lookback_periods: 1,
    },

    // === Phase 2a-3 D: 必要人数管理 ===
    staffingDraft: [], // クライアント側の編集中状態 ([{day_of_week, start_time, end_time, required_count}])

    // === Phase A'-1: 承認プロセス設定 ===
    workflowState: {
        approval_required: false,
        owner_count: 0,
        pending_schedules_count: 0,
    },
};
