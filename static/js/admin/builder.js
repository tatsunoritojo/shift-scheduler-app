/**
 * シフト構築タブ: 期間選択 → カレンダー表示 → 日クリック → ワーカー割当 →
 * 保存 / 承認申請 / 確定 (Google Calendar 同期) のメインフロー全体.
 *
 * モジュール内構成:
 *   - 期間選択: loadBuilderPeriodSelect / loadBuilderData / loadScheduleForPeriod
 *   - 集約: buildDayAggregatedData (state.dayAggregatedData の構築)
 *   - 描画: updateBuilderPeriodTitle / renderBuilderCalendar / Day popup /
 *           Coverage timeline / Sidebar (submissions / hours / sync status / progress)
 *   - 操作: toggleWorkerAssignment / applyWorkerTime
 *   - 永続化: saveSchedule / submitForApproval / confirmSchedule
 *
 * 依存:
 *   - state (シフト構築のほぼ全状態)
 *   - api / showToast / escapeHtml / showConfirmDialog
 *   - timeToMinutes / minutesToTime / formatDate (modules/time-utils.js)
 *   - WEEKDAY_NAMES / isAllDayEvent / getEventsForDate / formatSubmittedAt
 *   - renderCalendar (modules/calendar-grid.js)
 *   - setDirty / setClean (admin/dirty-tracker.js)
 *   - openVacancyDialog (admin/vacancy.js, day popup から欠員補充ボタンで起動)
 *   - promptArchiveAfterConfirm (admin/periods.js, 確定後アーカイブ提案)
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { showConfirmDialog } from '../modules/ui-dialogs.js';
import { timeToMinutes, minutesToTime, formatDate } from '../modules/time-utils.js';
import { WEEKDAY_NAMES } from '../modules/date-constants.js';
import { isAllDayEvent, getEventsForDate as _getEventsForDate, formatSubmittedAt } from '../modules/event-utils.js';
import { renderCalendar } from '../modules/calendar-grid.js';
import { state } from './state.js';
import { setDirty, setClean } from './dirty-tracker.js';
import { promptArchiveAfterConfirm } from './periods.js';

// 日 popup のワーカーカード色 (固定パレット, idx % length で巡回)
const WORKER_COLORS = [
    '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899',
    '#06b6d4', '#f97316', '#78716c', '#64748b', '#84cc16',
];

// ---- Period select & data load ----

export async function loadBuilderPeriodSelect() {
    // Builder dropdown は archived を除外（include_archived は default false）
    const periods = await api.get('/api/admin/periods');
    const select = document.getElementById('builder-period-select');
    const previousValue = select.value;
    select.innerHTML = '<option value="">選択してください</option>' +
        periods.map(p => `<option value="${p.id}">${escapeHtml(p.name)} (${p.start_date} 〜 ${p.end_date})</option>`).join('');
    // 直前に選択していた期間がアーカイブされた場合の selection クリア
    if (previousValue && Array.from(select.options).some(o => o.value === previousValue)) {
        select.value = previousValue;
    }
}

export async function loadBuilderData() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) {
        document.getElementById('builder-content').style.display = 'none';
        updateBuilderPeriodTitle(null);
        return;
    }

    // Close any open popup before switching
    closeAdminDayPopup();

    const thisGeneration = ++state.builderLoadGeneration;

    document.getElementById('builder-content').style.display = 'block';

    // Find the period object from the select option text
    const select = document.getElementById('builder-period-select');
    const opt = select.options[select.selectedIndex];
    // Parse dates from option text: "name (YYYY-MM-DD 〜 YYYY-MM-DD)"
    const match = opt.textContent.match(/(\d{4}-\d{2}-\d{2})\s*〜\s*(\d{4}-\d{2}-\d{2})/);
    const periodName = opt.textContent.replace(/\s*\(.*$/, '');
    state.currentPeriod = match ? { id: periodId, name: periodName, start_date: match[1], end_date: match[2] } : null;

    updateBuilderPeriodTitle(state.currentPeriod);

    try {
        // Fetch calendar events in parallel with other data
        const calEventsPromise = api.get(`/api/calendar/events?startDate=${state.currentPeriod.start_date}&endDate=${state.currentPeriod.end_date}&calendarId=primary`)
            .catch(err => { console.warn('カレンダーイベント取得失敗:', err); return []; });

        const [submissions, schedule, workers, openingHours, calEvents] = await Promise.all([
            api.get(`/api/admin/periods/${periodId}/submissions`),
            api.get(`/api/admin/periods/${periodId}/schedule`),
            api.get('/api/admin/workers'),
            api.get(`/api/admin/periods/${periodId}/opening-hours`),
            calEventsPromise,
        ]);

        // Guard: discard stale response if user switched periods during fetch
        if (thisGeneration !== state.builderLoadGeneration) return;

        state.submissionsData = submissions || [];
        state.workersData = workers || [];
        state.scheduleEntries = schedule && schedule.entries ? schedule.entries : [];
        state.scheduleVersion = schedule && schedule.schedule_version ? schedule.schedule_version : null;
        state.openingHoursData = openingHours || {};
        state.adminCalendarEvents = calEvents || [];

        renderScheduleProgress(schedule);
        updateScheduleButtons(schedule);

        renderSubmissionsSummary(submissions);
        buildDayAggregatedData();
        renderBuilderCalendar();
        renderHoursSummary();
        renderSyncStatusSummary(schedule);
        setClean('schedule');
    } catch (e) {
        if (thisGeneration !== state.builderLoadGeneration) return;
        showToast('データの読み込みに失敗しました', 'error');
    }
}

/**
 * 指定期間の schedule を再読込する。SCHEDULE_VERSION_MISMATCH (楽観ロック) や
 * workflow 設定変更後に呼ばれ、ドロップダウンを periodId に揃えてから loadBuilderData
 * を呼ぶ。旧 admin-app.js では関数未定義の pre-existing バグだった (PR10 で実装).
 */
export function loadScheduleForPeriod(periodId) {
    const select = document.getElementById('builder-period-select');
    if (select) {
        const wantValue = String(periodId);
        if (select.value !== wantValue) select.value = wantValue;
    }
    return loadBuilderData();
}

// ---- Aggregation ----

function buildDayAggregatedData() {
    state.dayAggregatedData = {};
    if (!state.currentPeriod) return;

    const start = new Date(state.currentPeriod.start_date);
    const end = new Date(state.currentPeriod.end_date);

    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const dateStr = formatDate(d);
        const oh = state.openingHoursData[dateStr];
        const closed = !oh || oh.is_closed;

        // Build per-worker info for this date
        const workers = [];
        (state.submissionsData || []).forEach(sub => {
            const slot = (sub.slots || []).find(s => s.slot_date === dateStr);
            const isAvailable = slot && slot.is_available;
            const entry = state.scheduleEntries.find(e => e.user_id === sub.user_id && e.shift_date === dateStr);
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

        // 必要人数: その日の曜日に該当する state.staffingDraft の合計
        // (時間帯ごとに違う場合は延べ人数として扱う。MVP では単一値で集約)
        const dayOfWeek = d.getDay();
        const requiredCount = state.staffingDraft
            .filter(r => r.day_of_week === dayOfWeek)
            .reduce((sum, r) => sum + (r.required_count || 0), 0);
        const hasRequirement = state.staffingDraft.some(r => r.day_of_week === dayOfWeek);

        state.dayAggregatedData[dateStr] = {
            closed,
            openingHours: oh,
            workers,
            availableCount,
            assignedCount,
            requiredCount,
            hasRequirement,
        };
    }
}

// ---- Period Title ----

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

// ---- Calendar Rendering ----

function renderBuilderCalendar() {
    const container = document.getElementById('calendar-container');
    if (!state.currentPeriod) {
        container.innerHTML = '<p style="color:#999;">期間が選択されていません</p>';
        return;
    }

    renderCalendar(container, state.currentPeriod.start_date, state.currentPeriod.end_date, state.dayAggregatedData, {
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

            // Badge: assigned/available [/必要]
            if (!data.closed) {
                const badge = document.createElement('div');
                badge.className = 'admin-day-badge';
                badge.textContent = `${data.assignedCount}/${data.availableCount}`;
                cell.appendChild(badge);

                // 必要人数バッジ（設定済の曜日のみ表示、情報のみ）
                // 注意: requiredCount は時間帯合計のため「のべ人数」相当。assignedCount は
                // 1人=1カウントなので、両者を直接比較すると誤判定になる
                // (例: 09-13=2名 + 13-22=3名 を 1人が通しで担当しても assigned=1)。
                // 時間帯別の精緻な充足判定は次フェーズで対応するため、現段階では
                // バッジは情報表示のみとし、不足/充足の色分けは行わない。
                if (data.hasRequirement) {
                    const reqBadge = document.createElement('div');
                    reqBadge.className = 'admin-day-required-badge';
                    reqBadge.textContent = `必要 ${data.requiredCount}`;
                    reqBadge.title = `この曜日の必要人数（時間帯合計のべ）: ${data.requiredCount} 名`;
                    cell.appendChild(reqBadge);
                }
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

// ---- Calendar Event Helpers ----

function getEventsForDate(dateStr) {
    return _getEventsForDate(state.adminCalendarEvents, dateStr);
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

// ---- Day Popup ----

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
                ${worker.entry_id ? `<button class="btn btn-state-warning btn-sm" data-action="openVacancyDialog" data-entry-id="${worker.entry_id}" title="欠員補充" style="margin-left:4px;padding:2px 6px;"><i data-lucide="user-minus" style="width:12px;height:12px;"></i></button>` : ''}
            </div>
        `;
    }

    card.innerHTML = html;
    return card;
}

export function closeAdminDayPopup() {
    const overlay = document.getElementById('admin-day-popup-overlay');
    if (!overlay) return;
    overlay.classList.remove('visible');
    const popup = overlay.querySelector('.day-popup');
    if (popup) popup.classList.remove('visible');
    setTimeout(() => overlay.remove(), 200);
}

// ---- Coverage Timeline ----

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

// ---- Worker Assignment Toggle ----

export function toggleWorkerAssignment(userId, dateStr) {
    const idx = state.scheduleEntries.findIndex(e => e.user_id === userId && e.shift_date === dateStr);
    if (idx >= 0) {
        state.scheduleEntries.splice(idx, 1);
    } else {
        // Find worker's available time from submissions
        const dayData = state.dayAggregatedData[dateStr];
        const worker = dayData ? dayData.workers.find(w => w.user_id === userId) : null;
        state.scheduleEntries.push({
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
    const newData = state.dayAggregatedData[dateStr];
    if (newData) showAdminDayPopup(dateStr, newData);
}

// ---- Apply Worker Time Change ----

export function applyWorkerTime(userId, dateStr) {
    const startInput = document.getElementById(`assigned-start-${userId}`);
    const endInput = document.getElementById(`assigned-end-${userId}`);
    if (!startInput || !endInput) return;

    const entry = state.scheduleEntries.find(e => e.user_id === userId && e.shift_date === dateStr);
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
    const newData = state.dayAggregatedData[dateStr];
    if (tlContainer && newData) {
        renderAdminCoverageTimeline(dateStr, newData, tlContainer);
    }
}

// ---- Sidebar renderers ----

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
    state.scheduleEntries.forEach(e => {
        const uid = e.user_id;
        if (!summary[uid]) {
            const sub = (state.submissionsData || []).find(s => s.user_id === uid);
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
    const steps = state.workflowState.approval_required ? SCHEDULE_STEPS_FULL : SCHEDULE_STEPS_SIMPLE;

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

        if (isRejected && i === 1 && state.workflowState.approval_required) {
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
    const hints = state.workflowState.approval_required ? hintsFull : hintsSimple;
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

    if (state.workflowState.approval_required) {
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

// ---- Persistence ----

export async function saveSchedule() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;
    try {
        const result = await api.post(`/api/admin/periods/${periodId}/schedule`, {
            entries: state.scheduleEntries,
            expected_version: state.scheduleVersion,
        });
        // Update version so subsequent saves stay in sync
        if (result && result.schedule_version) {
            state.scheduleVersion = result.schedule_version;
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
                    if (state.currentPeriod) loadScheduleForPeriod(state.currentPeriod.id);
                },
            );
            return;
        }
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

export async function submitForApproval() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;

    if (state.scheduleEntries.length === 0) {
        showToast('スタッフが割り当てられていません。カレンダーから割当を行ってください。', 'warning');
        return;
    }

    showConfirmDialog(
        '承認申請を送信しますか？',
        `現在のスケジュール（${state.scheduleEntries.length}件のシフト）を事業主に承認申請します。申請後も事業主が差戻した場合は再編集できます。`,
        'btn-state-warning',
        '承認申請を送信',
        async () => {
            try {
                await api.post(`/api/admin/periods/${periodId}/schedule`, { entries: state.scheduleEntries });
                await api.post(`/api/admin/periods/${periodId}/schedule/submit`);
                showToast('承認申請を送信しました', 'success');
            } catch (e) {
                showToast(`承認申請に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

export async function confirmSchedule() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;

    showConfirmDialog(
        'シフトを確定してGoogleカレンダーに同期しますか？',
        '確定すると各スタッフのGoogleカレンダーにシフトが登録されます。この操作は取り消せません。',
        'btn-primary',
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

                // Refresh schedule view to reflect new confirmed state
                await loadBuilderData();

                // 確定後にアーカイブ確認ダイアログを表示
                if (result.period) {
                    promptArchiveAfterConfirm(result.period);
                }
            } catch (e) {
                showToast(`確定に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}
