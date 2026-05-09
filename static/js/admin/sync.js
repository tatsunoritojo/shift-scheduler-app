/**
 * Google Calendar 同期: ステータス表示・履歴閲覧・キーワード設定・初回セットアップ
 * ウィザード.
 *
 * 構成:
 *  - Sync Status & Logs: 設定タブ最上段に「最終同期: ...」のステータスバーを表示
 *  - Sync Settings: 同期判定キーワード (例: '営業時間') の設定保存
 *  - Setup Wizard: 初回利用時に Google カレンダー接続を案内する 2 ステップ UI
 *
 * 依存: state.syncKeyword / api / showToast / escapeHtml / setClean
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { state } from './state.js';
import { setClean } from './dirty-tracker.js';

// ---- Sync Status & Logs ----

/**
 * 「設定」タブの最終同期ステータスバーを更新する。レスポンスを返却するので
 * init() 側で初期セットアップ判定に使える。
 */
export async function loadSyncStatus() {
    const container = document.getElementById('sync-status');
    if (!container) return null;
    try {
        const data = await api.get('/api/admin/opening-hours/sync/status');
        if (data.last_sync) {
            const s = data.last_sync;
            const at = new Date(s.performed_at);
            const dateStr = `${at.getMonth() + 1}/${at.getDate()} ${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
            const typeLabel = s.operation_type === 'import' ? 'インポート' : 'エクスポート';
            const rangeLabel = `${s.start_date} 〜 ${s.end_date}`;
            container.innerHTML = `
                <span class="sync-status-icon synced"><i data-lucide="check" style="width:16px;height:16px;"></i></span>
                <span class="sync-status-text">最終同期: <strong>${dateStr}</strong> ${typeLabel} ${rangeLabel}</span>
                <button class="sync-status-link" data-action="showSyncLogs">履歴</button>
            `;
        } else {
            container.innerHTML = `
                <span class="sync-status-icon not-synced"><i data-lucide="minus" style="width:16px;height:16px;"></i></span>
                <span class="sync-status-text">まだ同期されていません</span>
                <button class="sync-status-link" data-action="showSyncLogs">履歴</button>
            `;
        }
        if (window.lucide) lucide.createIcons();
        return data;
    } catch (e) {
        container.innerHTML = '<span style="color:var(--color-neutral-400);font-size:0.9em;">ステータスを取得できませんでした</span>';
        return null;
    }
}

/**
 * 同期履歴ダイアログを開いて過去の import/export ログを表として描画する。
 */
export async function showSyncLogs() {
    try {
        const logs = await api.get('/api/admin/opening-hours/sync/logs');

        const overlay = document.createElement('div');
        overlay.className = 'confirm-dialog-overlay';

        let tableRows = '';
        if (!logs || logs.length === 0) {
            tableRows = '<tr><td colspan="4" style="text-align:center;color:var(--color-neutral-400);padding:20px;">同期履歴はありません</td></tr>';
        } else {
            tableRows = logs.map(log => {
                const at = new Date(log.performed_at);
                const dateStr = `${at.getMonth() + 1}/${at.getDate()} ${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
                const typeLabel = log.operation_type === 'import' ? 'インポート' : 'エクスポート';
                const range = `${log.start_date} 〜 ${log.end_date}`;
                const summary = log.result_summary || {};
                const parts = [];
                if (log.operation_type === 'import') {
                    if (summary.imported) parts.push(`取込${summary.imported}`);
                    if (summary.updated) parts.push(`更新${summary.updated}`);
                    if (summary.skipped) parts.push(`skip${summary.skipped}`);
                } else {
                    if (summary.created) parts.push(`作成${summary.created}`);
                    if (summary.updated) parts.push(`更新${summary.updated}`);
                    if (summary.deleted) parts.push(`削除${summary.deleted}`);
                    if (summary.skipped) parts.push(`skip${summary.skipped}`);
                }
                if (summary.errors && summary.errors.length > 0) parts.push(`err${summary.errors.length}`);
                const summaryStr = parts.join(' / ') || '-';
                return `<tr><td>${dateStr}</td><td><span class="badge ${log.operation_type === 'import' ? 'badge-calendar' : 'badge-manual'}">${typeLabel}</span></td><td>${range}</td><td>${summaryStr}</td></tr>`;
            }).join('');
        }

        overlay.innerHTML = `
            <div class="confirm-dialog" style="max-width:600px;">
                <h3>同期履歴</h3>
                <div style="max-height:400px;overflow-y:auto;">
                    <table class="sync-log-table">
                        <thead><tr><th>日時</th><th>種別</th><th>範囲</th><th>結果</th></tr></thead>
                        <tbody>${tableRows}</tbody>
                    </table>
                </div>
                <div class="confirm-dialog-actions">
                    <button class="btn btn-secondary" id="sync-logs-close">閉じる</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        overlay.querySelector('#sync-logs-close').onclick = () => overlay.remove();
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    } catch (e) {
        showToast('同期履歴の取得に失敗しました', 'error');
    }
}

// ---- Sync Settings ----

/**
 * 同期キーワードを取得して state と DOM を更新する。
 * @returns {Promise<object|null>} 設定データ (calendar_setup_dismissed 等を init で参照)
 */
export async function loadSyncSettings() {
    try {
        const data = await api.get('/api/admin/sync-settings');
        state.syncKeyword = data.calendar_sync_keyword || '営業時間';
        // Update keyword display in UI
        const keywordLabel = document.getElementById('sync-keyword-label');
        if (keywordLabel) keywordLabel.textContent = state.syncKeyword;
        const keywordInput = document.getElementById('sync-keyword-input');
        if (keywordInput) keywordInput.value = state.syncKeyword;
        setClean('sync-keyword');
        return data;
    } catch (e) {
        console.warn('Failed to load sync settings:', e);
        return null;
    }
}

/** 同期キーワードを保存する。 */
export async function saveSyncKeyword() {
    const input = document.getElementById('sync-keyword-input');
    if (!input) return;
    const keyword = input.value.trim();
    if (!keyword) {
        showToast('キーワードを入力してください', 'warning');
        return;
    }
    try {
        await api.put('/api/admin/sync-settings', { calendar_sync_keyword: keyword });
        state.syncKeyword = keyword;
        const keywordLabel = document.getElementById('sync-keyword-label');
        if (keywordLabel) keywordLabel.textContent = state.syncKeyword;
        setClean('sync-keyword');
        showToast('同期キーワードを保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

// ---- Setup Wizard ----

export function showSetupWizard() {
    const wizard = document.getElementById('setup-wizard');
    if (wizard) wizard.style.display = '';
}

export function hideSetupWizard() {
    const wizard = document.getElementById('setup-wizard');
    if (wizard) wizard.style.display = 'none';
}

/** ウィザード Step 1 → 2: Google カレンダー接続テスト. */
export async function wizardConnect() {
    const keyword = document.getElementById('wizard-keyword').value.trim();
    if (!keyword) {
        showToast('キーワードを入力してください', 'warning');
        return;
    }
    const resultEl = document.getElementById('wizard-calendar-result');
    resultEl.innerHTML = '<span style="color:var(--color-neutral-400);">接続テスト中...</span>';
    document.getElementById('wizard-step-1').style.display = 'none';
    document.getElementById('wizard-step-2').style.display = '';

    try {
        const calendars = await api.get('/api/admin/calendars');
        const calNames = calendars.map(c => c.summary || c.id).slice(0, 5).join('、');
        resultEl.innerHTML = `
            <div style="padding:12px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;">
                <strong>Googleカレンダーへの接続を確認しました</strong> — ${calendars.length}件のカレンダーにアクセスできます。<br>
                <span style="font-size:0.85em;color:var(--color-neutral-500);">${calNames}</span>
            </div>
            <p class="mt-8" style="font-size:0.9em;">次のステップで、キーワード「<strong>${escapeHtml(keyword)}</strong>」に一致するイベントの取込を実行します。<br>
            <span style="color:var(--color-neutral-400);font-size:0.9em;">※ 該当イベントが存在するかどうかは、インポート実行後に確認できます。</span></p>
        `;
    } catch (e) {
        resultEl.innerHTML = `
            <div style="padding:12px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;">
                <strong>接続に失敗しました</strong><br>
                <span style="font-size:0.85em;">${escapeHtml(e.message)}</span>
            </div>
            <p class="mt-8" style="font-size:0.9em;">再ログインが必要な場合があります。</p>
        `;
    }
}

export function wizardBack() {
    document.getElementById('wizard-step-1').style.display = '';
    document.getElementById('wizard-step-2').style.display = 'none';
}

/** ウィザード Step 2: 設定を保存しインポートを開始する. */
export async function wizardSave() {
    const keyword = document.getElementById('wizard-keyword').value.trim();
    if (!keyword) return;

    try {
        await api.put('/api/admin/sync-settings', {
            calendar_sync_keyword: keyword,
            calendar_setup_dismissed: true,
        });
        state.syncKeyword = keyword;
        const keywordLabel = document.getElementById('sync-keyword-label');
        if (keywordLabel) keywordLabel.textContent = state.syncKeyword;
        const keywordInput = document.getElementById('sync-keyword-input');
        if (keywordInput) keywordInput.value = state.syncKeyword;
        hideSetupWizard();
        showSyncKeywordCard();
        showToast('カレンダー連携を設定しました。インポートを開始します。', 'success');
        // Auto-trigger import
        document.getElementById('btn-import-hours').click();
    } catch (e) {
        showToast(`設定の保存に失敗しました: ${e.message}`, 'error');
    }
}

/** ウィザード: スキップしてキーワードカードのみ表示する. */
export async function wizardSkip() {
    try {
        await api.put('/api/admin/sync-settings', { calendar_setup_dismissed: true });
    } catch (e) { /* ignore */ }
    hideSetupWizard();
    showSyncKeywordCard();
    showToast('カレンダー連携設定をスキップしました。後から設定できます。', 'info');
}

export function showSyncKeywordCard() {
    const card = document.getElementById('sync-keyword-card');
    if (card) card.style.display = '';
}
