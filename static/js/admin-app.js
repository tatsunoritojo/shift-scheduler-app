import { api, getCurrentUser } from './modules/api-client.js';
import { showToast } from './modules/notification.js';
import { renderCalendar } from './modules/calendar-grid.js';
import { timeToMinutes, minutesToTime } from './modules/time-utils.js';
import { escapeHtml } from './modules/escape-html.js';
import { showConfirmDialog } from './modules/ui-dialogs.js';
import { isAllDayEvent, getEventsForDate as _getEventsForDate, formatSubmittedAt } from './modules/event-utils.js';

let currentUser = null;
let scheduleEntries = [];  // Current schedule being built
let submissionsData = [];  // period submissions
let openingHoursData = {}; // dateStr -> { start_time, end_time } | null
let currentPeriod = null;  // Selected period object
let dayAggregatedData = {}; // dateStr -> aggregated day info
let workersData = []; // workers list
let builderLoadGeneration = 0; // Guard against stale async responses
let adminCalendarEvents = []; // Google Calendar events for the admin

const WEEKDAY_NAMES = ['日', '月', '火', '水', '木', '金', '土'];

// Worker colors for timeline
const WORKER_COLORS = [
    '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899',
    '#06b6d4', '#f97316', '#78716c', '#64748b', '#84cc16',
];

// --- Sync Status & Logs ---

async function loadSyncStatus() {
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

async function showSyncLogs() {
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
                    <button class="btn btn-outline" id="sync-logs-close">閉じる</button>
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

// --- Import Preview Calendar ---

let exceptionsData = [];

function renderImportPreview(startDateStr, endDateStr) {
    const container = document.getElementById('import-preview');
    const actionsEl = document.getElementById('import-preview-actions');
    if (!container) return;

    lastPreviewRange = { start: startDateStr, end: endDateStr };

    const excMap = {};
    (exceptionsData || []).forEach(e => { excMap[e.exception_date] = e; });

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
            const dateStr = d.toISOString().slice(0, 10);
            const inRange = dateStr >= startDateStr && dateStr <= endDateStr;
            const exc = excMap[dateStr];

            let cellClass = 'preview-calendar-cell';
            let timeLabel = '';

            if (!inRange) {
                cellClass += ' out-of-range';
            } else if (exc) {
                if (exc.is_closed) {
                    cellClass += ' preview-closed';
                    timeLabel = '休校';
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
            <span class="preview-legend-item"><span class="preview-legend-dot preview-closed"></span>休校</span>
            <span class="preview-legend-item"><span class="preview-legend-dot preview-default"></span>曜日デフォルト</span>
        </div>
    `;

    container.innerHTML = html;
    if (actionsEl) actionsEl.style.display = 'flex';
    if (window.lucide) lucide.createIcons();
}

let lastPreviewRange = null;

function refreshPreviewIfVisible() {
    if (lastPreviewRange) {
        renderImportPreview(lastPreviewRange.start, lastPreviewRange.end);
    }
}

function openManualAndScroll(sectionId) {
    const details = document.getElementById('manual-settings-details');
    if (details) {
        details.open = true;
        setTimeout(() => {
            const target = document.getElementById(sectionId);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    }
}

function goToAddException() { openManualAndScroll('section-add-exception'); }
function goToExceptionsList() { openManualAndScroll('section-exceptions-list'); }
function goToOpeningHours() { openManualAndScroll('section-opening-hours'); }

function generatePeriodName(startStr, endStr) {
    return `${startStr}〜${endStr} 自習室シフト`;
}

function goToCreatePeriod() {
    // Pre-fill period form from preview range
    if (lastPreviewRange) {
        const nameField = document.getElementById('period-name');
        const startField = document.getElementById('period-start');
        const endField = document.getElementById('period-end');
        if (nameField && !nameField.value) {
            nameField.value = generatePeriodName(lastPreviewRange.start, lastPreviewRange.end);
        }
        if (startField && !startField.value) startField.value = lastPreviewRange.start;
        if (endField && !endField.value) endField.value = lastPreviewRange.end;
    }
    switchTab('periods');
}

function initSyncDateRange() {
    const now = new Date();
    const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    const lastDay = new Date(now.getFullYear(), now.getMonth() + 2, 0);
    const fmt = d => d.toISOString().slice(0, 10);
    document.getElementById('sync-start-date').value = fmt(nextMonth);
    document.getElementById('sync-end-date').value = fmt(lastDay);
}

// --- Settings Day Popup ---

function showSettingsDayPopup(dateStr) {
    closeSettingsDayPopup();

    const exc = exceptionsData.find(e => e.exception_date === dateStr);
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
            <div class="day-popup-label">開校時間</div>
            <div class="day-popup-time-edit">
                <input type="time" class="form-control popup-time-input" id="settings-popup-start" value="${startVal}">
                <span class="time-separator">〜</span>
                <input type="time" class="form-control popup-time-input" id="settings-popup-end" value="${endVal}">
            </div>
            <label style="display:flex;align-items:center;gap:6px;margin-top:8px;cursor:pointer;">
                <input type="checkbox" id="settings-popup-closed" ${isClosed ? 'checked' : ''}> 休校
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
                ${exc ? `<button class="btn btn-danger" data-action="deleteSettingsPopup" data-exc-id="${exc.id}"><i data-lucide="trash-2" style="width:15px;height:15px;"></i> 削除</button>` : ''}
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

function closeSettingsDayPopup() {
    const overlay = document.getElementById('settings-day-popup-overlay');
    if (!overlay) return;
    overlay.classList.remove('visible');
    const popup = overlay.querySelector('.day-popup');
    if (popup) popup.classList.remove('visible');
    setTimeout(() => overlay.remove(), 200);
}

async function saveSettingsPopup(dateStr, excId) {
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

async function deleteSettingsPopup(excId) {
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

function setupStaticHandlers() {
    document.getElementById('btn-logout').addEventListener('click', () => {
        location.href = '/auth/logout';
    });

    // Tab buttons
    document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Sync buttons
    document.getElementById('btn-import-hours').addEventListener('click', () => importOpeningHours());
    document.getElementById('btn-export-hours').addEventListener('click', () => exportOpeningHours());

    // Preview action buttons
    document.getElementById('btn-go-create-period').addEventListener('click', () => goToCreatePeriod());
    document.getElementById('btn-go-add-exception').addEventListener('click', () => goToAddException());
    document.getElementById('btn-go-exceptions-list').addEventListener('click', () => goToExceptionsList());
    document.getElementById('btn-go-opening-hours').addEventListener('click', () => goToOpeningHours());

    // Manual settings
    document.getElementById('btn-save-opening-hours').addEventListener('click', () => saveOpeningHours());
    document.getElementById('btn-add-exception').addEventListener('click', () => addException());

    // Periods
    document.getElementById('btn-create-period').addEventListener('click', () => createPeriod());

    // Builder
    document.getElementById('builder-period-select').addEventListener('change', () => loadBuilderData());
    document.getElementById('btn-save-schedule').addEventListener('click', () => saveSchedule());
    document.getElementById('btn-submit-approval').addEventListener('click', () => submitForApproval());
    document.getElementById('confirm-btn').addEventListener('click', () => confirmSchedule());
    document.getElementById('btn-refresh-builder').addEventListener('click', () => loadBuilderData());

    // Members tab
    const btnGenerate = document.getElementById('btn-generate-invite-code');
    if (btnGenerate) btnGenerate.addEventListener('click', () => generateInviteCode());
    const btnRegenerate = document.getElementById('btn-regenerate-invite-code');
    if (btnRegenerate) btnRegenerate.addEventListener('click', () => generateInviteCode());
    const btnCopy = document.getElementById('btn-copy-invite-url');
    if (btnCopy) btnCopy.addEventListener('click', () => copyInviteUrl());
    const enableToggle = document.getElementById('invite-code-enabled-toggle');
    if (enableToggle) enableToggle.addEventListener('change', (e) => toggleInviteCode(e.target.checked));
    const btnCreateInvitation = document.getElementById('btn-create-invitation');
    if (btnCreateInvitation) btnCreateInvitation.addEventListener('click', () => createInvitation());

    // Reminder settings
    const btnSaveReminder = document.getElementById('btn-save-reminder-settings');
    if (btnSaveReminder) btnSaveReminder.addEventListener('click', () => saveReminderSettings());
}

function setupDelegatedHandlers() {
    // Click delegation for dynamically generated elements
    document.addEventListener('click', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;
        const action = target.dataset.action;
        switch (action) {
            case 'showSyncLogs': showSyncLogs(); break;
            case 'showSettingsDayPopup': showSettingsDayPopup(target.dataset.date); break;
            case 'closeSettingsDayPopup': closeSettingsDayPopup(); break;
            case 'saveSettingsPopup': saveSettingsPopup(target.dataset.date, target.dataset.excId === 'null' ? null : Number(target.dataset.excId)); break;
            case 'deleteSettingsPopup': deleteSettingsPopup(Number(target.dataset.excId)); break;
            case 'deleteException': deleteException(Number(target.dataset.id)); break;
            case 'updatePeriodStatus': updatePeriodStatus(Number(target.dataset.id), target.dataset.status); break;
            case 'closeAdminDayPopup': closeAdminDayPopup(); break;
            case 'toggleWorkerAssignment': toggleWorkerAssignment(Number(target.dataset.userId), target.dataset.date); break;
            case 'revokeInvitation': revokeInvitation(Number(target.dataset.id)); break;
            case 'removeMember': removeMember(Number(target.dataset.id), target.dataset.name); break;
            case 'openVacancyDialog': openVacancyDialog(Number(target.dataset.entryId)); break;
            case 'cancelVacancy': cancelVacancy(Number(target.dataset.id)); break;
            case 'sendPeriodReminder': sendPeriodReminder(Number(target.dataset.periodId)); break;
        }
    });

    // Change delegation for dynamically generated time inputs
    document.addEventListener('change', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;
        if (target.dataset.action === 'applyWorkerTime') {
            applyWorkerTime(Number(target.dataset.userId), target.dataset.date);
        }
        if (target.dataset.action === 'changeMemberRole') {
            changeMemberRole(Number(target.dataset.memberId), target.value);
        }
    });
}

// --- Members Tab ---

let membersTabLoaded = false;

async function loadMembersTab() {
    if (membersTabLoaded) return;
    membersTabLoaded = true;
    await Promise.all([loadInviteCode(), loadInvitations(), loadMembers()]);
    if (window.lucide) lucide.createIcons();
}

async function loadInviteCode() {
    try {
        const data = await api.get('/api/admin/invite-code');
        if (data.invite_code) {
            const baseUrl = window.location.origin;
            const url = `${baseUrl}/invite?code=${data.invite_code}`;
            document.getElementById('invite-url-display').value = url;
            document.getElementById('invite-code-enabled-toggle').checked = data.invite_code_enabled;
            document.getElementById('invite-code-content').style.display = '';
            document.getElementById('invite-code-empty').style.display = 'none';
            renderQRCode(url);
        } else {
            document.getElementById('invite-code-content').style.display = 'none';
            document.getElementById('invite-code-empty').style.display = '';
        }
    } catch (e) {
        console.error('Failed to load invite code:', e);
    }
}

function renderQRCode(url) {
    const container = document.getElementById('invite-qr-code');
    if (!container || typeof qrcode === 'undefined') return;
    container.innerHTML = '';
    try {
        const qr = qrcode(0, 'M');
        qr.addData(url);
        qr.make();
        container.innerHTML = qr.createSvgTag(4, 0);
    } catch (e) {
        container.innerHTML = '<span style="color:var(--color-neutral-400);font-size:0.85em;">QRコード生成エラー</span>';
    }
}

async function generateInviteCode() {
    try {
        await api.post('/api/admin/invite-code');
        showToast('招待コードを生成しました', 'success');
        membersTabLoaded = false;
        await loadMembersTab();
    } catch (e) {
        showToast(`生成に失敗しました: ${e.message}`, 'error');
    }
}

function copyInviteUrl() {
    const input = document.getElementById('invite-url-display');
    if (!input || !input.value) return;
    navigator.clipboard.writeText(input.value).then(
        () => showToast('リンクをコピーしました', 'success'),
        () => showToast('コピーに失敗しました', 'error')
    );
}

async function toggleInviteCode(enabled) {
    try {
        await api.put('/api/admin/invite-code', { enabled });
        showToast(enabled ? '招待リンクを有効にしました' : '招待リンクを無効にしました', 'success');
    } catch (e) {
        showToast(`更新に失敗しました: ${e.message}`, 'error');
        // Revert toggle
        document.getElementById('invite-code-enabled-toggle').checked = !enabled;
    }
}

async function loadInvitations() {
    try {
        const data = await api.get('/api/admin/invitations');
        const container = document.getElementById('invitations-table');
        if (!data || data.length === 0) {
            container.innerHTML = '<p style="color:var(--color-neutral-400);font-size:0.9em;">招待はありません</p>';
            return;
        }
        const ROLE_LABELS = { admin: '管理者', owner: '事業主', worker: 'アルバイト' };
        const rows = data.map(t => {
            const valid = t.is_valid;
            const status = t.used_at ? '使用済み' : (valid ? '有効' : '期限切れ');
            const statusColor = t.used_at ? 'var(--color-neutral-400)' : (valid ? 'var(--color-success, #22c55e)' : 'var(--color-error, #ef4444)');
            const expires = t.expires_at ? new Date(t.expires_at).toLocaleString('ja-JP') : '-';
            return `<tr>
                <td>${escapeHtml(t.email || '(制限なし)')}</td>
                <td>${ROLE_LABELS[t.role] || t.role}</td>
                <td style="color:${statusColor}">${status}</td>
                <td style="font-size:0.85em;">${expires}</td>
                <td>${valid && !t.used_at ? `<button class="btn btn-outline btn-sm" data-action="revokeInvitation" data-id="${t.id}" title="取消"><i data-lucide="x" style="width:13px;height:13px;"></i></button>` : ''}</td>
            </tr>`;
        }).join('');
        container.innerHTML = `<table class="data-table" style="width:100%;font-size:0.9em;">
            <thead><tr><th>メール</th><th>ロール</th><th>状態</th><th>有効期限</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    } catch (e) {
        console.error('Failed to load invitations:', e);
    }
}

async function createInvitation() {
    const email = document.getElementById('invitation-email').value.trim();
    const role = document.getElementById('invitation-role').value;
    const expiresHours = parseInt(document.getElementById('invitation-expires').value, 10) || 72;
    const body = { role, expires_hours: expiresHours };
    if (email) body.email = email;
    try {
        const result = await api.post('/api/admin/invitations', body);
        showToast('招待を作成しました', 'success');
        document.getElementById('invitation-email').value = '';
        await loadInvitations();
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        showToast(`招待の作成に失敗しました: ${e.message}`, 'error');
    }
}

async function revokeInvitation(id) {
    showConfirmDialog(
        '招待を取り消しますか？',
        '取り消すと、このリンクは使えなくなります。',
        'btn-danger',
        '取り消す',
        async () => {
            try {
                await api.delete(`/api/admin/invitations/${id}`);
                showToast('招待を取り消しました', 'success');
                await loadInvitations();
                if (window.lucide) lucide.createIcons();
            } catch (e) {
                showToast(`取消に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

async function loadMembers() {
    try {
        const data = await api.get('/api/admin/members');
        const container = document.getElementById('members-table');
        if (!data || data.length === 0) {
            container.innerHTML = '<p style="color:var(--color-neutral-400);font-size:0.9em;">メンバーはいません</p>';
            return;
        }
        const ROLE_LABELS = { admin: '管理者', owner: '事業主', worker: 'アルバイト' };
        const rows = data.map(m => {
            const isSelf = currentUser && m.user_id === currentUser.id;
            const joined = m.joined_at ? new Date(m.joined_at).toLocaleDateString('ja-JP') : '-';
            return `<tr>
                <td>${escapeHtml(m.user_name || '-')}</td>
                <td style="font-size:0.85em;">${escapeHtml(m.user_email || '-')}</td>
                <td>
                    <select class="form-control" style="width:auto;padding:4px 8px;font-size:0.85em;" data-action="changeMemberRole" data-member-id="${m.id}" ${isSelf ? 'disabled' : ''}>
                        ${['admin', 'owner', 'worker'].map(r => `<option value="${r}" ${m.role === r ? 'selected' : ''}>${ROLE_LABELS[r]}</option>`).join('')}
                    </select>
                </td>
                <td style="font-size:0.85em;">${joined}</td>
                <td>${!isSelf ? `<button class="btn btn-outline btn-sm" data-action="removeMember" data-id="${m.id}" data-name="${escapeHtml(m.user_name || m.user_email || '')}" title="除外"><i data-lucide="user-x" style="width:13px;height:13px;"></i></button>` : ''}</td>
            </tr>`;
        }).join('');
        container.innerHTML = `<table class="data-table" style="width:100%;font-size:0.9em;">
            <thead><tr><th>名前</th><th>メール</th><th>ロール</th><th>参加日</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    } catch (e) {
        console.error('Failed to load members:', e);
    }
}

async function changeMemberRole(memberId, newRole) {
    try {
        await api.put(`/api/admin/members/${memberId}/role`, { role: newRole });
        showToast('ロールを変更しました', 'success');
    } catch (e) {
        showToast(`ロール変更に失敗しました: ${e.message}`, 'error');
        await loadMembers();
        if (window.lucide) lucide.createIcons();
    }
}

async function removeMember(id, name) {
    showConfirmDialog(
        `${name || 'このメンバー'} を除外しますか？`,
        '除外すると、このユーザーは組織にアクセスできなくなります。',
        'btn-danger',
        '除外する',
        async () => {
            try {
                await api.delete(`/api/admin/members/${id}`);
                showToast('メンバーを除外しました', 'success');
                await loadMembers();
                if (window.lucide) lucide.createIcons();
            } catch (e) {
                showToast(`除外に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

async function init() {
    setupStaticHandlers();
    setupDelegatedHandlers();
    try {
        currentUser = await getCurrentUser();
        document.getElementById('user-name').textContent = currentUser.display_name || currentUser.email;
        initSyncDateRange();
        const [statusData] = await Promise.all([
            loadSyncStatus(),
            loadOpeningHours(),
            loadExceptions(),
            loadPeriods(),
            loadReminderSettings(),
        ]);
        // Show preview calendar based on calendar exceptions range
        if (statusData && statusData.calendar_exceptions && statusData.calendar_exceptions.count > 0) {
            renderImportPreview(
                statusData.calendar_exceptions.min_date,
                statusData.calendar_exceptions.max_date
            );
        }
    } catch (e) {
        console.error('Init error:', e);
    }
}

// --- Tab switching ---
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    if (tabName === 'builder') {
        loadBuilderPeriodSelect();
        loadChangeLog();
        loadVacancies();
    }
    if (tabName === 'members') loadMembersTab();
}

// --- Opening Hours ---
async function loadOpeningHours() {
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
                        ${existing && existing.is_closed ? 'checked' : ''}> 休校
                </label>
            </div>
        `);
    }
    grid.innerHTML = rows.join('');
}

async function saveOpeningHours() {
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
        showToast('開校時間を保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

// --- Exceptions ---
async function loadExceptions(highlightRange) {
    const data = await api.get('/api/admin/opening-hours/exceptions');
    exceptionsData = data || [];
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
                        <td>${e.is_closed ? '休校' : `${e.start_time}-${e.end_time}`}</td>
                        <td><span class="badge ${badgeClass}">${badgeLabel}</span></td>
                        <td>${escapeHtml(e.reason)}</td>
                        <td><button class="btn btn-danger" style="padding:4px 12px;font-size:0.85em;"
                            data-action="deleteException" data-id="${e.id}">削除</button></td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>
    `;
}

async function addException() {
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

async function deleteException(id) {
    try {
        await api.delete(`/api/admin/opening-hours/exceptions/${id}`);
        showToast('例外日を削除しました', 'success');
        await loadExceptions();
        refreshPreviewIfVisible();
    } catch (e) {
        showToast(`削除に失敗しました: ${e.message}`, 'error');
    }
}

// --- Opening Hours Calendar Sync ---

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

async function exportOpeningHours() {
    const startDate = document.getElementById('sync-start-date').value;
    const endDate = document.getElementById('sync-end-date').value;
    if (!startDate || !endDate) {
        showToast('開始日と終了日を入力してください', 'warning');
        return;
    }
    showConfirmDialog(
        'エクスポート確認',
        `${startDate} 〜 ${endDate} の開校時間をGoogleカレンダーに書き出します。カレンダー上の既存「開校時間」イベントは更新されます。`,
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

async function importOpeningHours() {
    const startDate = document.getElementById('sync-start-date').value;
    const endDate = document.getElementById('sync-end-date').value;
    if (!startDate || !endDate) {
        showToast('開始日と終了日を入力してください', 'warning');
        return;
    }
    showConfirmDialog(
        'インポート確認',
        `${startDate} 〜 ${endDate} の「開校時間」イベントをGoogleカレンダーから取込み、例外リストに<strong>保存</strong>します。手動設定済みの日は上書きされません。`,
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

// --- Periods ---
async function loadPeriods() {
    const data = await api.get('/api/admin/periods');
    const container = document.getElementById('periods-table-container');

    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>シフト期間はまだありません</p><p class="empty-state-hint">上のフォームから新しいシフト期間を作成してください</p></div>';
        return;
    }

    const statusLabels = {
        draft: '下書き', open: '募集中', closed: '締切', finalized: '確定済',
    };

    container.innerHTML = `
        <table class="data-table">
            <thead><tr><th>名前</th><th>期間</th><th>ステータス</th><th>操作</th></tr></thead>
            <tbody>
                ${data.map(p => `
                    <tr>
                        <td>${escapeHtml(p.name)}</td>
                        <td>${p.start_date} 〜 ${p.end_date}</td>
                        <td><span class="badge badge-${p.status}">${statusLabels[p.status] || p.status}</span></td>
                        <td>
                            ${p.status === 'draft' ? `<button class="btn btn-primary" style="padding:4px 12px;font-size:0.85em;" data-action="updatePeriodStatus" data-id="${p.id}" data-status="open">募集開始</button>` : ''}
                            ${p.status === 'open' ? `<button class="btn btn-warning" style="padding:4px 12px;font-size:0.85em;" data-action="updatePeriodStatus" data-id="${p.id}" data-status="closed">締切</button>` : ''}
                            ${p.status === 'open' ? `<button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;" data-action="sendPeriodReminder" data-period-id="${p.id}" title="未提出者にリマインド送信"><i data-lucide="bell" style="width:13px;height:13px;"></i> リマインド</button>` : ''}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function createPeriod() {
    const data = {
        name: document.getElementById('period-name').value,
        start_date: document.getElementById('period-start').value,
        end_date: document.getElementById('period-end').value,
        status: document.getElementById('period-status').value,
        submission_deadline: document.getElementById('period-deadline').value || null,
    };
    if (!data.name || !data.start_date || !data.end_date) {
        showToast('名前と期間を入力してください', 'warning');
        return;
    }
    try {
        await api.post('/api/admin/periods', data);
        showToast('シフト期間を作成しました', 'success');
        await loadPeriods();
    } catch (e) {
        showToast(`作成に失敗しました: ${e.message}`, 'error');
    }
}

async function updatePeriodStatus(id, status) {
    try {
        await api.put(`/api/admin/periods/${id}`, { status });
        showToast('ステータスを更新しました', 'success');
        await loadPeriods();
    } catch (e) {
        showToast(`更新に失敗しました: ${e.message}`, 'error');
    }
}

// --- Builder ---
async function loadBuilderPeriodSelect() {
    const periods = await api.get('/api/admin/periods');
    const select = document.getElementById('builder-period-select');
    select.innerHTML = '<option value="">選択してください</option>' +
        periods.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (${p.start_date} 〜 ${p.end_date})</option>`).join('');
}

async function loadBuilderData() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) {
        document.getElementById('builder-content').style.display = 'none';
        updateBuilderPeriodTitle(null);
        return;
    }

    // Close any open popup before switching
    closeAdminDayPopup();

    const thisGeneration = ++builderLoadGeneration;

    document.getElementById('builder-content').style.display = 'block';

    // Find the period object from the select option text
    const select = document.getElementById('builder-period-select');
    const opt = select.options[select.selectedIndex];
    // Parse dates from option text: "name (YYYY-MM-DD 〜 YYYY-MM-DD)"
    const match = opt.textContent.match(/(\d{4}-\d{2}-\d{2})\s*〜\s*(\d{4}-\d{2}-\d{2})/);
    const periodName = opt.textContent.replace(/\s*\(.*$/, '');
    currentPeriod = match ? { id: periodId, name: periodName, start_date: match[1], end_date: match[2] } : null;

    updateBuilderPeriodTitle(currentPeriod);

    try {
        // Fetch calendar events in parallel with other data
        const calEventsPromise = api.get(`/api/calendar/events?startDate=${currentPeriod.start_date}&endDate=${currentPeriod.end_date}&calendarId=primary`)
            .catch(err => { console.warn('カレンダーイベント取得失敗:', err); return []; });

        const [submissions, schedule, workers, openingHours, calEvents] = await Promise.all([
            api.get(`/api/admin/periods/${periodId}/submissions`),
            api.get(`/api/admin/periods/${periodId}/schedule`),
            api.get('/api/admin/workers'),
            api.get(`/api/admin/periods/${periodId}/opening-hours`),
            calEventsPromise,
        ]);

        // Guard: discard stale response if user switched periods during fetch
        if (thisGeneration !== builderLoadGeneration) return;

        submissionsData = submissions || [];
        workersData = workers || [];
        scheduleEntries = schedule && schedule.entries ? schedule.entries : [];
        openingHoursData = openingHours || {};
        adminCalendarEvents = calEvents || [];

        // Show confirm button if schedule is approved
        if (schedule && schedule.status === 'approved') {
            document.getElementById('confirm-btn').style.display = 'inline-block';
        } else {
            document.getElementById('confirm-btn').style.display = 'none';
        }

        renderSubmissionsSummary(submissions);
        buildDayAggregatedData();
        renderBuilderCalendar();
        renderHoursSummary();
    } catch (e) {
        if (thisGeneration !== builderLoadGeneration) return;
        showToast('データの読み込みに失敗しました', 'error');
    }
}

// --- Aggregation ---

function buildDayAggregatedData() {
    dayAggregatedData = {};
    if (!currentPeriod) return;

    const start = new Date(currentPeriod.start_date);
    const end = new Date(currentPeriod.end_date);

    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const dateStr = d.toISOString().slice(0, 10);
        const oh = openingHoursData[dateStr];
        const closed = !oh || oh.is_closed;

        // Build per-worker info for this date
        const workers = [];
        (submissionsData || []).forEach(sub => {
            const slot = (sub.slots || []).find(s => s.slot_date === dateStr);
            const isAvailable = slot && slot.is_available;
            const entry = scheduleEntries.find(e => e.user_id === sub.user_id && e.shift_date === dateStr);
            workers.push({
                user_id: sub.user_id,
                user_name: sub.user_name || sub.user_email || `User ${sub.user_id}`,
                is_available: !!isAvailable,
                start_time: slot ? slot.start_time : null,
                end_time: slot ? slot.end_time : null,
                is_assigned: !!entry,
                entry_id: entry ? entry.id : null,
                assigned_start: entry ? entry.start_time : null,
                assigned_end: entry ? entry.end_time : null,
            });
        });

        const availableCount = workers.filter(w => w.is_available).length;
        const assignedCount = workers.filter(w => w.is_assigned).length;

        dayAggregatedData[dateStr] = {
            closed,
            openingHours: oh,
            workers,
            availableCount,
            assignedCount,
        };
    }
}

// --- Period Title ---

function updateBuilderPeriodTitle(period) {
    let el = document.getElementById('builder-period-title');
    if (!el) {
        const container = document.getElementById('builder-content');
        if (!container) return;
        el = document.createElement('div');
        el.id = 'builder-period-title';
        container.insertBefore(el, container.firstChild);
    }
    if (period) {
        el.innerHTML = `<div class="guide-box" style="padding:12px 20px;margin-bottom:16px;"><strong style="font-size:1.05em;">${escapeHtml(period.name)}</strong><span style="margin-left:12px;color:var(--color-neutral-500);font-size:0.9em;">${period.start_date} 〜 ${period.end_date}</span></div>`;
    } else {
        el.innerHTML = '';
    }
}

// --- Calendar Rendering ---

function renderBuilderCalendar() {
    const container = document.getElementById('calendar-container');
    if (!currentPeriod) {
        container.innerHTML = '<p style="color:#999;">期間が選択されていません</p>';
        return;
    }

    renderCalendar(container, currentPeriod.start_date, currentPeriod.end_date, dayAggregatedData, {
        renderDayContent(cell, dateStr, data) {
            // Remove default styles, add admin-specific class
            cell.classList.add('admin-calendar-day');
            if (data.closed) {
                cell.classList.add('admin-day-closed');
            } else if (data.availableCount === 0) {
                cell.classList.add('admin-day-nobody');
            } else if (data.assignedCount === 0) {
                cell.classList.add('admin-day-empty');
            } else if (data.assignedCount < data.availableCount) {
                cell.classList.add('admin-day-partial');
            } else {
                cell.classList.add('admin-day-full');
            }

            // Badge: assigned/available
            if (!data.closed) {
                const badge = document.createElement('div');
                badge.className = 'admin-day-badge';
                badge.textContent = `${data.assignedCount}/${data.availableCount}`;
                cell.appendChild(badge);
            }

            // Opening hours text
            if (!data.closed && data.openingHours) {
                const hours = document.createElement('div');
                hours.className = 'admin-day-hours';
                hours.textContent = `${data.openingHours.start_time}-${data.openingHours.end_time}`;
                cell.appendChild(hours);
            }

            if (data.closed) {
                const closedLabel = document.createElement('div');
                closedLabel.className = 'admin-day-hours';
                closedLabel.textContent = '休校';
                closedLabel.style.color = '#999';
                cell.appendChild(closedLabel);
            }
        },
        onDayClick(dateStr, data) {
            if (!data.closed) {
                showAdminDayPopup(dateStr, data);
            }
        },
    });
}

// --- Calendar Event Helpers ---

function getEventsForDate(dateStr) {
    return _getEventsForDate(adminCalendarEvents, dateStr);
}

function renderAdminEventsSection(dateStr) {
    const events = getEventsForDate(dateStr);
    if (events.length === 0) {
        return '<div class="day-popup-no-events">この日の予定はありません</div>';
    }

    const allDayEvents = events.filter(isAllDayEvent);
    const timedEvents = events.filter(e => !isAllDayEvent(e));
    const sorted = [...allDayEvents, ...timedEvents];

    let html = '<div class="day-popup-events">';
    for (const event of sorted) {
        if (isAllDayEvent(event)) {
            html += `
                <div class="event-chip event-chip-allday">
                    <span class="event-chip-title">${escapeHtml(event.summary || 'No Title')}</span>
                    <span class="event-chip-time">終日</span>
                </div>
            `;
        } else {
            const startTime = (event.start || '').substring(11, 16) || '';
            const endTime = (event.end || '').substring(11, 16) || '';
            html += `
                <div class="event-chip event-chip-timed">
                    <span class="event-chip-time">${startTime} - ${endTime}</span>
                    <span class="event-chip-title">${escapeHtml(event.summary || 'No Title')}</span>
                </div>
            `;
        }
    }
    html += '</div>';
    return html;
}

// --- Day Popup ---

function showAdminDayPopup(dateStr, data) {
    // Remove existing popup if any
    closeAdminDayPopup();

    const d = new Date(dateStr);
    const dayLabel = `${d.getMonth() + 1}/${d.getDate()}(${WEEKDAY_NAMES[d.getDay()]})`;

    const overlay = document.createElement('div');
    overlay.className = 'day-popup-overlay';
    overlay.id = 'admin-day-popup-overlay';
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeAdminDayPopup();
    });

    const popup = document.createElement('div');
    popup.className = 'day-popup admin-day-popup';

    // Header
    popup.innerHTML = `
        <div class="day-popup-header">
            <span class="day-popup-date">${dayLabel}</span>
            <button class="day-popup-close" data-action="closeAdminDayPopup">&times;</button>
        </div>
    `;

    // Opening hours section
    if (data.openingHours) {
        const section = document.createElement('div');
        section.className = 'day-popup-section';
        section.innerHTML = `
            <div class="day-popup-label">開校時間</div>
            <div class="day-popup-opening-hours">${data.openingHours.start_time} 〜 ${data.openingHours.end_time}</div>
        `;
        popup.appendChild(section);
    }

    // Calendar events section
    const eventsForDay = getEventsForDate(dateStr);
    if (eventsForDay.length > 0) {
        const evSection = document.createElement('div');
        evSection.className = 'day-popup-section';
        evSection.innerHTML = `<div class="day-popup-label">Googleカレンダー予定 (${eventsForDay.length}件)</div>` + renderAdminEventsSection(dateStr);
        popup.appendChild(evSection);
    }

    // Coverage timeline section
    const tlSection = document.createElement('div');
    tlSection.className = 'day-popup-section';
    tlSection.innerHTML = `<div class="day-popup-label">カバレッジ</div>`;
    const tlContainer = document.createElement('div');
    tlContainer.id = 'admin-coverage-timeline';
    tlSection.appendChild(tlContainer);
    popup.appendChild(tlSection);
    renderAdminCoverageTimeline(dateStr, data, tlContainer);

    // Workers section
    const workersSection = document.createElement('div');
    workersSection.className = 'day-popup-section';
    workersSection.innerHTML = `<div class="day-popup-label">スタッフ (${data.assignedCount}/${data.availableCount})</div>`;
    const workerList = document.createElement('div');
    workerList.className = 'admin-worker-list';
    workerList.id = 'admin-worker-list';

    data.workers.forEach((w, idx) => {
        const card = createWorkerCard(w, dateStr, idx);
        workerList.appendChild(card);
    });

    workersSection.appendChild(workerList);
    popup.appendChild(workersSection);

    overlay.appendChild(popup);
    document.body.appendChild(overlay);

    // Animate in
    requestAnimationFrame(() => {
        overlay.classList.add('visible');
        popup.classList.add('visible');
    });
}

function createWorkerCard(worker, dateStr, idx) {
    const card = document.createElement('div');
    card.className = 'admin-worker-card';
    card.dataset.userId = worker.user_id;

    if (!worker.is_available) {
        card.classList.add('admin-worker-card-unavailable');
    } else if (worker.is_assigned) {
        card.classList.add('admin-worker-card-assigned');
    }

    const color = WORKER_COLORS[idx % WORKER_COLORS.length];

    let html = `
        <div class="admin-worker-card-header">
            <div style="display:flex;align-items:center;gap:8px;">
                <span class="admin-worker-dot" style="background:${color};"></span>
                <span class="admin-worker-name">${escapeHtml(worker.user_name)}</span>
            </div>
    `;

    if (worker.is_available) {
        const activeClass = worker.is_assigned ? ' active' : '';
        html += `
            <button class="day-popup-toggle${activeClass}"
                data-action="toggleWorkerAssignment" data-user-id="${worker.user_id}" data-date="${dateStr}">
                <span class="toggle-track"><span class="toggle-thumb"></span></span>
                <span class="toggle-label">${worker.is_assigned ? 'ON' : 'OFF'}</span>
            </button>
        `;
    } else {
        html += `<span style="color:#999;font-size:0.85em;">不可</span>`;
    }

    html += `</div>`;

    // Available time
    if (worker.is_available && worker.start_time) {
        html += `<div class="admin-worker-time-info">希望: ${worker.start_time} 〜 ${worker.end_time}</div>`;
    }

    // Assigned time editing
    if (worker.is_assigned) {
        const aStart = worker.assigned_start || worker.start_time || '09:00';
        const aEnd = worker.assigned_end || worker.end_time || '17:00';
        html += `
            <div class="admin-worker-assigned-time">
                <input type="time" class="form-control popup-time-input" value="${aStart}"
                    id="assigned-start-${worker.user_id}" data-action="applyWorkerTime" data-user-id="${worker.user_id}" data-date="${dateStr}">
                <span class="time-separator">〜</span>
                <input type="time" class="form-control popup-time-input" value="${aEnd}"
                    id="assigned-end-${worker.user_id}" data-action="applyWorkerTime" data-user-id="${worker.user_id}" data-date="${dateStr}">
                ${worker.entry_id ? `<button class="btn btn-outline btn-sm" data-action="openVacancyDialog" data-entry-id="${worker.entry_id}" title="欠員補充" style="margin-left:4px;padding:2px 6px;"><i data-lucide="user-minus" style="width:12px;height:12px;"></i></button>` : ''}
            </div>
        `;
    }

    card.innerHTML = html;
    return card;
}

function closeAdminDayPopup() {
    const overlay = document.getElementById('admin-day-popup-overlay');
    if (!overlay) return;
    overlay.classList.remove('visible');
    const popup = overlay.querySelector('.day-popup');
    if (popup) popup.classList.remove('visible');
    setTimeout(() => overlay.remove(), 200);
}

// --- Coverage Timeline ---

function renderAdminCoverageTimeline(dateStr, data, container) {
    const oh = data.openingHours;
    if (!oh) {
        container.innerHTML = '<span style="color:#999;font-size:0.85em;">開校時間未設定</span>';
        return;
    }

    const totalStart = timeToMinutes(oh.start_time);
    const totalEnd = timeToMinutes(oh.end_time);
    const totalRange = totalEnd - totalStart;
    if (totalRange <= 0) {
        container.innerHTML = '<span style="color:#999;font-size:0.85em;">-</span>';
        return;
    }

    const assignedWorkers = data.workers.filter(w => w.is_assigned);

    // Build timeline bar
    let html = '<div class="timeline-bar">';
    assignedWorkers.forEach((w, idx) => {
        const color = WORKER_COLORS[idx % WORKER_COLORS.length];
        const wStart = timeToMinutes(w.assigned_start || w.start_time || oh.start_time);
        const wEnd = timeToMinutes(w.assigned_end || w.end_time || oh.end_time);
        const left = Math.max(0, ((wStart - totalStart) / totalRange) * 100);
        const width = Math.min(100 - left, ((wEnd - wStart) / totalRange) * 100);
        html += `<div class="tl-block" style="left:${left}%;width:${width}%;background:${color};opacity:0.7;" title="${escapeHtml(w.user_name)}"></div>`;
    });
    html += '</div>';

    // Labels
    html += '<div class="timeline-labels">';
    const labels = [oh.start_time];
    const midTime = minutesToTime(Math.round((totalStart + totalEnd) / 2));
    labels.push(midTime);
    labels.push(oh.end_time);
    labels.forEach((lbl, i) => {
        const pos = i === 0 ? 0 : i === labels.length - 1 ? 100 : 50;
        html += `<span class="tl-label" style="left:${pos}%;">${lbl}</span>`;
    });
    html += '</div>';

    // Legend
    if (assignedWorkers.length > 0) {
        html += '<div class="timeline-legend">';
        assignedWorkers.forEach((w, idx) => {
            const color = WORKER_COLORS[idx % WORKER_COLORS.length];
            html += `<span class="tl-legend-item"><span class="tl-legend-dot" style="background:${color};"></span>${escapeHtml(w.user_name)}</span>`;
        });
        html += '</div>';
    }

    container.innerHTML = html;
}

// --- Worker Assignment Toggle ---

function toggleWorkerAssignment(userId, dateStr) {
    const idx = scheduleEntries.findIndex(e => e.user_id === userId && e.shift_date === dateStr);
    if (idx >= 0) {
        scheduleEntries.splice(idx, 1);
    } else {
        // Find worker's available time from submissions
        const dayData = dayAggregatedData[dateStr];
        const worker = dayData ? dayData.workers.find(w => w.user_id === userId) : null;
        scheduleEntries.push({
            user_id: userId,
            shift_date: dateStr,
            start_time: (worker && worker.start_time) || '09:00',
            end_time: (worker && worker.end_time) || '17:00',
        });
    }

    // Rebuild and re-render
    buildDayAggregatedData();
    renderBuilderCalendar();
    renderHoursSummary();

    // Re-open popup for this date
    const newData = dayAggregatedData[dateStr];
    if (newData) showAdminDayPopup(dateStr, newData);
}

// --- Apply Worker Time Change ---

function applyWorkerTime(userId, dateStr) {
    const startInput = document.getElementById(`assigned-start-${userId}`);
    const endInput = document.getElementById(`assigned-end-${userId}`);
    if (!startInput || !endInput) return;

    const entry = scheduleEntries.find(e => e.user_id === userId && e.shift_date === dateStr);
    if (entry) {
        entry.start_time = startInput.value;
        entry.end_time = endInput.value;
    }

    // Rebuild and refresh popup
    buildDayAggregatedData();
    renderBuilderCalendar();
    renderHoursSummary();

    // Refresh timeline in popup without full re-open
    const tlContainer = document.getElementById('admin-coverage-timeline');
    const newData = dayAggregatedData[dateStr];
    if (tlContainer && newData) {
        renderAdminCoverageTimeline(dateStr, newData, tlContainer);
    }
}

// --- Sidebar renderers ---

function renderSubmissionsSummary(submissions) {
    const container = document.getElementById('submissions-summary');
    if (!submissions || submissions.length === 0) {
        container.innerHTML = '<p style="color:#999;font-size:0.9em;">まだ希望提出がありません。アルバイトがシフト希望を提出すると、ここに表示されます。</p>';
        return;
    }
    container.innerHTML = submissions.map(s => {
        const timeLabel = s.submitted_at ? formatSubmittedAt(s.submitted_at) : '';
        return `
            <div class="mb-8" style="padding:6px 0;border-bottom:1px solid var(--color-neutral-100);">
                <div class="flex-between">
                    <span>${escapeHtml(s.user_name || s.user_email)}</span>
                    <span class="badge badge-${s.status}">${s.status === 'submitted' ? '提出済' : s.status}</span>
                </div>
                ${timeLabel ? `<div style="color:#999;font-size:0.78em;margin-top:2px;">提出: ${timeLabel}</div>` : ''}
            </div>
        `;
    }).join('');
}

function renderHoursSummary() {
    const container = document.getElementById('hours-summary');
    const summary = {};
    scheduleEntries.forEach(e => {
        const uid = e.user_id;
        if (!summary[uid]) {
            const sub = (submissionsData || []).find(s => s.user_id === uid);
            summary[uid] = {
                name: sub ? (sub.user_name || sub.user_email) : `User ${uid}`,
                hours: 0,
                shifts: 0,
            };
        }
        const startMins = timeToMinutes(e.start_time);
        const endMins = timeToMinutes(e.end_time);
        summary[uid].hours += (endMins - startMins) / 60;
        summary[uid].shifts++;
    });

    if (Object.keys(summary).length === 0) {
        container.innerHTML = '<p style="color:#999;font-size:0.9em;">カレンダーの日付をクリックして、スタッフを割り当ててください。</p>';
        return;
    }

    container.innerHTML = Object.values(summary).map(s => `
        <div class="flex-between mb-8">
            <span>${escapeHtml(s.name)}</span>
            <span style="font-weight:600;">${s.hours.toFixed(1)}h (${s.shifts}日)</span>
        </div>
    `).join('');
}

async function saveSchedule() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;
    try {
        await api.post(`/api/admin/periods/${periodId}/schedule`, { entries: scheduleEntries });
        showToast('スケジュールを保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

async function submitForApproval() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;

    if (scheduleEntries.length === 0) {
        showToast('スタッフが割り当てられていません。カレンダーから割当を行ってください。', 'warning');
        return;
    }

    showConfirmDialog(
        '承認申請を送信しますか？',
        `現在のスケジュール（${scheduleEntries.length}件のシフト）を事業主に承認申請します。申請後も事業主が差戻した場合は再編集できます。`,
        'btn-warning',
        '承認申請を送信',
        async () => {
            try {
                await api.post(`/api/admin/periods/${periodId}/schedule`, { entries: scheduleEntries });
                await api.post(`/api/admin/periods/${periodId}/schedule/submit`);
                showToast('承認申請を送信しました', 'success');
            } catch (e) {
                showToast(`承認申請に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

async function confirmSchedule() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;

    showConfirmDialog(
        'シフトを確定してGoogleカレンダーに同期しますか？',
        '確定すると各スタッフのGoogleカレンダーにシフトが登録されます。この操作は取り消せません。',
        'btn-success',
        '確定・同期する',
        async () => {
            try {
                const result = await api.post(`/api/admin/periods/${periodId}/schedule/confirm`);
                const syncResults = result.sync_results || [];
                const success = syncResults.filter(r => r.success).length;
                const failed = syncResults.filter(r => r.error).length;
                showToast(`確定完了: ${success}件同期成功, ${failed}件失敗`, success > 0 ? 'success' : 'warning');
            } catch (e) {
                showToast(`確定に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

// --- Reminder Settings ---

async function loadReminderSettings() {
    try {
        const data = await api.get('/api/admin/reminder-settings');
        const daysDeadline = document.getElementById('reminder-days-deadline');
        const timeDeadline = document.getElementById('reminder-time-deadline');
        const daysShift = document.getElementById('reminder-days-shift');
        const timeShift = document.getElementById('reminder-time-shift');
        if (daysDeadline) daysDeadline.value = data.reminder_days_before_deadline ?? 1;
        if (timeDeadline) timeDeadline.value = data.reminder_time_deadline || '09:00';
        if (daysShift) daysShift.value = data.reminder_days_before_shift ?? 1;
        if (timeShift) timeShift.value = data.reminder_time_shift || '21:00';
    } catch (e) {
        console.warn('Failed to load reminder settings:', e);
    }
}

async function saveReminderSettings() {
    try {
        await api.put('/api/admin/reminder-settings', {
            reminder_days_before_deadline: Number(document.getElementById('reminder-days-deadline').value),
            reminder_time_deadline: document.getElementById('reminder-time-deadline').value,
            reminder_days_before_shift: Number(document.getElementById('reminder-days-shift').value),
            reminder_time_shift: document.getElementById('reminder-time-shift').value,
        });
        showToast('リマインド設定を保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

async function sendPeriodReminder(periodId) {
    showConfirmDialog(
        '未提出者にリマインドを送信しますか？',
        'まだシフト希望を提出していないアルバイトにメールで通知します。',
        'btn-primary',
        '送信する',
        async () => {
            try {
                const result = await api.post(`/api/admin/reminders/send/${periodId}`);
                showToast(`リマインド送信: ${result.sent}件送信, ${result.skipped}件スキップ`, 'success');
            } catch (e) {
                showToast(`送信に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

// --- Vacancy Management ---

async function loadVacancies() {
    const container = document.getElementById('vacancy-list');
    if (!container) return;
    try {
        const vacancies = await api.get('/api/admin/vacancy');
        if (!vacancies || vacancies.length === 0) {
            container.innerHTML = '<p class="help-text">欠員補充リクエストはありません</p>';
            return;
        }
        const statusLabel = { open: '募集中', notified: '通知済', accepted: '補充完了', expired: '期限切れ', cancelled: '取消' };
        const statusColor = { open: '#3b82f6', notified: '#f59e0b', accepted: '#22c55e', expired: '#6b7280', cancelled: '#ef4444' };
        container.innerHTML = vacancies.map(v => `
            <div class="flex-between mb-8" style="padding:8px 0;border-bottom:1px solid var(--color-neutral-100);">
                <div>
                    <span style="font-weight:600;">${escapeHtml(v.original_user_name || '不明')}</span>
                    <span style="color:var(--color-neutral-400);font-size:0.85em;margin-left:8px;">${v.shift_date || ''} ${v.start_time || ''}-${v.end_time || ''}</span>
                    <span style="color:${statusColor[v.status] || '#666'};font-size:0.82em;margin-left:8px;font-weight:600;">${statusLabel[v.status] || v.status}</span>
                    ${v.accepted_by_name ? `<span style="color:#22c55e;font-size:0.82em;margin-left:4px;">→ ${escapeHtml(v.accepted_by_name)}</span>` : ''}
                </div>
                ${v.status === 'open' || v.status === 'notified' ? `<button class="btn btn-outline btn-sm" data-action="cancelVacancy" data-id="${v.id}" title="キャンセル"><i data-lucide="x" style="width:13px;height:13px;"></i></button>` : ''}
            </div>
        `).join('');
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        container.innerHTML = '<p class="help-text">読み込みに失敗しました</p>';
    }
}

async function openVacancyDialog(entryId) {
    try {
        const candidates = await api.get(`/api/admin/vacancy/candidates/${entryId}`);
        if (!candidates || candidates.length === 0) {
            showToast('候補者が見つかりません（この日に勤務可能な未割当スタッフがいません）', 'warning');
            return;
        }

        const overlay = document.createElement('div');
        overlay.className = 'confirm-dialog-overlay';
        overlay.innerHTML = `
            <div class="confirm-dialog" style="max-width:500px;">
                <h3>欠員補充 — 候補者選択</h3>
                <p style="color:var(--color-neutral-400);font-size:0.9em;margin-bottom:16px;">候補者を選択して通知を送信します。労働時間が少ない順に並んでいます。</p>
                <div class="form-group">
                    <label>理由（任意）</label>
                    <input type="text" id="vacancy-reason" class="form-control" placeholder="例: 体調不良による欠勤">
                </div>
                <div style="max-height:300px;overflow-y:auto;margin-bottom:16px;">
                    ${candidates.map(c => `
                        <label style="display:flex;align-items:center;gap:8px;padding:8px;border-bottom:1px solid var(--color-neutral-100);cursor:pointer;">
                            <input type="checkbox" class="vacancy-candidate-cb" value="${c.user_id}" checked>
                            <span style="flex:1;">
                                <strong>${escapeHtml(c.user_name)}</strong>
                                <span style="color:var(--color-neutral-400);font-size:0.85em;margin-left:8px;">週${c.weekly_hours}h</span>
                            </span>
                        </label>
                    `).join('')}
                </div>
                <div class="confirm-dialog-actions">
                    <button class="btn btn-outline" id="vacancy-dialog-cancel">キャンセル</button>
                    <button class="btn btn-primary" id="vacancy-dialog-send">通知を送信</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        overlay.querySelector('#vacancy-dialog-cancel').onclick = () => overlay.remove();
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
        overlay.querySelector('#vacancy-dialog-send').onclick = async () => {
            const selectedIds = [...overlay.querySelectorAll('.vacancy-candidate-cb:checked')].map(cb => Number(cb.value));
            if (selectedIds.length === 0) {
                showToast('候補者を選択してください', 'warning');
                return;
            }
            const reason = overlay.querySelector('#vacancy-reason').value;
            try {
                const vacancy = await api.post('/api/admin/vacancy', {
                    schedule_entry_id: entryId,
                    reason: reason,
                });
                await api.post(`/api/admin/vacancy/${vacancy.id}/notify`, {
                    candidate_user_ids: selectedIds,
                });
                showToast('欠員補充通知を送信しました', 'success');
                overlay.remove();
                loadVacancies();
            } catch (e) {
                showToast(`送信に失敗しました: ${e.message}`, 'error');
            }
        };
    } catch (e) {
        showToast(`候補者の取得に失敗しました: ${e.message}`, 'error');
    }
}

async function cancelVacancy(id) {
    showConfirmDialog(
        '欠員補充リクエストをキャンセルしますか？',
        'キャンセルすると、候補者への通知は無効になります。',
        'btn-danger',
        'キャンセルする',
        async () => {
            try {
                await api.delete(`/api/admin/vacancy/${id}`);
                showToast('リクエストをキャンセルしました', 'success');
                loadVacancies();
            } catch (e) {
                showToast(`キャンセルに失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

// --- Change Log ---

async function loadChangeLog() {
    const container = document.getElementById('change-log-list');
    if (!container) return;
    try {
        const logs = await api.get('/api/admin/change-log');
        if (!logs || logs.length === 0) {
            container.innerHTML = '<p class="help-text">変更履歴はありません</p>';
            return;
        }
        container.innerHTML = logs.map(l => `
            <div style="padding:6px 0;border-bottom:1px solid var(--color-neutral-100);font-size:0.85em;">
                <div><strong>${l.shift_date || ''}</strong> ${escapeHtml(l.original_user_name || '?')} → ${escapeHtml(l.new_user_name || '?')}</div>
                <div style="color:var(--color-neutral-400);">${l.reason ? escapeHtml(l.reason) : ''} ${l.performed_at ? `(${new Date(l.performed_at).toLocaleDateString('ja-JP')})` : ''}</div>
            </div>
        `).join('');
    } catch (e) {
        container.innerHTML = '<p class="help-text">読み込みに失敗しました</p>';
    }
}

init().finally(() => { if (window.lucide) lucide.createIcons(); });
