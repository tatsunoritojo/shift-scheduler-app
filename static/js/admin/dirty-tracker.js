/**
 * 保存ボタンの dirty 追跡ユーティリティ.
 *
 * 各保存ボタンは btn-secondary (白枠) 状態で開始する。ユーザーが追跡対象フォーム
 * を編集すると btn-primary (青) に切替し「保存待ち」を視覚化する。保存成功時や
 * 初回ロード時には btn-secondary に戻る。
 *
 * 旧 admin-app.js では module-private な dirtyTrackers Map を使っていた。
 * リファクタリングで sync / settings 等の保存系モジュールが setClean / setDirty
 * を共通利用する必要があるため、このモジュールに切り出した。
 */

const dirtyTrackers = {};

/**
 * scope 要素内で input/change が発生したら saveBtn を dirty 状態に切替えるよう
 * 登録する。同じ name で再登録すると上書き。scope または saveBtn が null の
 * 場合は no-op (DOM が無いページでの保護)。
 * @param {string} name 一意な識別子 (例: 'reminder', 'opening-hours')
 * @param {Element|null} scope イベントを監視する親要素
 * @param {HTMLButtonElement|null} saveBtn 状態を反映する保存ボタン
 */
export function registerDirtyTracker(name, scope, saveBtn) {
    if (!scope || !saveBtn) return;
    dirtyTrackers[name] = { scope, saveBtn };
    setClean(name);
    scope.addEventListener('input', () => setDirty(name));
    scope.addEventListener('change', () => setDirty(name));
}

/** 保存ボタンを dirty (btn-primary) に切替える。 */
export function setDirty(name) {
    const t = dirtyTrackers[name];
    if (!t) return;
    t.saveBtn.classList.remove('btn-secondary');
    t.saveBtn.classList.add('btn-primary');
    t.saveBtn.dataset.dirty = 'true';
}

/** 保存ボタンを clean (btn-secondary) に戻す。 */
export function setClean(name) {
    const t = dirtyTrackers[name];
    if (!t) return;
    t.saveBtn.classList.remove('btn-primary');
    t.saveBtn.classList.add('btn-secondary');
    t.saveBtn.dataset.dirty = 'false';
}

/**
 * admin.html 内の代表的な保存ボタン × scope の組み合わせを一括登録する。
 * 該当 ID が存在しないボタンはスキップ (idempotent)。
 */
export function initDirtyTrackers() {
    // Each tracker pairs a scope element (usually a .card) with a save button.
    const map = [
        ['sync-keyword',      'sync-keyword-card',       'btn-save-sync-keyword'],
        ['reminder',          null,                      'btn-save-reminder-settings'],
        ['levels',            null,                      'btn-save-level-settings'],
        ['overlap-check',     null,                      'btn-save-overlap-check'],
        ['min-attendance',    null,                      'btn-save-min-attendance'],
        ['staffing',          null,                      'btn-save-staffing'],
        ['workflow',          null,                      'btn-save-workflow'],
        ['opening-hours',     'section-opening-hours',   'btn-save-opening-hours'],
        ['schedule',          'builder-content',         'btn-save-schedule'],
    ];
    for (const [name, scopeId, btnId] of map) {
        const btn = document.getElementById(btnId);
        if (!btn) continue;
        // Fall back to the closest .card of the save button if no explicit scope id.
        const scope = scopeId ? document.getElementById(scopeId) : btn.closest('.card');
        registerDirtyTracker(name, scope, btn);
    }
}
