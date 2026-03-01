import { api, getCurrentUser, getCalendarEvents, getCalendarList } from './modules/api-client.js';
import { renderCalendar } from './modules/calendar-grid.js';
import { calculateAvailableSlots, calculateDetailedSlots } from './modules/shift-calculator.js';
import { timeToMinutes, minutesToTime } from './modules/time-utils.js';
import { showToast } from './modules/notification.js';
import { escapeHtml } from './modules/escape-html.js';

let currentUser = null;
let currentPeriod = null;
let slotData = {};  // dateStr -> { is_available, start_time, end_time, ... }
let cachedCalendarEvents = [];  // Module-level cache for calendar events
let calendarList = [];           // Available Google Calendars
let selectedCalendarIds = [];    // Currently selected calendar IDs
let cachedOpeningHours = null;   // Cached opening hours for recalculation

const WEEKDAY_NAMES_FULL = ['日曜日', '月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日'];

// --- Calc Settings ---
const CALC_SETTINGS_KEY = 'shift_calc_settings';
const DEFAULT_CALC_SETTINGS = { bufferTime: 30, minGapTime: 60 };

function getCalcSettings() {
    try {
        const stored = localStorage.getItem(CALC_SETTINGS_KEY);
        if (stored) {
            const parsed = JSON.parse(stored);
            return { ...DEFAULT_CALC_SETTINGS, ...parsed };
        }
    } catch (e) { /* ignore */ }
    return { ...DEFAULT_CALC_SETTINGS };
}

function saveCalcSettings(settings) {
    localStorage.setItem(CALC_SETTINGS_KEY, JSON.stringify(settings));
}

function renderCalcSettingsPanel() {
    const container = document.getElementById('calc-settings-container');
    if (!container) return;

    const settings = getCalcSettings();
    container.innerHTML = `
        <div class="calc-settings-body" id="calc-settings-body" style="display:none;">
            <p class="help-text" style="margin-bottom:4px;">開校時間からGoogleカレンダーの予定を差し引き、勤務可能な時間帯を自動計算しています。</p>
            <p class="help-text" style="margin-bottom:12px;">計算ロジック: 開校時間 − 予定の時間 − 前後バッファ = 勤務可能時間。残った空き時間が最低勤務時間より短い場合は除外されます。</p>
            <div class="calc-settings-row">
                <label class="calc-settings-label">移動時間（前後バッファ）</label>
                <div class="calc-settings-input-group">
                    <input type="range" id="calc-buffer-time" class="calc-settings-range"
                        min="0" max="120" step="5" value="${settings.bufferTime}"
                        oninput="document.getElementById('calc-buffer-val').textContent=this.value">
                    <span class="calc-settings-value"><span id="calc-buffer-val">${settings.bufferTime}</span> 分</span>
                </div>
                <div class="field-hint">予定の前後に確保する余裕時間です。通勤や準備の時間を考慮してください。</div>
            </div>
            <div class="calc-settings-row">
                <label class="calc-settings-label">最低勤務時間</label>
                <div class="calc-settings-input-group">
                    <input type="range" id="calc-mingap-time" class="calc-settings-range"
                        min="15" max="480" step="15" value="${settings.minGapTime}"
                        oninput="document.getElementById('calc-mingap-val').textContent=this.value">
                    <span class="calc-settings-value"><span id="calc-mingap-val">${settings.minGapTime}</span> 分</span>
                </div>
                <div class="field-hint">空き時間がこの値より短い場合、勤務不可として除外されます。</div>
            </div>
            <div class="calc-settings-actions">
                <button class="btn btn-primary btn-sm" onclick="window.applyCalcSettings()">適用</button>
                <button class="btn btn-outline btn-sm" onclick="window.resetCalcSettings()">デフォルトに戻す</button>
            </div>
        </div>
    `;
}

window.toggleCalcSettings = function() {
    const body = document.getElementById('calc-settings-body');
    if (!body) return;
    const isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : '';
    const btn = document.getElementById('calc-settings-toggle-btn');
    if (btn) btn.classList.toggle('active', !isOpen);
};

window.applyCalcSettings = function() {
    const bufferTime = parseInt(document.getElementById('calc-buffer-time').value, 10);
    const minGapTime = parseInt(document.getElementById('calc-mingap-time').value, 10);
    saveCalcSettings({ bufferTime, minGapTime });
    recalculateSlots();
    renderAvailabilityCalendar();
    updateSlotSummary();
    showToast('計算設定を適用しました', 'success');
};

window.resetCalcSettings = function() {
    saveCalcSettings({ ...DEFAULT_CALC_SETTINGS });
    renderCalcSettingsPanel();
    recalculateSlots();
    renderAvailabilityCalendar();
    updateSlotSummary();
    showToast('デフォルト設定に戻しました', 'info');
};

function formatSubmittedAt(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} 提出`;
}

async function init() {
    try {
        currentUser = await getCurrentUser();
        document.getElementById('user-name').textContent = currentUser.display_name || currentUser.email;
        await loadPeriods();
    } catch (e) {
        console.error('Init error:', e);
    }
}

async function loadPeriods() {
    const container = document.getElementById('periods-list');
    try {
        const periods = await api.get('/api/worker/periods');
        if (!periods || periods.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>現在提出可能なシフト期間はありません</p><p class="empty-state-hint">管理者がシフト期間を作成し「募集中」にすると、ここに表示されます</p></div>';
            return;
        }

        container.innerHTML = periods.map(p => {
            let statusHtml;
            if (p.submission_status) {
                const submittedLabel = formatSubmittedAt(p.submitted_at);
                statusHtml = `<div style="text-align:right;"><span class="badge badge-submitted">提出済</span><div style="color:#999;font-size:0.78em;margin-top:4px;">${submittedLabel}</div></div>`;
            } else {
                statusHtml = `<span class="badge badge-open">未提出</span>`;
            }
            return `
                <div class="card" style="cursor:pointer;" onclick="window.selectPeriod(${p.id})">
                    <div class="flex-between">
                        <div>
                            <strong>${escapeHtml(p.name)}</strong>
                            <div style="color:#666;font-size:0.9em;">${p.start_date} 〜 ${p.end_date}</div>
                            ${p.submission_status ? '<div style="color:#16a34a;font-size:0.82em;margin-top:2px;">クリックして内容を確認・再提出</div>' : ''}
                        </div>
                        <div>${statusHtml}</div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p>読み込みに失敗しました</p><p class="empty-state-hint">ネットワーク接続を確認して、ページを再読み込みしてください</p></div>`;
    }
}

window.selectPeriod = async function(periodId) {
    try {
        const periods = await api.get('/api/worker/periods');
        currentPeriod = periods.find(p => p.id === periodId);
        if (!currentPeriod) return;

        document.getElementById('period-select-section').style.display = 'none';
        document.getElementById('availability-section').style.display = 'block';
        document.getElementById('period-title').textContent = currentPeriod.name;

        // Show resubmission banner if already submitted
        let bannerEl = document.getElementById('resubmit-banner');
        if (!bannerEl) {
            bannerEl = document.createElement('div');
            bannerEl.id = 'resubmit-banner';
            const section = document.getElementById('availability-section');
            section.insertBefore(bannerEl, section.children[1]);
        }
        if (currentPeriod.submission_status) {
            const submittedLabel = formatSubmittedAt(currentPeriod.submitted_at);
            bannerEl.className = 'guide-box';
            bannerEl.style.cssText = 'background:var(--color-warning-50);border-color:var(--color-warning-100);';
            bannerEl.innerHTML = `<div class="guide-box-title" style="color:var(--color-warning-600);">前回の提出内容を表示しています</div><p style="margin:0;font-size:0.9em;color:var(--color-neutral-600);">最終提出: ${submittedLabel}。内容を変更して再提出できます。再提出すると前回の内容は上書きされます。</p>`;
        } else {
            bannerEl.className = '';
            bannerEl.style.cssText = '';
            bannerEl.innerHTML = '';
        }

        await loadCalendarList();
        await loadAvailabilityData();
    } catch (e) {
        showToast('データの読み込みに失敗しました', 'error');
    }
};

// --- Calendar list ---

async function loadCalendarList() {
    calendarList = [];
    selectedCalendarIds = [];
    try {
        calendarList = await getCalendarList();
        // Default: select only calendars the user owns (primary + self-created)
        selectedCalendarIds = calendarList
            .filter(c => c.accessRole === 'owner')
            .map(c => c.id);
        // Fallback: if no owner calendars found, select primary
        if (selectedCalendarIds.length === 0) {
            const primary = calendarList.find(c => c.primary);
            if (primary) selectedCalendarIds = [primary.id];
        }
    } catch (e) {
        console.warn('Could not fetch calendar list:', e);
    }
    renderCalendarSelector();
}

function renderCalendarSelector() {
    const container = document.getElementById('calendar-selector');
    const card = document.getElementById('calendar-selector-card');
    if (!container) return;

    if (calendarList.length === 0) {
        if (card) card.style.display = 'none';
        return;
    }

    if (card) card.style.display = '';

    // Group: owner calendars vs shared/other calendars
    const ownCalendars = calendarList.filter(c => c.accessRole === 'owner');
    const sharedCalendars = calendarList.filter(c => c.accessRole !== 'owner');

    let html = '';

    if (ownCalendars.length > 0) {
        html += '<div class="cal-group">';
        html += '<div class="cal-group-label">自分のカレンダー</div>';
        html += '<div class="cal-group-items">';
        html += ownCalendars.map(cal => renderCalendarItem(cal)).join('');
        html += '</div></div>';
    }

    if (sharedCalendars.length > 0) {
        html += '<div class="cal-group">';
        html += '<div class="cal-group-label">その他のカレンダー</div>';
        html += '<div class="cal-group-items">';
        html += sharedCalendars.map(cal => renderCalendarItem(cal)).join('');
        html += '</div></div>';
    }

    container.innerHTML = html;
}

function renderCalendarItem(cal) {
    const checked = selectedCalendarIds.includes(cal.id) ? 'checked' : '';
    const colorDot = `<span class="cal-color-dot" style="background:${cal.backgroundColor}"></span>`;
    const label = cal.summary || cal.id;
    const primaryTag = cal.primary ? ' <span class="cal-primary-tag">メイン</span>' : '';
    // Escape the calendar ID for use in HTML attributes
    const escapedId = cal.id.replace(/"/g, '&quot;');
    return `
        <label class="cal-selector-item">
            <input type="checkbox" value="${escapedId}" ${checked}
                onchange="window.onCalendarSelectionChange()">
            ${colorDot}
            <span class="cal-selector-name">${label}${primaryTag}</span>
        </label>
    `;
}

window.onCalendarSelectionChange = async function() {
    const checkboxes = document.querySelectorAll('#calendar-selector input[type="checkbox"]');
    selectedCalendarIds = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.value);

    // Re-fetch events and recalculate
    await fetchAndCacheEvents();
    recalculateSlots();
    renderAvailabilityCalendar();
    updateSlotSummary();
};

// --- Data loading ---

async function fetchAndCacheEvents() {
    cachedCalendarEvents = [];
    if (selectedCalendarIds.length === 0 || !currentPeriod) return;

    const fetches = selectedCalendarIds.map(calId =>
        getCalendarEvents(currentPeriod.start_date, currentPeriod.end_date, calId)
            .then(events => events.map(e => ({ ...e, calendarId: calId })))
            .catch(err => {
                console.warn(`Failed to fetch events from calendar ${calId}:`, err);
                return [];
            })
    );

    const results = await Promise.all(fetches);
    cachedCalendarEvents = results.flat();
}

async function loadAvailabilityData() {
    cachedOpeningHours = await api.get(`/api/worker/periods/${currentPeriod.id}/opening-hours`);

    // Fetch events from selected calendars
    await fetchAndCacheEvents();

    // Check for existing submission
    const existing = await api.get(`/api/worker/periods/${currentPeriod.id}/availability`);

    // Build slot data
    buildSlotData(existing);

    renderCalcSettingsPanel();
    renderAvailabilityCalendar();
    updateSlotSummary();
}

function buildSlotData(existing) {
    slotData = {};
    const start = new Date(currentPeriod.start_date);
    const end = new Date(currentPeriod.end_date);

    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const dateStr = d.toISOString().split('T')[0];
        const hours = cachedOpeningHours[dateStr];

        if (!hours) {
            slotData[dateStr] = { is_available: false, closed: true };
            continue;
        }

        // Get events for this day
        const dayEvents = getEventsForDate(dateStr);
        const mappedEvents = dayEvents.filter(e => !isAllDayEvent(e)).map(e => ({
            start: (e.start || '').substring(11, 16) || '00:00',
            end: (e.end || '').substring(11, 16) || '23:59',
        }));

        const calcSettings = getCalcSettings();
        const availableSlots = calculateAvailableSlots(
            hours.start_time, hours.end_time, mappedEvents,
            calcSettings
        );
        const detailed = calculateDetailedSlots(
            hours.start_time, hours.end_time, mappedEvents,
            calcSettings
        );

        if (availableSlots.length > 0) {
            const totalSlot = {
                start_time: availableSlots[0].start,
                end_time: availableSlots[availableSlots.length - 1].end,
            };
            slotData[dateStr] = {
                is_available: true,
                start_time: totalSlot.start_time,
                end_time: totalSlot.end_time,
                auto_calculated_start: totalSlot.start_time,
                auto_calculated_end: totalSlot.end_time,
                opening_start: hours.start_time,
                opening_end: hours.end_time,
                slots: availableSlots,
                event_count: dayEvents.length,
                detailed,
            };
        } else {
            slotData[dateStr] = {
                is_available: false,
                opening_start: hours.start_time,
                opening_end: hours.end_time,
                event_count: dayEvents.length,
                detailed,
            };
        }
    }

    // Overlay existing submission data
    if (existing && existing.slots) {
        for (const slot of existing.slots) {
            if (slotData[slot.slot_date]) {
                slotData[slot.slot_date].is_available = slot.is_available;
                if (slot.start_time) slotData[slot.slot_date].start_time = slot.start_time;
                if (slot.end_time) slotData[slot.slot_date].end_time = slot.end_time;
                slotData[slot.slot_date].is_custom_time = slot.is_custom_time;
            }
        }
        if (existing.notes) {
            document.getElementById('submission-notes').value = existing.notes;
        }
    }
}

function recalculateSlots() {
    buildSlotData(null);
}

// --- Event cache helpers ---

function getEventsForDate(dateStr) {
    return cachedCalendarEvents.filter(e => {
        const eventStart = (e.start || '').substring(0, 10);
        const eventEnd = (e.end || '').substring(0, 10);
        return eventStart === dateStr || (eventStart < dateStr && eventEnd > dateStr);
    });
}

function isAllDayEvent(event) {
    return event.start && event.start.length === 10;
}

function getCalendarColor(calendarId) {
    const cal = calendarList.find(c => c.id === calendarId);
    return cal ? cal.backgroundColor : '#3b82f6';
}

function getCalendarName(calendarId) {
    const cal = calendarList.find(c => c.id === calendarId);
    return cal ? (cal.summary || calendarId) : '';
}

function hexToTint(hex, alpha) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}

// --- Calendar rendering ---

function renderAvailabilityCalendar() {
    const container = document.getElementById('calendar-container');
    renderCalendar(container, currentPeriod.start_date, currentPeriod.end_date, slotData, {
        onDayClick: (dateStr, data, cellElement) => {
            if (data.closed) return;
            showDayPopup(dateStr, data, cellElement);
        },
        renderDayContent: (cell, dateStr, data) => {
            if (data.closed) {
                cell.classList.add('excluded');
                return;
            }
            if (data.is_available) {
                cell.classList.add('available');
                const timeEl = document.createElement('div');
                timeEl.className = 'time-slot';
                if (data.is_custom_time) {
                    timeEl.classList.add('custom-time');
                }
                timeEl.textContent = `${data.start_time}-${data.end_time}`;
                cell.appendChild(timeEl);
            } else {
                cell.classList.add('unavailable');
            }
            if (data.event_count && data.event_count > 0) {
                const dot = document.createElement('div');
                dot.className = 'event-dot';
                dot.title = `${data.event_count}件の予定`;
                cell.appendChild(dot);
            }
        },
    });
}

// --- Timeline Bar ---

function generateTimeLabels(startTime, endTime) {
    const startMin = timeToMinutes(startTime);
    const endMin = timeToMinutes(endTime);
    const totalMin = endMin - startMin;
    const labels = [];
    // Round up start to next full hour
    let hour = Math.ceil(startMin / 60) * 60;
    while (hour < endMin) {
        const pct = ((hour - startMin) / totalMin) * 100;
        labels.push({ time: minutesToTime(hour), pct });
        hour += 60;
    }
    return labels;
}

function renderTimelineBar(data, dateStr) {
    const detailed = data.detailed;
    if (!detailed) return '';

    const startMin = timeToMinutes(detailed.workStart);
    const endMin = timeToMinutes(detailed.workEnd);
    const totalMin = endMin - startMin;
    if (totalMin <= 0) return '';

    const pct = (sMin, eMin) => {
        const left = ((Math.max(sMin, startMin) - startMin) / totalMin) * 100;
        const width = ((Math.min(eMin, endMin) - Math.max(sMin, startMin)) / totalMin) * 100;
        return { left: Math.max(0, left), width: Math.max(0, width) };
    };

    let blocksHtml = '';

    // Available slots (green)
    for (const s of detailed.availableSlots) {
        const { left, width } = pct(s.startMin, s.endMin);
        blocksHtml += `<div class="tl-block tl-available" style="left:${left}%;width:${width}%" title="勤務可能: ${s.start}〜${s.end}"></div>`;
    }

    // Excluded slots (orange semi-transparent)
    for (const s of detailed.excludedSlots) {
        const { left, width } = pct(s.startMin, s.endMin);
        blocksHtml += `<div class="tl-block tl-excluded" style="left:${left}%;width:${width}%" title="時間不足: ${s.start}〜${s.end}（${Math.round(s.duration * 60)}分）"></div>`;
    }

    // Event blocks (red)
    for (const s of detailed.eventBlocks) {
        const { left, width } = pct(s.startMin, s.endMin);
        blocksHtml += `<div class="tl-block tl-event" style="left:${left}%;width:${width}%" title="予定: ${s.start}〜${s.end}"></div>`;
    }

    // Buffer zones (orange hatched)
    for (const s of detailed.bufferZones) {
        const { left, width } = pct(s.startMin, s.endMin);
        blocksHtml += `<div class="tl-block tl-buffer" style="left:${left}%;width:${width}%" title="バッファ: ${s.start}〜${s.end}"></div>`;
    }

    // Time labels
    const labels = generateTimeLabels(detailed.workStart, detailed.workEnd);
    let labelsHtml = labels.map(l => `<span class="tl-label" style="left:${l.pct}%">${l.time.substring(0,2)}</span>`).join('');

    const settings = getCalcSettings();

    return `
        <div class="day-popup-section">
            <div class="day-popup-label">自動計算の内訳</div>
            <div class="timeline-bar">${blocksHtml}</div>
            <div class="timeline-labels">${labelsHtml}</div>
            <div class="timeline-legend">
                <span class="tl-legend-item"><span class="tl-legend-dot tl-legend-event"></span>予定</span>
                <span class="tl-legend-item"><span class="tl-legend-dot tl-legend-buffer"></span>バッファ(${settings.bufferTime}分)</span>
                <span class="tl-legend-item"><span class="tl-legend-dot tl-legend-available"></span>勤務可能</span>
                <span class="tl-legend-item"><span class="tl-legend-dot tl-legend-excluded"></span>時間不足(&lt;${settings.minGapTime}分)</span>
            </div>
        </div>
    `;
}

// --- Day Popup ---

function showDayPopup(dateStr, data, cellElement) {
    closeDayPopup();

    const d = new Date(dateStr);
    const weekday = WEEKDAY_NAMES_FULL[d.getDay()];
    const displayDate = `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 (${weekday.charAt(0)})`;

    const dayEvents = getEventsForDate(dateStr);
    const allDayEvents = dayEvents.filter(isAllDayEvent);
    const timedEvents = dayEvents.filter(e => !isAllDayEvent(e));

    const isAvailable = data.is_available;
    const startTime = data.start_time || data.auto_calculated_start || data.opening_start || '09:00';
    const endTime = data.end_time || data.auto_calculated_end || data.opening_end || '21:00';

    const overlay = document.createElement('div');
    overlay.className = 'day-popup-overlay';
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeDayPopup();
    });

    const popup = document.createElement('div');
    popup.className = 'day-popup';
    popup.innerHTML = `
        <div class="day-popup-header">
            <div class="day-popup-date">${displayDate}</div>
            <button class="day-popup-close" onclick="window.closeDayPopup()">&times;</button>
        </div>

        <div class="day-popup-section">
            <div class="day-popup-label">開校時間</div>
            <div class="day-popup-opening-hours">
                ${data.opening_start && data.opening_end
                    ? `${data.opening_start} 〜 ${data.opening_end}`
                    : '情報なし'}
            </div>
        </div>

        <div class="day-popup-section">
            <div class="day-popup-label">勤務可能</div>
            <div class="day-popup-toggle-row">
                <button class="day-popup-toggle ${isAvailable ? 'active' : ''}"
                        id="popup-toggle-btn"
                        onclick="window.toggleDayFromPopup('${dateStr}')">
                    <span class="toggle-track">
                        <span class="toggle-thumb"></span>
                    </span>
                    <span class="toggle-label">${isAvailable ? 'ON' : 'OFF'}</span>
                </button>
            </div>
        </div>

        <div class="day-popup-section" id="popup-time-section" style="${isAvailable ? '' : 'display:none;'}">
            <div class="day-popup-label">勤務時間</div>
            <div class="day-popup-time-edit">
                <input type="time" id="popup-start-time" class="form-control popup-time-input" value="${startTime}">
                <span class="time-separator">〜</span>
                <input type="time" id="popup-end-time" class="form-control popup-time-input" value="${endTime}">
            </div>
            <div class="day-popup-time-actions">
                <button class="btn btn-primary btn-sm" onclick="window.applyCustomTime('${dateStr}')">適用</button>
                <button class="btn btn-outline btn-sm" onclick="window.resetCustomTime('${dateStr}')">リセット</button>
            </div>
            ${data.is_custom_time ? '<div class="day-popup-custom-badge">カスタム時間設定中</div>' : ''}
            ${data.auto_calculated_start
                ? `<div class="day-popup-auto-time">自動計算: ${data.auto_calculated_start} 〜 ${data.auto_calculated_end}</div>`
                : ''}
        </div>

        ${renderTimelineBar(data, dateStr)}

        <div class="day-popup-section">
            <div class="day-popup-label">Google カレンダーの予定</div>
            <div class="day-popup-events" id="popup-events">
                ${dayEvents.length === 0
                    ? '<div class="day-popup-no-events">予定なし</div>'
                    : renderEventChips(allDayEvents, timedEvents)}
            </div>
        </div>
    `;

    overlay.appendChild(popup);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
        overlay.classList.add('visible');
        popup.classList.add('visible');
    });
}

function renderEventChips(allDayEvents, timedEvents) {
    const allEvents = [...allDayEvents, ...timedEvents];

    // Group events by calendarId
    const groups = {};
    for (const event of allEvents) {
        const calId = event.calendarId || '_unknown';
        if (!groups[calId]) groups[calId] = [];
        groups[calId].push(event);
    }

    const calIds = Object.keys(groups);

    // Legend (only if multiple calendars)
    let html = '';
    if (calIds.length > 1) {
        html += '<div class="event-legend">';
        for (const calId of calIds) {
            const color = getCalendarColor(calId);
            const name = getCalendarName(calId) || calId;
            html += `<span class="event-legend-item"><span class="event-legend-dot" style="background:${color}"></span><span class="event-legend-name">${name}</span></span>`;
        }
        html += '</div>';
    }

    // Render each calendar group
    for (const calId of calIds) {
        const color = getCalendarColor(calId);
        const name = getCalendarName(calId) || calId;
        const events = groups[calId];
        const tint = hexToTint(color, 0.15);

        html += '<div class="event-calendar-group">';
        if (calIds.length > 1) {
            html += `<div class="event-group-header" style="background:${color}"><span>${name}</span><span class="event-group-count">${events.length}件</span></div>`;
        }
        html += `<div class="event-group-items" style="${calIds.length > 1 ? `background:${tint}` : ''}">`;

        for (const event of events) {
            const isAllDay = isAllDayEvent(event);
            if (isAllDay) {
                html += `
                    <div class="event-chip event-chip-allday" style="border-left-color:${color}">
                        <span class="event-chip-title">${escapeHtml(event.summary || 'No Title')}</span>
                        <span class="event-chip-time">終日</span>
                    </div>
                `;
            } else {
                const startTime = (event.start || '').substring(11, 16) || '';
                const endTime = (event.end || '').substring(11, 16) || '';
                html += `
                    <div class="event-chip event-chip-timed" style="border-left-color:${color}">
                        <span class="event-chip-time">${startTime} - ${endTime}</span>
                        <span class="event-chip-title">${escapeHtml(event.summary || 'No Title')}</span>
                    </div>
                `;
            }
        }

        html += '</div></div>';
    }

    return html;
}

window.closeDayPopup = function() {
    const overlay = document.querySelector('.day-popup-overlay');
    if (overlay) {
        overlay.classList.remove('visible');
        const popup = overlay.querySelector('.day-popup');
        if (popup) popup.classList.remove('visible');
        setTimeout(() => overlay.remove(), 200);
    }
};

function closeDayPopup() {
    window.closeDayPopup();
}

window.toggleDayFromPopup = function(dateStr) {
    const data = slotData[dateStr];
    if (!data || data.closed) return;

    data.is_available = !data.is_available;

    const toggleBtn = document.getElementById('popup-toggle-btn');
    if (toggleBtn) {
        toggleBtn.classList.toggle('active', data.is_available);
        const label = toggleBtn.querySelector('.toggle-label');
        if (label) label.textContent = data.is_available ? 'ON' : 'OFF';
    }

    const timeSection = document.getElementById('popup-time-section');
    if (timeSection) {
        timeSection.style.display = data.is_available ? '' : 'none';
    }

    renderAvailabilityCalendar();
    updateSlotSummary();
};

window.applyCustomTime = function(dateStr) {
    const data = slotData[dateStr];
    if (!data) return;

    const startInput = document.getElementById('popup-start-time');
    const endInput = document.getElementById('popup-end-time');
    if (!startInput || !endInput) return;

    const newStart = startInput.value;
    const newEnd = endInput.value;

    if (!newStart || !newEnd) {
        showToast('時間を入力してください', 'warning');
        return;
    }
    if (timeToMinutes(newStart) >= timeToMinutes(newEnd)) {
        showToast('開始時間は終了時間より前にしてください', 'warning');
        return;
    }

    if (data.opening_start && data.opening_end) {
        if (timeToMinutes(newStart) < timeToMinutes(data.opening_start) ||
            timeToMinutes(newEnd) > timeToMinutes(data.opening_end)) {
            showToast('開校時間の範囲内で設定してください', 'warning');
            return;
        }
    }

    data.start_time = newStart;
    data.end_time = newEnd;
    data.is_custom_time = true;

    renderAvailabilityCalendar();
    updateSlotSummary();
    showToast('勤務時間を更新しました', 'success');

    closeDayPopup();
    const cell = document.querySelector(`[data-date="${dateStr}"]`);
    if (cell) showDayPopup(dateStr, data, cell);
};

window.resetCustomTime = function(dateStr) {
    const data = slotData[dateStr];
    if (!data) return;

    if (data.auto_calculated_start && data.auto_calculated_end) {
        data.start_time = data.auto_calculated_start;
        data.end_time = data.auto_calculated_end;
    }
    data.is_custom_time = false;

    renderAvailabilityCalendar();
    updateSlotSummary();
    showToast('自動計算値にリセットしました', 'info');

    closeDayPopup();
    const cell = document.querySelector(`[data-date="${dateStr}"]`);
    if (cell) showDayPopup(dateStr, data, cell);
};

// --- Summary ---

function updateSlotSummary() {
    const available = Object.values(slotData).filter(d => d.is_available).length;
    const total = Object.values(slotData).filter(d => !d.closed).length;
    document.getElementById('slot-summary').textContent = `${available}/${total} 日勤務可能`;
}

window.showPeriodList = function() {
    document.getElementById('period-select-section').style.display = 'block';
    document.getElementById('availability-section').style.display = 'none';
    currentPeriod = null;
    cachedCalendarEvents = [];
    calendarList = [];
    selectedCalendarIds = [];
    cachedOpeningHours = null;
};

window.submitAvailability = async function() {
    if (!currentPeriod) return;

    const available = Object.values(slotData).filter(d => d.is_available).length;
    const total = Object.values(slotData).filter(d => !d.closed).length;
    const isResubmit = !!currentPeriod.submission_status;

    const title = isResubmit ? 'シフト希望を再提出しますか？' : 'シフト希望を提出しますか？';
    const message = isResubmit
        ? `${total}日中 ${available}日を勤務可能として再提出します。前回の提出内容は上書きされます。`
        : `${total}日中 ${available}日を勤務可能として提出します。提出後も期間内であれば再提出できます。`;
    const btnLabel = isResubmit ? '再提出する' : '提出する';

    showConfirmDialog(
        title,
        message,
        'btn-success',
        btnLabel,
        async () => {
            const slots = Object.entries(slotData)
                .filter(([_, d]) => !d.closed)
                .map(([dateStr, d]) => ({
                    slot_date: dateStr,
                    is_available: d.is_available,
                    start_time: d.start_time || null,
                    end_time: d.end_time || null,
                    is_custom_time: d.is_custom_time || false,
                    auto_calculated_start: d.auto_calculated_start || null,
                    auto_calculated_end: d.auto_calculated_end || null,
                }));

            const notes = document.getElementById('submission-notes').value;

            try {
                await api.post(`/api/worker/periods/${currentPeriod.id}/availability`, { slots, notes });
                showToast(isResubmit ? 'シフト希望を再提出しました' : 'シフト希望を提出しました', 'success');
                showPeriodList();
                await loadPeriods();
            } catch (e) {
                showToast(`提出に失敗しました: ${e.message}`, 'error');
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
