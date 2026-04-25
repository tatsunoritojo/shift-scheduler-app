import { api, getCurrentUser } from './modules/api-client.js';
import { showToast } from './modules/notification.js';
import { renderCalendar } from './modules/calendar-grid.js';
import { timeToMinutes, minutesToTime } from './modules/time-utils.js';
import { escapeHtml } from './modules/escape-html.js';
import { showConfirmDialog } from './modules/ui-dialogs.js';
import { setLoading, withLoading } from './modules/btn-loading.js';
import { isAllDayEvent, getEventsForDate as _getEventsForDate, formatSubmittedAt } from './modules/event-utils.js';
import { WEEKDAY_NAMES } from './modules/date-constants.js';

/** Format a local Date to YYYY-MM-DD without UTC conversion. */
const toLocalDateStr = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

let currentUser = null;
let scheduleEntries = [];  // Current schedule being built
let scheduleVersion = null; // Optimistic locking: updated_at of last fetched schedule

// --- Dirty tracking for save buttons ---
// A save button starts as btn-outline (white with blue border). When the user
// edits any tracked form, the button switches to btn-primary (solid blue) to
// signal "click to persist changes". After a successful save or fresh load,
// it returns to btn-outline.
const dirtyTrackers = {};

function registerDirtyTracker(name, scope, saveBtn) {
    if (!scope || !saveBtn) return;
    dirtyTrackers[name] = { scope, saveBtn };
    setClean(name);
    // Listen for form interactions within the scope.
    scope.addEventListener('input', () => setDirty(name));
    scope.addEventListener('change', () => setDirty(name));
}

function setDirty(name) {
    const t = dirtyTrackers[name];
    if (!t) return;
    t.saveBtn.classList.remove('btn-outline');
    t.saveBtn.classList.add('btn-primary');
    t.saveBtn.dataset.dirty = 'true';
}

function setClean(name) {
    const t = dirtyTrackers[name];
    if (!t) return;
    t.saveBtn.classList.remove('btn-primary');
    t.saveBtn.classList.add('btn-outline');
    t.saveBtn.dataset.dirty = 'false';
}

function initDirtyTrackers() {
    // Each tracker pairs a scope element (usually a .card) with a save button.
    const map = [
        ['sync-keyword',      'sync-keyword-card',       'btn-save-sync-keyword'],
        ['reminder',          null,                      'btn-save-reminder-settings'],
        ['levels',            null,                      'btn-save-level-settings'],
        ['overlap-check',     null,                      'btn-save-overlap-check'],
        ['min-attendance',    null,                      'btn-save-min-attendance'],
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
let submissionsData = [];  // period submissions
let openingHoursData = {}; // dateStr -> { start_time, end_time } | null
let currentPeriod = null;  // Selected period object
let dayAggregatedData = {}; // dateStr -> aggregated day info
let workersData = []; // workers list
let builderLoadGeneration = 0; // Guard against stale async responses
let adminCalendarEvents = []; // Google Calendar events for the admin
let syncKeyword = '営業時間'; // Calendar sync keyword (loaded from settings)

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
            const dateStr = toLocalDateStr(d);
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
    const fmt = toLocalDateStr;
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

    // Level settings
    const levelEnabled = document.getElementById('level-system-enabled');
    if (levelEnabled) levelEnabled.addEventListener('change', (e) => {
        levelSystemState.enabled = e.target.checked;
        renderLevelSettings();
    });
    const btnAddLevelTier = document.getElementById('btn-add-level-tier');
    if (btnAddLevelTier) btnAddLevelTier.addEventListener('click', () => addLevelTier());
    const btnSaveLevel = document.getElementById('btn-save-level-settings');
    if (btnSaveLevel) btnSaveLevel.addEventListener('click', () => saveLevelSettings());

    // Overlap check settings
    const btnSaveOverlap = document.getElementById('btn-save-overlap-check');
    if (btnSaveOverlap) btnSaveOverlap.addEventListener('click', () => saveOverlapCheckSettings());

    // Min attendance settings
    const minMode = document.getElementById('min-attendance-mode');
    if (minMode) minMode.addEventListener('change', (e) => {
        minAttendanceState.mode = e.target.value;
        renderMinAttendanceSettings();
    });
    const minUnit = document.getElementById('min-attendance-unit');
    if (minUnit) minUnit.addEventListener('change', (e) => {
        minAttendanceState.unit = e.target.value;
        renderMinAttendanceSettings();
    });
    const btnSaveMinAtt = document.getElementById('btn-save-min-attendance');
    if (btnSaveMinAtt) btnSaveMinAtt.addEventListener('click', () => saveMinAttendanceSettings());

    // Workflow (approval process) settings
    const workflowToggle = document.getElementById('workflow-approval-required');
    if (workflowToggle) workflowToggle.addEventListener('change', () => updateWorkflowWarning());
    const btnSaveWorkflow = document.getElementById('btn-save-workflow');
    if (btnSaveWorkflow) btnSaveWorkflow.addEventListener('click', () => saveWorkflowSettings());
    const btnGotoOwnerInvite = document.getElementById('btn-goto-owner-invite');
    if (btnGotoOwnerInvite) btnGotoOwnerInvite.addEventListener('click', () => gotoOwnerInvite());
    const btnInviteOwner = document.getElementById('btn-invite-owner');
    if (btnInviteOwner) btnInviteOwner.addEventListener('click', () => inviteOwner());

    // Sync keyword settings
    const btnSaveSyncKeyword = document.getElementById('btn-save-sync-keyword');
    if (btnSaveSyncKeyword) btnSaveSyncKeyword.addEventListener('click', () => saveSyncKeyword());

    // Setup wizard
    const btnWizardConnect = document.getElementById('btn-wizard-connect');
    if (btnWizardConnect) btnWizardConnect.addEventListener('click', () => wizardConnect());
    const btnWizardSkip = document.getElementById('btn-wizard-skip');
    if (btnWizardSkip) btnWizardSkip.addEventListener('click', () => wizardSkip());
    const btnWizardSave = document.getElementById('btn-wizard-save');
    if (btnWizardSave) btnWizardSave.addEventListener('click', () => wizardSave());
    const btnWizardBack = document.getElementById('btn-wizard-back');
    if (btnWizardBack) btnWizardBack.addEventListener('click', () => wizardBack());
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
            case 'removeLevelTier': removeLevelTier(target.dataset.key, target.dataset.label, Number(target.dataset.count)); break;
            case 'moveLevelTierUp': moveLevelTier(target.dataset.key, -1); break;
            case 'moveLevelTierDown': moveLevelTier(target.dataset.key, 1); break;
            case 'openVacancyDialog': openVacancyDialog(Number(target.dataset.entryId)); break;
            case 'cancelVacancy': cancelVacancy(Number(target.dataset.id)); break;
            case 'sendPeriodReminder': sendPeriodReminder(Number(target.dataset.periodId)); break;
            case 'openShareModal': openShareModal(Number(target.dataset.periodId)); break;
            case 'closeShareModal': closeShareModal(); break;
            case 'shareDownloadPng': shareDownloadPng(); break;
            case 'shareDownloadPdf': shareDownloadPdf(); break;
            case 'shareCopyMessage': shareCopyMessage(); break;
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
        if (target.dataset.action === 'changeMemberLevel') {
            const memberId = Number(target.dataset.memberId);
            const value = target.value || null;
            updateMemberAttributes(memberId, { level_key: value })
                .then(() => {
                    showToast('レベルを更新しました', 'success');
                    // Refresh tier member counts on settings tab
                    loadLevelSettings();
                })
                .catch(() => loadMembers());
        }
        if (target.dataset.action === 'changeMemberMinCount' || target.dataset.action === 'changeMemberMinHours') {
            const memberId = Number(target.dataset.memberId);
            const raw = target.value;
            const parsed = raw === '' ? null : Number(raw);
            const key = target.dataset.action === 'changeMemberMinCount'
                ? 'min_attendance_count_per_week' : 'min_attendance_hours_per_week';
            updateMemberAttributes(memberId, { [key]: parsed })
                .then(() => showToast('最低出勤設定を更新しました', 'success'))
                .catch(() => loadMembers());
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

let currentOrgName = '';

async function loadInviteCode() {
    try {
        const data = await api.get('/api/admin/invite-code');
        if (data.organization_name) currentOrgName = data.organization_name;
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
        container.onclick = () => showQRCodeFullscreen(url);
    } catch (e) {
        container.innerHTML = '<span style="color:var(--color-neutral-400);font-size:0.85em;">QRコード生成エラー</span>';
    }
}

function showQRCodeFullscreen(url) {
    if (typeof qrcode === 'undefined') return;
    const orgName = currentOrgName || 'シフリー';
    const overlay = document.createElement('div');
    Object.assign(overlay.style, {
        position: 'fixed', inset: '0', zIndex: '9999',
        background: '#fff', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
    });
    const qr = qrcode(0, 'M');
    qr.addData(url);
    qr.make();
    const svgHtml = qr.createSvgTag(10, 0);
    overlay.innerHTML = `
        <div style="text-align:center;padding:24px;">
            <p style="font-size:1.1em;color:#3b82f6;font-weight:700;letter-spacing:0.05em;margin-bottom:8px;">シフリー</p>
            <p style="font-size:1.6em;font-weight:700;color:#1e293b;margin-bottom:32px;">${orgName}</p>
            <div style="display:inline-block;padding:16px;border-radius:16px;border:2px solid #e2e8f0;">${svgHtml}</div>
            <p style="color:#94a3b8;font-size:0.85em;margin-top:32px;">スキャンして組織に参加</p>
            <p style="color:#cbd5e1;font-size:0.75em;margin-top:12px;">タップして閉じる</p>
        </div>`;
    overlay.onclick = () => overlay.remove();
    document.addEventListener('keydown', function handler(e) {
        if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', handler); }
    });
    document.body.appendChild(overlay);
}

async function generateInviteCode() {
    const hasExisting = document.getElementById('invite-code-content')?.style.display !== 'none';
    const doGenerate = async () => {
        const btn = document.getElementById('btn-regenerate-invite-code') || document.getElementById('btn-generate-invite-code');
        await withLoading(btn, async () => {
            await api.post('/api/admin/invite-code');
            showToast('招待コードを生成しました', 'success');
            membersTabLoaded = false;
            await loadMembersTab();
        });
    };
    if (hasExisting) {
        showConfirmDialog(
            '招待コードを再生成しますか？',
            '現在のコードは無効になり、既存の招待リンクやQRコードが使えなくなります。',
            'btn-warning',
            '再生成する',
            async () => {
                try { await doGenerate(); }
                catch (e) { showToast(`生成に失敗しました: ${e.message}`, 'error'); }
            }
        );
    } else {
        try { await doGenerate(); }
        catch (e) { showToast(`生成に失敗しました: ${e.message}`, 'error'); }
    }
}

function copyInviteUrl() {
    const input = document.getElementById('invite-url-display');
    const btn = document.getElementById('btn-copy-invite-url');
    if (!input || !input.value) return;
    navigator.clipboard.writeText(input.value).then(
        () => {
            if (btn) {
                const original = btn.innerHTML;
                btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg> コピーしました';
                btn.classList.add('btn-copied');
                setTimeout(() => {
                    btn.innerHTML = original;
                    btn.classList.remove('btn-copied');
                    if (window.lucide) lucide.createIcons();
                }, 2000);
            }
        },
        () => showToast('コピーに失敗しました', 'error')
    );
}

async function toggleInviteCode(enabled) {
    const toggle = document.getElementById('invite-code-enabled-toggle');
    toggle.disabled = true;
    try {
        await api.put('/api/admin/invite-code', { enabled });
        showToast(enabled ? '招待リンクを有効にしました' : '招待リンクを無効にしました', 'success');
    } catch (e) {
        showToast(`更新に失敗しました: ${e.message}`, 'error');
        toggle.checked = !enabled;
    } finally {
        toggle.disabled = false;
    }
}

async function loadInvitations() {
    try {
        const data = await api.get('/api/admin/invitations');
        const container = document.getElementById('invitations-table');
        const pendingCount = (data || []).filter(t => t.is_valid && !t.used_at).length;
        setTabBadge('members', pendingCount);
        if (!data || data.length === 0) {
            container.innerHTML = '<p style="color:var(--color-neutral-400);font-size:0.9em;">招待はありません</p>';
            return;
        }
        const ROLE_LABELS = { admin: '管理者', owner: '事業主', worker: 'アルバイト' };
        const rows = data.map(t => {
            const valid = t.is_valid;
            let badgeClass, badgeLabel;
            if (t.used_at) {
                badgeClass = 'badge-invite-accepted';
                badgeLabel = '使用済み';
            } else if (valid) {
                badgeClass = 'badge-invite-pending';
                badgeLabel = '有効';
            } else {
                badgeClass = 'badge-invite-expired';
                badgeLabel = '期限切れ';
            }
            const expires = t.expires_at ? new Date(t.expires_at).toLocaleString('ja-JP') : '-';
            return `<tr>
                <td>${escapeHtml(t.email || '(制限なし)')}</td>
                <td>${ROLE_LABELS[t.role] || t.role}</td>
                <td><span class="badge ${badgeClass}">${badgeLabel}</span></td>
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
        setTabBadge('members', 0);
    }
}

async function createInvitation() {
    const btn = document.getElementById('btn-create-invitation');
    const email = document.getElementById('invitation-email').value.trim();
    const role = document.getElementById('invitation-role').value;
    const expiresHours = parseInt(document.getElementById('invitation-expires').value, 10) || 72;
    const body = { role, expires_hours: expiresHours };
    if (email) body.email = email;
    try {
        await withLoading(btn, async () => {
            await api.post('/api/admin/invitations', body);
            showToast('招待を作成しました', 'success');
            document.getElementById('invitation-email').value = '';
            await loadInvitations();
            if (window.lucide) lucide.createIcons();
        });
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
        const showLevel = levelSystemState.enabled && levelSystemState.tiers.length > 0;
        const showPerMemberAttendance = minAttendanceState.mode === 'per_member';
        const showCount = showPerMemberAttendance && (minAttendanceState.unit === 'count' || minAttendanceState.unit === 'both');
        const showHours = showPerMemberAttendance && (minAttendanceState.unit === 'hours' || minAttendanceState.unit === 'both');
        const rows = data.map(m => {
            const isSelf = currentUser && m.user_id === currentUser.id;
            const joined = m.joined_at ? new Date(m.joined_at).toLocaleDateString('ja-JP') : '-';
            const levelCell = showLevel ? `<td>
                <select class="form-control form-control-sm" data-action="changeMemberLevel" data-member-id="${m.id}">
                    <option value="">—</option>
                    ${levelSystemState.tiers.map(t => `<option value="${escapeHtml(t.key)}" ${m.level_key === t.key ? 'selected' : ''}>${escapeHtml(t.label)}</option>`).join('')}
                </select>
            </td>` : '';
            const countCell = showCount ? `<td>
                <input type="number" min="0" class="form-control form-control-sm" style="width:72px;" data-action="changeMemberMinCount" data-member-id="${m.id}" value="${m.min_attendance_count_per_week ?? ''}" placeholder="—">
            </td>` : '';
            const hoursCell = showHours ? `<td>
                <input type="number" min="0" step="0.5" class="form-control form-control-sm" style="width:80px;" data-action="changeMemberMinHours" data-member-id="${m.id}" value="${m.min_attendance_hours_per_week ?? ''}" placeholder="—">
            </td>` : '';
            return `<tr>
                <td>${escapeHtml(m.user_name || '-')}</td>
                <td style="font-size:0.85em;">${escapeHtml(m.user_email || '-')}</td>
                <td>
                    <select class="form-control form-control-sm" data-action="changeMemberRole" data-member-id="${m.id}" data-previous-role="${m.role}" ${isSelf ? 'disabled' : ''}>
                        ${['admin', 'owner', 'worker'].map(r => `<option value="${r}" ${m.role === r ? 'selected' : ''}>${ROLE_LABELS[r]}</option>`).join('')}
                    </select>
                </td>
                ${levelCell}
                ${countCell}
                ${hoursCell}
                <td style="font-size:0.85em;">${joined}</td>
                <td>${!isSelf ? `<button class="btn btn-outline btn-sm" data-action="removeMember" data-id="${m.id}" data-name="${escapeHtml(m.user_name || m.user_email || '')}" title="除外"><i data-lucide="user-x" style="width:13px;height:13px;"></i></button>` : ''}</td>
            </tr>`;
        }).join('');
        const headerCells = ['<th>名前</th>', '<th>メール</th>', '<th>ロール</th>'];
        if (showLevel) headerCells.push('<th>レベル</th>');
        if (showCount) headerCells.push('<th>週最低回</th>');
        if (showHours) headerCells.push('<th>週最低h</th>');
        headerCells.push('<th>参加日</th>', '<th></th>');
        container.innerHTML = `<table class="data-table" style="width:100%;font-size:0.9em;">
            <thead><tr>${headerCells.join('')}</tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
    } catch (e) {
        console.error('Failed to load members:', e);
    }
}

async function changeMemberRole(memberId, newRole) {
    const ROLE_LABELS = { admin: '管理者', owner: '事業主', worker: 'アルバイト' };
    const select = document.querySelector(`[data-action="changeMemberRole"][data-member-id="${memberId}"]`);
    const previousValue = select ? select.dataset.previousRole : null;

    // Pre-flight: check impact (last owner, pending approvals, etc.)
    let impactNote = '';
    try {
        const impact = await api.get(`/api/admin/members/${memberId}/role-change-impact?new_role=${encodeURIComponent(newRole)}`);
        if (impact.is_last_owner_while_approval_required) {
            impactNote += '\n⚠️ この事業主を降格すると、承認プロセスが停止します。';
        }
        if (impact.pending_schedules_count > 0) {
            impactNote += `\n⚠️ 進行中の承認申請が ${impact.pending_schedules_count} 件あります。`;
        }
    } catch (_) {
        // If preflight fails, fall through to normal confirmation
    }

    showConfirmDialog(
        'ロールを変更しますか？',
        `このメンバーのロールを「${ROLE_LABELS[newRole] || newRole}」に変更します。${impactNote}`,
        'btn-primary',
        '変更する',
        async () => {
            try {
                await api.put(`/api/admin/members/${memberId}/role`, { role: newRole });
                showToast('ロールを変更しました', 'success');
                // Refresh workflow state (owner count may have changed)
                await loadWorkflowSettings();
            } catch (e) {
                showToast(`ロール変更に失敗しました: ${e.message}`, 'error');
                await loadMembers();
                if (window.lucide) lucide.createIcons();
            }
        },
        () => {
            // Revert select to previous value on cancel
            if (select && previousValue) select.value = previousValue;
        }
    );
}

async function removeMember(id, name) {
    // Pre-flight: check impact
    let impactNote = '';
    try {
        const impact = await api.get(`/api/admin/members/${id}/role-change-impact`);
        if (impact.is_last_admin) {
            impactNote += '\n⚠️ 最後の管理者は除外できません。';
        }
        if (impact.is_last_owner_while_approval_required) {
            impactNote += '\n⚠️ この事業主を除外すると、承認プロセスが停止します。';
        }
        if (impact.pending_schedules_count > 0) {
            impactNote += `\n⚠️ 進行中の承認申請が ${impact.pending_schedules_count} 件あります。`;
        }
    } catch (_) {}

    showConfirmDialog(
        `${name || 'このメンバー'} を除外しますか？`,
        `除外すると、このユーザーは組織にアクセスできなくなります。${impactNote}`,
        'btn-danger',
        '除外する',
        async () => {
            try {
                await api.delete(`/api/admin/members/${id}`);
                showToast('メンバーを除外しました', 'success');
                await loadMembers();
                await loadWorkflowSettings();
                if (window.lucide) lucide.createIcons();
            } catch (e) {
                showToast(`除外に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

// --- Sync Settings & Setup Wizard ---

async function loadSyncSettings() {
    try {
        const data = await api.get('/api/admin/sync-settings');
        syncKeyword = data.calendar_sync_keyword || '営業時間';
        // Update keyword display in UI
        const keywordLabel = document.getElementById('sync-keyword-label');
        if (keywordLabel) keywordLabel.textContent = syncKeyword;
        const keywordInput = document.getElementById('sync-keyword-input');
        if (keywordInput) keywordInput.value = syncKeyword;
        setClean('sync-keyword');
        return data;
    } catch (e) {
        console.warn('Failed to load sync settings:', e);
        return null;
    }
}

async function saveSyncKeyword() {
    const input = document.getElementById('sync-keyword-input');
    if (!input) return;
    const keyword = input.value.trim();
    if (!keyword) {
        showToast('キーワードを入力してください', 'warning');
        return;
    }
    try {
        await api.put('/api/admin/sync-settings', { calendar_sync_keyword: keyword });
        syncKeyword = keyword;
        const keywordLabel = document.getElementById('sync-keyword-label');
        if (keywordLabel) keywordLabel.textContent = syncKeyword;
        setClean('sync-keyword');
        showToast('同期キーワードを保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

function showSetupWizard() {
    const wizard = document.getElementById('setup-wizard');
    if (wizard) wizard.style.display = '';
}

function hideSetupWizard() {
    const wizard = document.getElementById('setup-wizard');
    if (wizard) wizard.style.display = 'none';
}

async function wizardConnect() {
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

function wizardBack() {
    document.getElementById('wizard-step-1').style.display = '';
    document.getElementById('wizard-step-2').style.display = 'none';
}

async function wizardSave() {
    const keyword = document.getElementById('wizard-keyword').value.trim();
    if (!keyword) return;

    try {
        await api.put('/api/admin/sync-settings', {
            calendar_sync_keyword: keyword,
            calendar_setup_dismissed: true,
        });
        syncKeyword = keyword;
        const keywordLabel = document.getElementById('sync-keyword-label');
        if (keywordLabel) keywordLabel.textContent = syncKeyword;
        const keywordInput = document.getElementById('sync-keyword-input');
        if (keywordInput) keywordInput.value = syncKeyword;
        hideSetupWizard();
        showSyncKeywordCard();
        showToast('カレンダー連携を設定しました。インポートを開始します。', 'success');
        // Auto-trigger import
        document.getElementById('btn-import-hours').click();
    } catch (e) {
        showToast(`設定の保存に失敗しました: ${e.message}`, 'error');
    }
}

async function wizardSkip() {
    try {
        await api.put('/api/admin/sync-settings', { calendar_setup_dismissed: true });
    } catch (e) { /* ignore */ }
    hideSetupWizard();
    showSyncKeywordCard();
    showToast('カレンダー連携設定をスキップしました。後から設定できます。', 'info');
}

function showSyncKeywordCard() {
    const card = document.getElementById('sync-keyword-card');
    if (card) card.style.display = '';
}

async function init() {
    setupStaticHandlers();
    setupDelegatedHandlers();
    initDirtyTrackers();
    try {
        currentUser = await getCurrentUser();
        document.getElementById('user-name').textContent = currentUser.display_name || currentUser.email;
        initSyncDateRange();
        const results = await Promise.allSettled([
            loadSyncStatus(),
            loadOpeningHours(),
            loadExceptions(),
            loadPeriods(),
            loadReminderSettings(),
            loadSyncSettings(),
            loadLevelSettings(),
            loadOverlapCheckSettings(),
            loadMinAttendanceSettings(),
            loadWorkflowSettings(),
            loadInvitations(),
        ]);
        const statusData = results[0].status === 'fulfilled' ? results[0].value : null;
        const syncSettings = results[5].status === 'fulfilled' ? results[5].value : null;

        // Show setup wizard or keyword card
        const isConfigured = syncSettings && syncSettings.calendar_setup_dismissed;
        const hasCalExceptions = statusData && statusData.calendar_exceptions && statusData.calendar_exceptions.count > 0;
        const needsSetup = !isConfigured && !hasCalExceptions;
        if (needsSetup) {
            showSetupWizard();
        } else {
            showSyncKeywordCard();
        }
        setTabBadgeDot('settings', needsSetup);

        // Show preview calendar based on calendar exceptions range
        if (statusData && statusData.calendar_exceptions && statusData.calendar_exceptions.count > 0) {
            renderImportPreview(
                statusData.calendar_exceptions.min_date,
                statusData.calendar_exceptions.max_date
            );
        }

        // 初期表示タブの決定: セットアップ未完了なら設定タブ、通常運用ならシフト構築タブ
        switchTab(needsSetup ? 'settings' : 'builder');
    } catch (e) {
        console.error('Init error:', e);
    }
}

// --- Tab badges ---
function setTabBadge(tabName, count) {
    const el = document.getElementById(`badge-${tabName}`);
    if (!el) return;
    if (count > 0) {
        el.textContent = String(count);
        el.hidden = false;
    } else {
        el.textContent = '';
        el.hidden = true;
    }
}

function setTabBadgeDot(tabName, show) {
    const el = document.getElementById(`badge-${tabName}`);
    if (!el) return;
    el.textContent = '';
    el.hidden = !show;
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
                        ${existing && existing.is_closed ? 'checked' : ''}> 休業
                </label>
            </div>
        `);
    }
    grid.innerHTML = rows.join('');
    setClean('opening-hours');
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
        setClean('opening-hours');
        showToast('営業時間を保存しました', 'success');
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
                        <td>${e.is_closed ? '休業' : `${e.start_time}-${e.end_time}`}</td>
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
        `${startDate} 〜 ${endDate} の営業時間をGoogleカレンダーに書き出します。カレンダー上の既存「${syncKeyword}」イベントは更新されます。`,
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
        `${startDate} 〜 ${endDate} の「${syncKeyword}」イベントをGoogleカレンダーから取込み、例外リストに<strong>保存</strong>します。手動設定済みの日は上書きされません。`,
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

    const buildPending = (data || []).filter(p => p.status === 'closed').length;
    setTabBadge('builder', buildPending);

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
                            <button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;" data-action="openShareModal" data-period-id="${p.id}" title="募集案内をPNG/PDFで保存"><i data-lucide="download" style="width:13px;height:13px;"></i> 案内DL</button>
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
        const created = await api.post('/api/admin/periods', data);
        showToast('シフト期間を作成しました', 'success');
        await loadPeriods();
        // Auto-open share modal so the admin can download the recruitment
        // calendar immediately after creation.
        if (created && created.id) {
            openShareModal(created.id);
        }
    } catch (e) {
        showToast(`作成に失敗しました: ${e.message}`, 'error');
    }
}

// ======================================================================
// Period share modal: download recruitment calendar as PNG / PDF
// ======================================================================

const SHARE_WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'];
let shareModalData = null; // { period, openingHours, exceptions }

async function openShareModal(periodId) {
    try {
        // Ensure org name is available for the card header
        const orgPromise = currentOrgName
            ? Promise.resolve({ organization_name: currentOrgName })
            : api.get('/api/admin/invite-code').catch(() => ({}));
        const [periods, openingHours, exceptions, orgData] = await Promise.all([
            api.get('/api/admin/periods'),
            api.get('/api/admin/opening-hours'),
            api.get('/api/admin/opening-hours/exceptions'),
            orgPromise,
        ]);
        if (orgData && orgData.organization_name) {
            currentOrgName = orgData.organization_name;
        }
        const period = periods.find(p => p.id === periodId);
        if (!period) {
            showToast('期間が見つかりません', 'error');
            return;
        }
        shareModalData = { period, openingHours, exceptions };
        renderShareModal();
        const modal = document.getElementById('period-share-modal');
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        showToast(`読み込みに失敗しました: ${e.message}`, 'error');
    }
}

function closeShareModal() {
    const modal = document.getElementById('period-share-modal');
    modal.hidden = true;
    document.body.style.overflow = '';
    shareModalData = null;
}

function renderShareModal() {
    const { period, openingHours, exceptions } = shareModalData;
    const target = document.getElementById('share-export-target');
    target.innerHTML = buildShareCardHtml(period, openingHours, exceptions);
    document.getElementById('share-template-text').textContent = buildShareTemplate(period);
}

function buildShareCardHtml(period, openingHours, exceptions) {
    const hoursByDow = {};
    for (const h of (openingHours || [])) hoursByDow[h.day_of_week] = h;
    const excByDate = {};
    for (const e of (exceptions || [])) {
        if (e.exception_date) excByDate[e.exception_date] = e;
    }

    const start = parseLocalDate(period.start_date);
    const end = parseLocalDate(period.end_date);
    const months = shareGetMonthsInRange(start, end);
    const monthsHtml = months.map(m => buildShareMonthHtml(m, start, end, hoursByDow, excByDate)).join('');

    const titleHtml = escapeHtml(period.name) + ' シフト希望提出のご案内';
    const orgHtml = currentOrgName ? `<p class="shcard-org">${escapeHtml(currentOrgName)}</p>` : '';
    const rangeLabel = `対象期間: ${formatJpDate(start)} 〜 ${formatJpDate(end)}`;
    let deadlineLabel = '';
    if (period.submission_deadline) {
        const deadline = new Date(period.submission_deadline);
        deadlineLabel = `<span class="shcard-pill deadline">提出期限: ${formatJpDateTime(deadline)}まで</span>`;
    }
    const loginUrl = `${window.location.origin}/login`;

    return `
        <div class="shcard-brand">
            <div class="shcard-brand-icon">シ</div>
            <div class="shcard-brand-text">SHIFREE</div>
        </div>
        <h1 class="shcard-title">${titleHtml}</h1>
        ${orgHtml}
        <div class="shcard-info-row">
            <span class="shcard-pill">${escapeHtml(rangeLabel)}</span>
            ${deadlineLabel}
        </div>
        <div class="shcard-calendar-container">${monthsHtml}</div>
        <div class="shcard-legend">
            <div class="shcard-legend-item"><span class="shcard-legend-swatch in-range"></span>希望提出対象日</div>
            <div class="shcard-legend-item"><span class="shcard-legend-swatch out-of-range"></span>期間外</div>
            <div class="shcard-legend-item"><span class="shcard-legend-swatch closed"></span>休業日</div>
        </div>
        <div class="shcard-footer">
            <p>下記URLからログインして希望シフトをご提出ください</p>
            <p><span class="shcard-url">${escapeHtml(loginUrl)}</span></p>
        </div>
    `;
}

function buildShareMonthHtml(month, periodStart, periodEnd, hoursByDow, excByDate) {
    const year = month.getFullYear();
    const mo = month.getMonth();
    const firstDow = new Date(year, mo, 1).getDay();
    const daysInMonth = new Date(year, mo + 1, 0).getDate();

    const headers = SHARE_WEEKDAYS.map((d, i) => {
        const cls = i === 0 ? 'sun' : i === 6 ? 'sat' : '';
        return `<div class="shcard-header ${cls}">${d}</div>`;
    }).join('');

    let cells = '';
    for (let i = 0; i < firstDow; i++) {
        cells += '<div class="shcard-day empty"></div>';
    }
    for (let d = 1; d <= daysInMonth; d++) {
        const date = new Date(year, mo, d);
        const dateStr = `${year}-${String(mo + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const inRange = date >= periodStart && date <= periodEnd;
        const dow = date.getDay();

        // Resolve time: exception > regular opening hours
        const exc = excByDate[dateStr];
        const regular = hoursByDow[dow];
        let timeLabel = null;
        let isClosed = false;
        if (exc) {
            if (exc.is_closed) isClosed = true;
            else if (exc.start_time && exc.end_time) timeLabel = `${formatShortTime(exc.start_time)}〜${formatShortTime(exc.end_time)}`;
        } else if (regular) {
            if (regular.is_closed) isClosed = true;
            else if (regular.start_time && regular.end_time) timeLabel = `${formatShortTime(regular.start_time)}〜${formatShortTime(regular.end_time)}`;
        }

        const classes = ['shcard-day'];
        if (!inRange) classes.push('out-of-range');
        else if (isClosed) classes.push('closed');
        else classes.push('in-range');
        if (dow === 0) classes.push('sun');
        if (dow === 6) classes.push('sat');

        const timeHtml = inRange
            ? (isClosed
                ? '<span class="shcard-day-time closed-label">休</span>'
                : (timeLabel ? `<span class="shcard-day-time">${escapeHtml(timeLabel)}</span>` : ''))
            : '';

        cells += `
            <div class="${classes.join(' ')}">
                <span class="shcard-day-num">${d}</span>
                ${timeHtml}
            </div>
        `;
    }

    return `
        <div class="shcard-month">
            <div class="shcard-month-title">${year}年${mo + 1}月</div>
            <div class="shcard-grid">${headers}${cells}</div>
        </div>
    `;
}

function buildShareTemplate(period) {
    const start = parseLocalDate(period.start_date);
    const end = parseLocalDate(period.end_date);
    const startStr = formatJpDate(start);
    const endStr = formatJpDate(end);
    let deadlineLine = '';
    if (period.submission_deadline) {
        deadlineLine = `\n提出期限: ${formatJpDateTime(new Date(period.submission_deadline))}まで`;
    }
    const loginUrl = `${window.location.origin}/login`;
    return `【シフト希望提出のお願い】

期間: ${startStr} 〜 ${endStr}${deadlineLine}

下記リンクからシフリーにログインして、
希望シフトをご提出ください。

${loginUrl}

添付のカレンダー画像もご参照ください。
よろしくお願いします。`;
}

async function shareDownloadPng() {
    if (!shareModalData || !window.html2canvas) {
        showToast('ダウンロードライブラリの読み込み中です', 'warning');
        return;
    }
    try {
        const target = document.getElementById('share-export-target');
        const canvas = await window.html2canvas(target, { scale: 2, backgroundColor: '#ffffff' });
        const link = document.createElement('a');
        link.download = sharedFileName(shareModalData.period.name, 'png');
        link.href = canvas.toDataURL('image/png');
        link.click();
        showToast('PNGを保存しました', 'success');
    } catch (e) {
        showToast(`PNG保存に失敗: ${e.message || e}`, 'error');
    }
}

async function shareDownloadPdf() {
    if (!shareModalData || !window.html2canvas || !window.jspdf) {
        showToast('ダウンロードライブラリの読み込み中です', 'warning');
        return;
    }
    try {
        const target = document.getElementById('share-export-target');
        const canvas = await window.html2canvas(target, { scale: 2, backgroundColor: '#ffffff' });
        const imgData = canvas.toDataURL('image/png');
        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
        const pageWidth = 210;
        const pageHeight = 297;
        const imgWidth = pageWidth - 20;
        const imgHeight = canvas.height * imgWidth / canvas.width;
        pdf.addImage(imgData, 'PNG', 10, 10, imgWidth, Math.min(imgHeight, pageHeight - 20));
        pdf.save(sharedFileName(shareModalData.period.name, 'pdf'));
        showToast('PDFを保存しました', 'success');
    } catch (e) {
        showToast(`PDF保存に失敗: ${e.message || e}`, 'error');
    }
}

async function shareCopyMessage() {
    const text = document.getElementById('share-template-text').textContent;
    try {
        await navigator.clipboard.writeText(text);
        showToast('メッセージをコピーしました', 'success');
    } catch (e) {
        showToast('コピーに失敗しました', 'error');
    }
}

// --- Share helpers ---

function sharedFileName(periodName, ext) {
    const safe = (periodName || '募集案内').replace(/[\\/:*?"<>|]/g, '_');
    return `shifree-${safe}-募集案内.${ext}`;
}

function parseLocalDate(str) {
    // 'YYYY-MM-DD' → local Date at midnight (avoid UTC shift from `new Date(str)`)
    if (!str) return null;
    const parts = str.split('-').map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2]);
}

function shareGetMonthsInRange(start, end) {
    const months = [];
    const current = new Date(start.getFullYear(), start.getMonth(), 1);
    const last = new Date(end.getFullYear(), end.getMonth(), 1);
    while (current <= last) {
        months.push(new Date(current));
        current.setMonth(current.getMonth() + 1);
    }
    return months;
}

function formatJpDate(d) {
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

function formatJpDateTime(d) {
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatShortTime(timeStr) {
    // '17:00:00' or '17:00' → '17:00'
    if (!timeStr) return '';
    return timeStr.slice(0, 5);
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
        scheduleVersion = schedule && schedule.schedule_version ? schedule.schedule_version : null;
        openingHoursData = openingHours || {};
        adminCalendarEvents = calEvents || [];

        renderScheduleProgress(schedule);
        updateScheduleButtons(schedule);

        renderSubmissionsSummary(submissions);
        buildDayAggregatedData();
        renderBuilderCalendar();
        renderHoursSummary();
        renderSyncStatusSummary(schedule);
        setClean('schedule');
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
        const dateStr = toLocalDateStr(d);
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
                closedLabel.textContent = '休業';
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
            <div class="day-popup-label">営業時間</div>
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
        container.innerHTML = '<span style="color:#999;font-size:0.85em;">営業時間未設定</span>';
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
    setDirty('schedule');

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
    setDirty('schedule');

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


function renderSyncStatusSummary(schedule) {
    const card = document.getElementById('sync-status-card');
    const container = document.getElementById('sync-status-summary');
    if (!card || !container) return;

    if (!schedule || schedule.status !== 'confirmed' || !schedule.sync_summary) {
        card.style.display = 'none';
        return;
    }

    card.style.display = 'block';
    const s = schedule.sync_summary;
    const rows = [];
    if (s.synced > 0) rows.push(`<div class="flex-between mb-4"><span>同期済み</span><span class="sync-count sync-count-success">${s.synced}</span></div>`);
    if (s.reauth_required > 0) rows.push(`<div class="flex-between mb-4"><span>要再認証</span><span class="sync-count sync-count-warning">${s.reauth_required}</span></div>`);
    if (s.failed > 0) rows.push(`<div class="flex-between mb-4"><span>同期失敗</span><span class="sync-count sync-count-danger">${s.failed}</span></div>`);
    if (s.pending > 0) rows.push(`<div class="flex-between mb-4"><span>未同期</span><span class="sync-count sync-count-neutral">${s.pending}</span></div>`);

    const allSynced = s.synced === s.total;
    const statusMsg = allSynced
        ? '<p class="help-text" style="color:var(--color-success-600);margin-top:8px;">全員のカレンダーに同期済みです</p>'
        : `<p class="help-text" style="margin-top:8px;">${s.total - s.synced}件が未同期です。スタッフに再ログインを依頼してください。</p>`;

    container.innerHTML = rows.join('') + statusMsg;
}

const SCHEDULE_STEPS_FULL = [
    { key: 'draft', label: '下書き', icon: '1' },
    { key: 'pending_approval', label: '承認待ち', icon: '2' },
    { key: 'approved', label: '承認済み', icon: '3' },
    { key: 'confirmed', label: '確定', icon: '✓' },
];

const SCHEDULE_STEPS_SIMPLE = [
    { key: 'draft', label: '下書き', icon: '1' },
    { key: 'confirmed', label: '確定', icon: '✓' },
];

function renderScheduleProgress(schedule) {
    const container = document.getElementById('schedule-progress');
    if (!container) return;

    const status = schedule?.status || null;
    const isRejected = status === 'rejected';
    const steps = workflowState.approval_required ? SCHEDULE_STEPS_FULL : SCHEDULE_STEPS_SIMPLE;

    if (!status) {
        container.innerHTML = '<div class="progress-hint" style="margin:0;width:100%;text-align:center;">シフトを作成して保存すると、進捗が表示されます</div>';
        return;
    }

    const statusIndex = steps.findIndex(s => s.key === status);
    const activeIndex = isRejected ? 0 : statusIndex;  // Rejected goes back to step 1

    let html = '';
    for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        let cls = '';
        let icon = step.icon;

        if (isRejected && i === 1 && workflowState.approval_required) {
            cls = 'rejected';
            icon = '!';
        } else if (i < activeIndex) {
            cls = 'completed';
            icon = '✓';
        } else if (i === activeIndex) {
            cls = isRejected ? 'rejected' : 'active';
        }

        html += `<div class="progress-step ${cls}">`;
        html += `<span class="progress-dot">${icon}</span>`;
        html += `<span class="progress-label">${isRejected && i === 0 ? '要修正' : step.label}</span>`;
        html += '</div>';
    }

    // Action hint
    const hintsFull = {
        draft: '「承認申請」で事業主に送信',
        pending_approval: '事業主の承認を待っています',
        approved: '「確定・カレンダー同期」で反映',
        confirmed: 'カレンダーに同期済み',
        rejected: '修正して再度「承認申請」してください',
    };
    const hintsSimple = {
        draft: '「シフトを確定」でカレンダーに反映',
        confirmed: 'カレンダーに同期済み',
    };
    const hints = workflowState.approval_required ? hintsFull : hintsSimple;
    html += `<span class="progress-hint">${hints[status] || ''}</span>`;

    container.innerHTML = html;
}

function updateScheduleButtons(schedule) {
    const status = schedule?.status || null;
    const saveBtn = document.getElementById('btn-save-schedule');
    const submitBtn = document.getElementById('btn-submit-approval');
    const confirmBtn = document.getElementById('confirm-btn');

    // Save: available for draft, rejected, or no schedule
    saveBtn.style.display = (!status || status === 'draft' || status === 'rejected') ? 'inline-flex' : 'none';

    if (workflowState.approval_required) {
        // Full flow: submit for approval, confirm only when approved
        submitBtn.style.display = (status === 'draft' || status === 'rejected') ? 'inline-flex' : 'none';
        confirmBtn.style.display = (status === 'approved') ? 'inline-flex' : 'none';
        if (confirmBtn) {
            confirmBtn.innerHTML = '<i data-lucide="calendar-check" style="width:15px;height:15px;"></i> 確定・カレンダー同期';
        }
    } else {
        // Simple flow: hide submit, confirm from draft directly
        submitBtn.style.display = 'none';
        confirmBtn.style.display = (status === 'draft') ? 'inline-flex' : 'none';
        if (confirmBtn) {
            confirmBtn.innerHTML = '<i data-lucide="calendar-check" style="width:15px;height:15px;"></i> シフトを確定・カレンダー同期';
        }
    }
    if (window.lucide) lucide.createIcons();
}

async function saveSchedule() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;
    try {
        const result = await api.post(`/api/admin/periods/${periodId}/schedule`, {
            entries: scheduleEntries,
            expected_version: scheduleVersion,
        });
        // Update version so subsequent saves stay in sync
        if (result && result.schedule_version) {
            scheduleVersion = result.schedule_version;
        }
        setClean('schedule');
        showToast('スケジュールを保存しました', 'success');
    } catch (e) {
        // Detect optimistic locking conflict (409 from server)
        if (e.code === 'SCHEDULE_VERSION_MISMATCH' || /SCHEDULE_VERSION_MISMATCH/.test(e.message || '')) {
            showConfirmDialog(
                '他の管理者が編集しています',
                'このシフトは他の管理者によって更新されました。最新の状態を再読込しますか？（未保存の変更は失われます）',
                'btn-primary',
                '再読込',
                () => {
                    if (currentPeriod) loadScheduleForPeriod(currentPeriod.id);
                },
            );
            return;
        }
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
                const summary = result.sync_summary || {};
                const syncResults = result.sync_results || [];
                const success = summary.synced || syncResults.filter(r => r.success).length;
                const needsAction = summary.needs_worker_action || 0;
                const failed = summary.failed || 0;

                let msg = `確定完了: ${success}件同期成功`;
                if (needsAction > 0) msg += `, ${needsAction}件は本人によるカレンダー追加が必要`;
                if (failed > 0) msg += `, ${failed}件失敗`;
                showToast(msg, success > 0 ? 'success' : 'warning');
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
        setClean('reminder');
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
        setClean('reminder');
        showToast('リマインド設定を保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

// --- Level / Overlap / Min-Attendance Settings (Phase A) ---

let levelSystemState = { enabled: false, tiers: [] };
let overlapCheckState = { enabled: false, scope: 'same_tier' };
let minAttendanceState = {
    mode: 'disabled', unit: 'count',
    org_wide_count_per_week: 1, org_wide_hours_per_week: 8.0,
    count_drafts: true, lookback_periods: 1,
};

async function loadLevelSettings() {
    try {
        const data = await api.get('/api/admin/settings/levels');
        levelSystemState = {
            enabled: !!data.enabled,
            tiers: (data.tiers || []).map(t => ({
                key: t.key, label: t.label, order: t.order,
                member_count: t.member_count || 0,
            })),
        };
        renderLevelSettings();
        setClean('levels');
    } catch (e) {
        console.warn('Failed to load level settings:', e);
    }
}

function renderLevelSettings() {
    const enabledToggle = document.getElementById('level-system-enabled');
    const tiersSection = document.getElementById('level-tiers-section');
    const list = document.getElementById('level-tiers-list');
    if (!enabledToggle || !tiersSection || !list) return;

    enabledToggle.checked = levelSystemState.enabled;
    tiersSection.style.display = levelSystemState.enabled ? '' : 'none';

    if (!levelSystemState.tiers.length) {
        list.innerHTML = '<p class="help-text" style="color:var(--color-neutral-400);">レベルがまだ設定されていません</p>';
    } else {
        list.innerHTML = levelSystemState.tiers.map((t, i) => `
            <div class="level-tier-row">
                <span class="tier-label"><strong>${escapeHtml(t.label)}</strong> <span style="color:var(--color-neutral-400);font-size:0.85em;">(${escapeHtml(t.key)})</span></span>
                <span class="tier-count">${t.member_count}名</span>
                <button class="btn btn-outline btn-sm" data-action="moveLevelTierUp" data-key="${escapeHtml(t.key)}" ${i === 0 ? 'disabled' : ''} title="上へ"><i data-lucide="chevron-up" style="width:12px;height:12px;"></i></button>
                <button class="btn btn-outline btn-sm" data-action="moveLevelTierDown" data-key="${escapeHtml(t.key)}" ${i === levelSystemState.tiers.length - 1 ? 'disabled' : ''} title="下へ"><i data-lucide="chevron-down" style="width:12px;height:12px;"></i></button>
                <button class="btn btn-outline btn-sm" data-action="removeLevelTier" data-key="${escapeHtml(t.key)}" data-label="${escapeHtml(t.label)}" data-count="${t.member_count}" title="削除"><i data-lucide="trash-2" style="width:12px;height:12px;"></i></button>
            </div>
        `).join('');
    }
    if (window.lucide) lucide.createIcons();
}

function addLevelTier() {
    const keyInput = document.getElementById('level-new-key');
    const labelInput = document.getElementById('level-new-label');
    const key = (keyInput.value || '').trim();
    const label = (labelInput.value || '').trim();
    if (!key || !label) {
        showToast('キーと表示名の両方を入力してください', 'warning');
        return;
    }
    if (!/^[a-z][a-z0-9_]{0,31}$/.test(key)) {
        showToast('キーは半角英小文字・数字・アンダースコアのみ（先頭は英字）', 'warning');
        return;
    }
    if (levelSystemState.tiers.some(t => t.key === key)) {
        showToast('同じキーが既に存在します', 'warning');
        return;
    }
    levelSystemState.tiers.push({
        key, label, order: levelSystemState.tiers.length + 1, member_count: 0,
    });
    keyInput.value = '';
    labelInput.value = '';
    renderLevelSettings();
    setDirty('levels');
}

function removeLevelTier(key, label, memberCount) {
    const proceed = () => {
        levelSystemState.tiers = levelSystemState.tiers.filter(t => t.key !== key);
        renderLevelSettings();
        setDirty('levels');
    };
    if (memberCount > 0) {
        showConfirmDialog(
            `「${label}」を削除しますか？`,
            `現在 ${memberCount}名のメンバーがこのレベルに割り当てられています。削除するとそのメンバーのレベルは未設定になります。`,
            'btn-danger', '削除する', proceed,
        );
    } else {
        proceed();
    }
}

function moveLevelTier(key, direction) {
    const idx = levelSystemState.tiers.findIndex(t => t.key === key);
    if (idx < 0) return;
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= levelSystemState.tiers.length) return;
    const tiers = levelSystemState.tiers;
    [tiers[idx], tiers[newIdx]] = [tiers[newIdx], tiers[idx]];
    tiers.forEach((t, i) => { t.order = i + 1; });
    renderLevelSettings();
    setDirty('levels');
}

async function saveLevelSettings() {
    const enabled = document.getElementById('level-system-enabled').checked;
    const currentKeys = new Set(levelSystemState.tiers.map(t => t.key));

    try {
        const serverCfg = await api.get('/api/admin/settings/levels');
        const serverKeys = new Set((serverCfg.tiers || []).map(t => t.key));
        const removedTierKeys = [...serverKeys].filter(k => !currentKeys.has(k));

        await api.put('/api/admin/settings/levels', {
            enabled,
            tiers: levelSystemState.tiers.map(t => ({ key: t.key, label: t.label, order: t.order })),
            removed_tier_keys: removedTierKeys,
        });
        levelSystemState.enabled = enabled;
        showToast('レベル設定を保存しました', 'success');
        await loadLevelSettings();  // resets setClean('levels')
        membersTabLoaded = false;
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

async function loadOverlapCheckSettings() {
    try {
        const data = await api.get('/api/admin/settings/overlap-check');
        overlapCheckState = {
            enabled: !!data.enabled,
            scope: data.scope || 'same_tier',
        };
        const el = document.getElementById('overlap-check-enabled');
        if (el) el.checked = overlapCheckState.enabled;
        setClean('overlap-check');
    } catch (e) {
        console.warn('Failed to load overlap check settings:', e);
    }
}

async function saveOverlapCheckSettings() {
    const enabled = document.getElementById('overlap-check-enabled').checked;
    try {
        await api.put('/api/admin/settings/overlap-check', { enabled, scope: 'same_tier' });
        overlapCheckState.enabled = enabled;
        setClean('overlap-check');
        showToast('重複チェック設定を保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

async function loadMinAttendanceSettings() {
    try {
        const data = await api.get('/api/admin/settings/min-attendance');
        minAttendanceState = {
            mode: data.mode || 'disabled',
            unit: data.unit || 'count',
            org_wide_count_per_week: data.org_wide_count_per_week ?? 1,
            org_wide_hours_per_week: data.org_wide_hours_per_week ?? 8.0,
            count_drafts: data.count_drafts !== false,
            lookback_periods: data.lookback_periods ?? 1,
        };
        renderMinAttendanceSettings();
        setClean('min-attendance');
    } catch (e) {
        console.warn('Failed to load min attendance settings:', e);
    }
}

function renderMinAttendanceSettings() {
    const modeEl = document.getElementById('min-attendance-mode');
    const configEl = document.getElementById('min-attendance-config');
    const unitEl = document.getElementById('min-attendance-unit');
    const orgWideEl = document.getElementById('min-attendance-org-wide');
    const countFieldEl = document.getElementById('min-attendance-count-field');
    const hoursFieldEl = document.getElementById('min-attendance-hours-field');
    const countEl = document.getElementById('min-attendance-count');
    const hoursEl = document.getElementById('min-attendance-hours');
    const countDraftsEl = document.getElementById('min-attendance-count-drafts');
    const lookbackEl = document.getElementById('min-attendance-lookback');

    if (!modeEl) return;
    modeEl.value = minAttendanceState.mode;
    unitEl.value = minAttendanceState.unit;
    countEl.value = minAttendanceState.org_wide_count_per_week;
    hoursEl.value = minAttendanceState.org_wide_hours_per_week;
    countDraftsEl.checked = minAttendanceState.count_drafts;
    lookbackEl.value = minAttendanceState.lookback_periods;

    configEl.style.display = minAttendanceState.mode === 'disabled' ? 'none' : '';
    orgWideEl.style.display = minAttendanceState.mode === 'org_wide' ? '' : 'none';

    const showCount = minAttendanceState.unit === 'count' || minAttendanceState.unit === 'both';
    const showHours = minAttendanceState.unit === 'hours' || minAttendanceState.unit === 'both';
    countFieldEl.style.display = showCount ? '' : 'none';
    hoursFieldEl.style.display = showHours ? '' : 'none';
}

async function saveMinAttendanceSettings() {
    const payload = {
        mode: document.getElementById('min-attendance-mode').value,
        unit: document.getElementById('min-attendance-unit').value,
        org_wide_count_per_week: Number(document.getElementById('min-attendance-count').value),
        org_wide_hours_per_week: Number(document.getElementById('min-attendance-hours').value),
        count_drafts: document.getElementById('min-attendance-count-drafts').checked,
        lookback_periods: Number(document.getElementById('min-attendance-lookback').value),
    };
    try {
        await api.put('/api/admin/settings/min-attendance', payload);
        minAttendanceState = payload;
        setClean('min-attendance');
        showToast('最低出勤設定を保存しました', 'success');
        membersTabLoaded = false;
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

async function updateMemberAttributes(memberId, updates) {
    try {
        await api.put(`/api/admin/members/${memberId}/attributes`, updates);
    } catch (e) {
        showToast(`メンバー属性の更新に失敗しました: ${e.message}`, 'error');
        throw e;
    }
}

// --- Workflow Settings (approval process) — Phase A' ---

let workflowState = {
    approval_required: false,
    owner_count: 0,
    pending_schedules_count: 0,
};

async function loadWorkflowSettings() {
    try {
        const data = await api.get('/api/admin/settings/workflow');
        workflowState = {
            approval_required: !!data.approval_required,
            owner_count: data.owner_count ?? 0,
            pending_schedules_count: data.pending_schedules_count ?? 0,
        };
        renderWorkflowSettings();
        renderOwnerInviteCard();
        setClean('workflow');
    } catch (e) {
        console.warn('Failed to load workflow settings:', e);
    }
}

function renderWorkflowSettings() {
    // Sync checkbox to server-known state. Only called on load/save, not on user click.
    const toggle = document.getElementById('workflow-approval-required');
    if (!toggle) return;
    toggle.checked = workflowState.approval_required;
    updateWorkflowWarning();
}

function updateWorkflowWarning() {
    // Reflect warning banner based on CURRENT checkbox state (not server state),
    // so users see the warning while still toggling ON before saving.
    const toggle = document.getElementById('workflow-approval-required');
    const warning = document.getElementById('workflow-owner-warning');
    if (!toggle || !warning) return;
    const wantsApproval = toggle.checked;
    const needWarn = wantsApproval && workflowState.owner_count < 1;
    warning.style.display = needWarn ? '' : 'none';
}

function renderOwnerInviteCard() {
    const card = document.getElementById('owner-invite-card');
    if (!card) return;
    const show = workflowState.approval_required && workflowState.owner_count < 1;
    card.style.display = show ? '' : 'none';
}

async function saveWorkflowSettings() {
    const enabled = document.getElementById('workflow-approval-required').checked;
    try {
        const result = await api.put('/api/admin/settings/workflow', {
            approval_required: enabled,
        });
        workflowState = {
            approval_required: !!result.approval_required,
            owner_count: result.owner_count ?? 0,
            pending_schedules_count: result.pending_schedules_count ?? 0,
        };
        renderWorkflowSettings();
        renderOwnerInviteCard();
        setClean('workflow');
        showToast('承認プロセス設定を保存しました', 'success');
        // Refresh schedule UI if a period is currently loaded
        if (currentPeriod) {
            loadScheduleForPeriod(currentPeriod.id);
        }
    } catch (e) {
        const msg = e.message || '保存に失敗しました';
        // Revert toggle state on failure
        const toggle = document.getElementById('workflow-approval-required');
        if (toggle) toggle.checked = workflowState.approval_required;
        showToast(msg, 'error');
    }
}

async function inviteOwner() {
    const emailInput = document.getElementById('owner-invite-email');
    const expiresInput = document.getElementById('owner-invite-expires');
    const email = (emailInput?.value || '').trim();
    if (!email) {
        showToast('メールアドレスを入力してください', 'warning');
        return;
    }
    try {
        await api.post('/api/admin/invitations', {
            email,
            role: 'owner',
            expires_in_hours: Number(expiresInput?.value || 168),
        });
        showToast('事業主への招待を作成しました', 'success');
        emailInput.value = '';
        await loadInvitations();
        await loadWorkflowSettings();  // refresh owner_count if already joined via link
    } catch (e) {
        showToast(`招待の作成に失敗しました: ${e.message}`, 'error');
    }
}

function gotoOwnerInvite() {
    // Switch to Members tab and focus owner invite card
    const membersBtn = document.querySelector('.tab-btn[data-tab="members"]');
    if (membersBtn) membersBtn.click();
    setTimeout(() => {
        const card = document.getElementById('owner-invite-card');
        if (card && card.style.display !== 'none') {
            card.scrollIntoView({ behavior: 'smooth', block: 'start' });
            document.getElementById('owner-invite-email')?.focus();
        }
    }, 200);
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
