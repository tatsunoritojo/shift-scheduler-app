import { api, getCurrentUser } from './modules/api-client.js';
import { showToast } from './modules/notification.js';
import { renderCalendar } from './modules/calendar-grid.js';
import { timeToMinutes, minutesToTime } from './modules/time-utils.js';

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

async function init() {
    try {
        currentUser = await getCurrentUser();
        document.getElementById('user-name').textContent = currentUser.display_name || currentUser.email;
        await loadOpeningHours();
        await loadExceptions();
        await loadPeriods();
    } catch (e) {
        console.error('Init error:', e);
    }
}

// --- Tab switching ---
window.switchTab = function(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    if (tabName === 'builder') loadBuilderPeriodSelect();
};

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

window.saveOpeningHours = async function() {
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
};

// --- Exceptions ---
async function loadExceptions() {
    const data = await api.get('/api/admin/opening-hours/exceptions');
    const container = document.getElementById('exceptions-list');

    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:24px;"><p>例外日はまだ設定されていません</p><p class="empty-state-hint">祝日や休校日を上のフォームから追加できます</p></div>';
        return;
    }

    container.innerHTML = `
        <table class="data-table">
            <thead><tr><th>日付</th><th>時間</th><th>理由</th><th></th></tr></thead>
            <tbody>
                ${data.map(e => `
                    <tr>
                        <td>${e.exception_date}</td>
                        <td>${e.is_closed ? '休校' : `${e.start_time}-${e.end_time}`}</td>
                        <td>${e.reason || ''}</td>
                        <td><button class="btn btn-danger" style="padding:4px 12px;font-size:0.85em;"
                            onclick="deleteException(${e.id})">削除</button></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

window.addException = async function() {
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
    } catch (e) {
        showToast(`追加に失敗しました: ${e.message}`, 'error');
    }
};

window.deleteException = async function(id) {
    try {
        await api.delete(`/api/admin/opening-hours/exceptions/${id}`);
        showToast('例外日を削除しました', 'success');
        await loadExceptions();
    } catch (e) {
        showToast(`削除に失敗しました: ${e.message}`, 'error');
    }
};

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
                        <td>${p.name}</td>
                        <td>${p.start_date} 〜 ${p.end_date}</td>
                        <td><span class="badge badge-${p.status}">${statusLabels[p.status] || p.status}</span></td>
                        <td>
                            ${p.status === 'draft' ? `<button class="btn btn-primary" style="padding:4px 12px;font-size:0.85em;" onclick="updatePeriodStatus(${p.id}, 'open')">募集開始</button>` : ''}
                            ${p.status === 'open' ? `<button class="btn btn-warning" style="padding:4px 12px;font-size:0.85em;" onclick="updatePeriodStatus(${p.id}, 'closed')">締切</button>` : ''}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

window.createPeriod = async function() {
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
};

window.updatePeriodStatus = async function(id, status) {
    try {
        await api.put(`/api/admin/periods/${id}`, { status });
        showToast('ステータスを更新しました', 'success');
        await loadPeriods();
    } catch (e) {
        showToast(`更新に失敗しました: ${e.message}`, 'error');
    }
};

// --- Builder ---
async function loadBuilderPeriodSelect() {
    const periods = await api.get('/api/admin/periods');
    const select = document.getElementById('builder-period-select');
    select.innerHTML = '<option value="">選択してください</option>' +
        periods.map(p => `<option value="${p.id}">${p.name} (${p.start_date} 〜 ${p.end_date})</option>`).join('');
}

window.loadBuilderData = async function() {
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
};

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
        el.innerHTML = `<div class="guide-box" style="padding:12px 20px;margin-bottom:16px;"><strong style="font-size:1.05em;">${period.name}</strong><span style="margin-left:12px;color:var(--color-neutral-500);font-size:0.9em;">${period.start_date} 〜 ${period.end_date}</span></div>`;
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

function isAllDayEvent(event) {
    return event.start && event.start.length === 10;
}

function getEventsForDate(dateStr) {
    return adminCalendarEvents.filter(event => {
        const eventStart = (event.start || '').substring(0, 10);
        const eventEnd = (event.end || '').substring(0, 10);
        return eventStart === dateStr || (eventStart < dateStr && eventEnd > dateStr);
    });
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
                    <span class="event-chip-title">${event.summary || 'No Title'}</span>
                    <span class="event-chip-time">終日</span>
                </div>
            `;
        } else {
            const startTime = (event.start || '').substring(11, 16) || '';
            const endTime = (event.end || '').substring(11, 16) || '';
            html += `
                <div class="event-chip event-chip-timed">
                    <span class="event-chip-time">${startTime} - ${endTime}</span>
                    <span class="event-chip-title">${event.summary || 'No Title'}</span>
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
            <button class="day-popup-close" onclick="window.closeAdminDayPopup()">&times;</button>
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
                <span class="admin-worker-name">${worker.user_name}</span>
            </div>
    `;

    if (worker.is_available) {
        const activeClass = worker.is_assigned ? ' active' : '';
        html += `
            <button class="day-popup-toggle${activeClass}"
                onclick="window.toggleWorkerAssignment(${worker.user_id}, '${dateStr}')">
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
                    id="assigned-start-${worker.user_id}" onchange="window.applyWorkerTime(${worker.user_id}, '${dateStr}')">
                <span class="time-separator">〜</span>
                <input type="time" class="form-control popup-time-input" value="${aEnd}"
                    id="assigned-end-${worker.user_id}" onchange="window.applyWorkerTime(${worker.user_id}, '${dateStr}')">
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
window.closeAdminDayPopup = closeAdminDayPopup;

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
        html += `<div class="tl-block" style="left:${left}%;width:${width}%;background:${color};opacity:0.7;" title="${w.user_name}"></div>`;
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
            html += `<span class="tl-legend-item"><span class="tl-legend-dot" style="background:${color};"></span>${w.user_name}</span>`;
        });
        html += '</div>';
    }

    container.innerHTML = html;
}

// --- Worker Assignment Toggle ---

window.toggleWorkerAssignment = function(userId, dateStr) {
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
};

// --- Apply Worker Time Change ---

window.applyWorkerTime = function(userId, dateStr) {
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
};

// --- Sidebar renderers ---

function formatSubmittedAt(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

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
                    <span>${s.user_name || s.user_email}</span>
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
            <span>${s.name}</span>
            <span style="font-weight:600;">${s.hours.toFixed(1)}h (${s.shifts}日)</span>
        </div>
    `).join('');
}

window.saveSchedule = async function() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;
    try {
        await api.post(`/api/admin/periods/${periodId}/schedule`, { entries: scheduleEntries });
        showToast('スケジュールを保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
};

window.submitForApproval = async function() {
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
};

window.confirmSchedule = async function() {
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
};

function showConfirmDialog(title, message, btnClass, btnLabel, onConfirm) {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-dialog-overlay';
    overlay.innerHTML = `
        <div class="confirm-dialog">
            <h3>${title}</h3>
            <p>${message}</p>
            <div class="confirm-dialog-actions">
                <button class="btn btn-outline" id="confirm-cancel">キャンセル</button>
                <button class="btn ${btnClass}" id="confirm-ok">${btnLabel}</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector('#confirm-cancel').onclick = () => overlay.remove();
    overlay.querySelector('#confirm-ok').onclick = () => {
        overlay.remove();
        onConfirm();
    };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
}

init().finally(() => { if (window.lucide) lucide.createIcons(); });
