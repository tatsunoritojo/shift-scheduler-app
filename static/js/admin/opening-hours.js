/**
 * 営業時間 (週次) + 例外日 + Google Calendar 同期 (import/export) + プレビュー
 * カレンダー + 例外編集ポップアップを統合したモジュール.
 *
 * UI 構成:
 *   設定タブ
 *     ├ 同期キーワード (sync.js が担当)
 *     ├ Calendar 連携 (export / import) ← exportOpeningHours / importOpeningHours
 *     ├ インポートプレビュー (renderImportPreview / showSettingsDayPopup)
 *     └ 手動設定 <details>
 *         ├ 営業時間 (loadOpeningHours / saveOpeningHours)
 *         └ 例外一覧 (loadExceptions / addException / deleteException)
 *
 * 状態:
 *   state.lastPreviewRange — プレビュー中の日付範囲 (refresh で再描画)
 *   state.exceptionsData    — 例外一覧の最新スナップショット (popup 表示で参照)
 *   state.syncKeyword       — sync.js 側で更新。export/import の確認文に使用
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { showConfirmDialog } from '../modules/ui-dialogs.js';
import { WEEKDAY_NAMES } from '../modules/date-constants.js';
import { formatDate } from '../modules/time-utils.js';
import { state } from './state.js';
import { setClean } from './dirty-tracker.js';
import { switchTab, generatePeriodName } from './tabs.js';
import { loadSyncStatus } from './sync.js';

// ---- Import Preview Calendar ----

/**
 * 期間範囲のプレビューカレンダーを描画。クリック可能なセルから
 * showSettingsDayPopup へ繋がる。state.lastPreviewRange を更新する。
 */
export function renderImportPreview(startDateStr, endDateStr) {
    const container = document.getElementById('import-preview');
    const actionsEl = document.getElementById('import-preview-actions');
    if (!container) return;

    state.lastPreviewRange = { start: startDateStr, end: endDateStr };

    const excMap = {};
    (state.exceptionsData || []).forEach(e => { excMap[e.exception_date] = e; });

    const start = new Date(startDateStr);
    const end = new Date(endDateStr);

    // Iterate month by month
    let html = '';
    let cur = new Date(start.getFullYear(), start.getMonth(), 1);
    const lastMonth = new Date(end.getFullYear(), end.getMonth() + 1, 0);

    while (cur <= lastMonth) {
        const year = cur.getFullYear();
        const month = cur.getMonth();
        html += `<div class="preview-month-title">${year}年${month + 1}月</div>`;
        html += '<div class="preview-calendar-grid">';

        // Header
        WEEKDAY_NAMES.forEach(name => {
            html += `<div class="preview-calendar-header">${name}</div>`;
        });

        // Empty cells before first day
        const firstDow = new Date(year, month, 1).getDay();
        for (let i = 0; i < firstDow; i++) {
            html += '<div class="preview-calendar-cell empty"></div>';
        }

        // Days
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        for (let day = 1; day <= daysInMonth; day++) {
            const d = new Date(year, month, day);
            const dateStr = formatDate(d);
            const inRange = dateStr >= startDateStr && dateStr <= endDateStr;
            const exc = excMap[dateStr];

            let cellClass = 'preview-calendar-cell';
            let timeLabel = '';

            if (!inRange) {
                cellClass += ' out-of-range';
            } else if (exc) {
                if (exc.is_closed) {
                    cellClass += ' preview-closed';
                    timeLabel = '休業';
                } else {
                    cellClass += exc.source === 'calendar' ? ' preview-calendar-source' : ' preview-manual-source';
                    timeLabel = `${exc.start_time}〜${exc.end_time}`;
                }
            } else {
                cellClass += ' preview-default';
            }

            if (inRange) {
                html += `<div class="${cellClass} preview-clickable" data-action="showSettingsDayPopup" data-date="${dateStr}"><div class="preview-day-num">${day}</div>${timeLabel ? `<div class="preview-day-time">${timeLabel}</div>` : ''}</div>`;
            } else {
                html += `<div class="${cellClass}"><div class="preview-day-num">${day}</div></div>`;
            }
        }

        html += '</div>';
        cur = new Date(year, month + 1, 1);
    }

    // Legend
    html += `
        <div class="preview-legend">
            <span class="preview-legend-item"><span class="preview-legend-dot preview-calendar-source"></span>カレンダー取込</span>
            <span class="preview-legend-item"><span class="preview-legend-dot preview-manual-source"></span>手動設定</span>
            <span class="preview-legend-item"><span class="preview-legend-dot preview-closed"></span>休業</span>
            <span class="preview-legend-item"><span class="preview-legend-dot preview-default"></span>曜日デフォルト</span>
        </div>
    `;

    container.innerHTML = html;
    if (actionsEl) actionsEl.style.display = 'flex';
    if (window.lucide) lucide.createIcons();
}

/** 例外操作後にプレビューが見えていれば再描画する。 */
export function refreshPreviewIfVisible() {
    if (state.lastPreviewRange) {
        renderImportPreview(state.lastPreviewRange.start, state.lastPreviewRange.end);
    }
}

/** プレビュー範囲を期間作成フォームに pre-fill して期間タブに遷移する。 */
export function goToCreatePeriod() {
    if (state.lastPreviewRange) {
        const nameField = document.getElementById('period-name');
        const startField = document.getElementById('period-start');
        const endField = document.getElementById('period-end');
        if (nameField && !nameField.value) {
            nameField.value = generatePeriodName(state.lastPreviewRange.start, state.lastPreviewRange.end);
        }
        if (startField && !startField.value) startField.value = state.lastPreviewRange.start;
        if (endField && !endField.value) endField.value = state.lastPreviewRange.end;
    }
    switchTab('periods');
}

/** 同期日付範囲のデフォルト値（翌月 1 日 〜 翌々月末）を設定する。 */
export function initSyncDateRange() {
    const now = new Date();
    const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    const lastDay = new Date(now.getFullYear(), now.getMonth() + 2, 0);
    document.getElementById('sync-start-date').value = formatDate(nextMonth);
    document.getElementById('sync-end-date').value = formatDate(lastDay);
}

// ---- Settings Day Popup ----

/** プレビューカレンダーで日をクリックしたときの設定編集ポップアップ. */
export function showSettingsDayPopup(dateStr) {
    closeSettingsDayPopup();

    const exc = state.exceptionsData.find(e => e.exception_date === dateStr);
    const d = new Date(dateStr);
    const dayLabel = `${d.getMonth() + 1}/${d.getDate()}(${WEEKDAY_NAMES[d.getDay()]})`;

    const sourceLabel = exc
        ? (exc.source === 'calendar' ? 'カレンダー取込' : '手動設定')
        : '曜日デフォルト';
    const sourceBadge = exc
        ? (exc.source === 'calendar' ? 'badge-calendar' : 'badge-manual')
        : 'badge-draft';

    const startVal = exc && !exc.is_closed ? (exc.start_time || '09:00') : '09:00';
    const endVal = exc && !exc.is_closed ? (exc.end_time || '21:00') : '21:00';
    const isClosed = exc ? exc.is_closed : false;
    const reason = exc ? (exc.reason || '') : '';

    const overlay = document.createElement('div');
    overlay.className = 'day-popup-overlay';
    overlay.id = 'settings-day-popup-overlay';
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeSettingsDayPopup();
    });

    const popup = document.createElement('div');
    popup.className = 'day-popup';

    popup.innerHTML = `
        <div class="day-popup-header">
            <span class="day-popup-date">${dayLabel}</span>
            <button class="day-popup-close" data-action="closeSettingsDayPopup">&times;</button>
        </div>
        <div class="day-popup-section">
            <div class="day-popup-label">ステータス</div>
            <span class="badge ${sourceBadge}">${sourceLabel}</span>
        </div>
        <div class="day-popup-section">
            <div class="day-popup-label">営業時間</div>
            <div class="day-popup-time-edit">
                <input type="time" class="form-control popup-time-input" id="settings-popup-start" value="${startVal}">
                <span class="time-separator">〜</span>
                <input type="time" class="form-control popup-time-input" id="settings-popup-end" value="${endVal}">
            </div>
            <label style="display:flex;align-items:center;gap:6px;margin-top:8px;cursor:pointer;">
                <input type="checkbox" id="settings-popup-closed" ${isClosed ? 'checked' : ''}> 休業
            </label>
        </div>
        <div class="day-popup-section">
            <div class="day-popup-label">理由（任意）</div>
            <input type="text" class="form-control" id="settings-popup-reason" value="${reason}" placeholder="例: 祝日、特別営業">
        </div>
        <div class="day-popup-section" style="border-bottom:none;">
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button class="btn btn-primary" data-action="saveSettingsPopup" data-date="${dateStr}" data-exc-id="${exc ? exc.id : 'null'}">
                    <i data-lucide="save" style="width:15px;height:15px;"></i> ${exc ? '更新' : '例外として保存'}
                </button>
                ${exc ? `<button class="btn btn-destructive" data-action="deleteSettingsPopup" data-exc-id="${exc.id}"><i data-lucide="trash-2" style="width:15px;height:15px;"></i> 削除</button>` : ''}
            </div>
        </div>
    `;

    overlay.appendChild(popup);
    document.body.appendChild(overlay);
    if (window.lucide) lucide.createIcons();
    requestAnimationFrame(() => {
        overlay.classList.add('visible');
        popup.classList.add('visible');
    });
}

export function closeSettingsDayPopup() {
    const overlay = document.getElementById('settings-day-popup-overlay');
    if (!overlay) return;
    overlay.classList.remove('visible');
    const popup = overlay.querySelector('.day-popup');
    if (popup) popup.classList.remove('visible');
    setTimeout(() => overlay.remove(), 200);
}

export async function saveSettingsPopup(dateStr, excId) {
    const startTime = document.getElementById('settings-popup-start').value;
    const endTime = document.getElementById('settings-popup-end').value;
    const isClosed = document.getElementById('settings-popup-closed').checked;
    const reason = document.getElementById('settings-popup-reason').value;

    try {
        if (excId) {
            await api.put(`/api/admin/opening-hours/exceptions/${excId}`, {
                start_time: isClosed ? null : startTime,
                end_time: isClosed ? null : endTime,
                is_closed: isClosed,
                reason: reason,
            });
            showToast('更新しました', 'success');
        } else {
            await api.post('/api/admin/opening-hours/exceptions', {
                exception_date: dateStr,
                start_time: isClosed ? null : startTime,
                end_time: isClosed ? null : endTime,
                is_closed: isClosed,
                reason: reason,
            });
            showToast('例外日を追加しました', 'success');
        }
        closeSettingsDayPopup();
        await loadExceptions();
        refreshPreviewIfVisible();
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

export async function deleteSettingsPopup(excId) {
    try {
        await api.delete(`/api/admin/opening-hours/exceptions/${excId}`);
        showToast('削除しました', 'success');
        closeSettingsDayPopup();
        await loadExceptions();
        refreshPreviewIfVisible();
    } catch (e) {
        showToast(`削除に失敗しました: ${e.message}`, 'error');
    }
}

// ---- Opening Hours (週次) ----

export async function loadOpeningHours() {
    const data = await api.get('/api/admin/opening-hours');
    const grid = document.getElementById('opening-hours-grid');

    const rows = [];
    for (let dow = 0; dow < 7; dow++) {
        const existing = data.find(h => h.day_of_week === dow);
        rows.push(`
            <div class="flex gap-8 mb-8" style="align-items:center;">
                <span style="width:40px;font-weight:600;">${WEEKDAY_NAMES[dow]}</span>
                <input type="time" class="form-control oh-start" data-dow="${dow}"
                    value="${existing ? existing.start_time : '09:00'}" style="width:auto;">
                <span>〜</span>
                <input type="time" class="form-control oh-end" data-dow="${dow}"
                    value="${existing ? existing.end_time : '21:00'}" style="width:auto;">
                <label style="display:flex;align-items:center;gap:4px;">
                    <input type="checkbox" class="oh-closed" data-dow="${dow}"
                        ${existing && existing.is_closed ? 'checked' : ''}> 休業
                </label>
            </div>
        `);
    }
    grid.innerHTML = rows.join('');
    setClean('opening-hours');
}

export async function saveOpeningHours() {
    const hours = [];
    for (let dow = 0; dow < 7; dow++) {
        hours.push({
            day_of_week: dow,
            start_time: document.querySelector(`.oh-start[data-dow="${dow}"]`).value,
            end_time: document.querySelector(`.oh-end[data-dow="${dow}"]`).value,
            is_closed: document.querySelector(`.oh-closed[data-dow="${dow}"]`).checked,
        });
    }
    try {
        await api.put('/api/admin/opening-hours', hours);
        setClean('opening-hours');
        showToast('営業時間を保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

// ---- Exceptions (例外日) ----

/**
 * @param {{start: string, end: string}} [highlightRange] 直近 import で取込んだ範囲
 */
export async function loadExceptions(highlightRange) {
    const data = await api.get('/api/admin/opening-hours/exceptions');
    state.exceptionsData = data || [];
    const container = document.getElementById('exceptions-list');

    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:24px;"><p>例外日はまだ設定されていません</p><p class="empty-state-hint">カレンダーからインポートするか、上のフォームから追加してください</p></div>';
        return;
    }

    function isInHighlightRange(dateStr) {
        if (!highlightRange) return false;
        return dateStr >= highlightRange.start && dateStr <= highlightRange.end;
    }

    container.innerHTML = `
        <table class="data-table">
            <thead><tr><th>日付</th><th>時間</th><th>ソース</th><th>理由</th><th></th></tr></thead>
            <tbody>
                ${data.map(e => {
                    const rowClass = isInHighlightRange(e.exception_date) ? ' class="exception-row-new"' : '';
                    const badgeClass = e.source === 'calendar' ? 'badge-calendar' : 'badge-manual';
                    const badgeLabel = e.source === 'calendar' ? 'カレンダー' : '手動';
                    return `
                    <tr${rowClass}>
                        <td>${e.exception_date}</td>
                        <td>${e.is_closed ? '休業' : `${e.start_time}-${e.end_time}`}</td>
                        <td><span class="badge ${badgeClass}">${badgeLabel}</span></td>
                        <td>${escapeHtml(e.reason)}</td>
                        <td><button class="btn btn-destructive" style="padding:4px 12px;font-size:0.85em;"
                            data-action="deleteException" data-id="${e.id}">削除</button></td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>
    `;
}

export async function addException() {
    const data = {
        exception_date: document.getElementById('exc-date').value,
        start_time: document.getElementById('exc-start').value,
        end_time: document.getElementById('exc-end').value,
        is_closed: document.getElementById('exc-closed').checked,
        reason: document.getElementById('exc-reason').value,
    };
    if (!data.exception_date) { showToast('日付を入力してください', 'warning'); return; }
    try {
        await api.post('/api/admin/opening-hours/exceptions', data);
        showToast('例外日を追加しました', 'success');
        await loadExceptions();
        refreshPreviewIfVisible();
    } catch (e) {
        showToast(`追加に失敗しました: ${e.message}`, 'error');
    }
}

export async function deleteException(id) {
    try {
        await api.delete(`/api/admin/opening-hours/exceptions/${id}`);
        showToast('例外日を削除しました', 'success');
        await loadExceptions();
        refreshPreviewIfVisible();
    } catch (e) {
        showToast(`削除に失敗しました: ${e.message}`, 'error');
    }
}

// ---- Calendar Sync (export / import) ----

function formatSyncResult(result, type) {
    const parts = [];
    if (type === 'export') {
        if (result.created) parts.push(`作成: ${result.created}件`);
        if (result.updated) parts.push(`更新: ${result.updated}件`);
        if (result.deleted) parts.push(`削除: ${result.deleted}件`);
        if (result.skipped) parts.push(`スキップ: ${result.skipped}件`);
    } else {
        if (result.imported) parts.push(`取込: ${result.imported}件`);
        if (result.updated) parts.push(`更新: ${result.updated}件`);
        if (result.skipped) parts.push(`スキップ: ${result.skipped}件`);
    }
    if (result.errors && result.errors.length > 0) {
        parts.push(`エラー: ${result.errors.length}件`);
    }
    return parts.join('　');
}

function showSyncResult(result, type) {
    const container = document.getElementById('sync-result');
    const hasErrors = result.errors && result.errors.length > 0;
    const summary = formatSyncResult(result, type);
    const importedCount = (result.imported || 0) + (result.updated || 0);
    const showNextStep = type === 'import' && !hasErrors && importedCount > 0;
    container.style.display = 'block';
    container.innerHTML = `
        <div style="padding:12px;border-radius:8px;background:${hasErrors ? '#fef2f2' : '#f0fdf4'};border:1px solid ${hasErrors ? '#fecaca' : '#bbf7d0'};">
            <strong>${type === 'export' ? 'エクスポート' : 'インポート'}結果:</strong> ${summary}
            ${hasErrors ? `<div style="margin-top:8px;color:#b91c1c;font-size:0.85em;">${result.errors.map(e => `<div>${e.date || e.event || ''}: ${e.error}</div>`).join('')}</div>` : ''}
            ${showNextStep ? `<div style="margin-top:10px;padding:10px 12px;background:var(--color-primary-50);border-radius:6px;font-size:0.88em;color:var(--color-neutral-700);">
                <strong>次のステップ:</strong> 下のプレビューで取込み結果を確認してください。問題なければ「シフト期間」タブへ進みます。
            </div>` : ''}
        </div>
    `;
}

export async function exportOpeningHours() {
    const startDate = document.getElementById('sync-start-date').value;
    const endDate = document.getElementById('sync-end-date').value;
    if (!startDate || !endDate) {
        showToast('開始日と終了日を入力してください', 'warning');
        return;
    }
    showConfirmDialog(
        'エクスポート確認',
        `${startDate} 〜 ${endDate} の営業時間をGoogleカレンダーに書き出します。カレンダー上の既存「${state.syncKeyword}」イベントは更新されます。`,
        'btn-primary', 'エクスポート',
        async () => {
            try {
                showToast('エクスポート中...', 'info');
                const result = await api.post('/api/admin/opening-hours/sync/export', {
                    start_date: startDate,
                    end_date: endDate,
                });
                showSyncResult(result, 'export');
                showToast('エクスポートが完了しました', 'success');
                await loadSyncStatus();
            } catch (e) {
                showToast(`エクスポートに失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

export async function importOpeningHours() {
    const startDate = document.getElementById('sync-start-date').value;
    const endDate = document.getElementById('sync-end-date').value;
    if (!startDate || !endDate) {
        showToast('開始日と終了日を入力してください', 'warning');
        return;
    }
    showConfirmDialog(
        'インポート確認',
        `${startDate} 〜 ${endDate} の「${state.syncKeyword}」イベントをGoogleカレンダーから取込み、例外リストに<strong>保存</strong>します。手動設定済みの日は上書きされません。`,
        'btn-primary', 'インポート',
        async () => {
            try {
                showToast('インポート中...', 'info');
                const result = await api.post('/api/admin/opening-hours/sync/import', {
                    start_date: startDate,
                    end_date: endDate,
                });
                showSyncResult(result, 'import');
                showToast('インポートが完了しました', 'success');
                await loadSyncStatus();
                await loadExceptions({ start: startDate, end: endDate });
                renderImportPreview(startDate, endDate);
            } catch (e) {
                showToast(`インポートに失敗しました: ${e.message}`, 'error');
            }
        }
    );
}
