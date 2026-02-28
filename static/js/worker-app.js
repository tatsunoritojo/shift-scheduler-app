import { api, getCurrentUser, getCalendarEvents } from './modules/api-client.js';
import { renderCalendar } from './modules/calendar-grid.js';
import { calculateAvailableSlots } from './modules/shift-calculator.js';
import { timeToMinutes, minutesToTime, formatDateJP } from './modules/time-utils.js';
import { showToast } from './modules/notification.js';

let currentUser = null;
let currentPeriod = null;
let slotData = {};  // dateStr -> { is_available, start_time, end_time, ... }

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
            container.innerHTML = '<div class="empty-state"><p>現在提出可能なシフト期間はありません</p></div>';
            return;
        }

        container.innerHTML = periods.map(p => `
            <div class="card" style="cursor:pointer;" onclick="window.selectPeriod(${p.id})">
                <div class="flex-between">
                    <div>
                        <strong>${p.name}</strong>
                        <div style="color:#666;font-size:0.9em;">${p.start_date} 〜 ${p.end_date}</div>
                    </div>
                    <div>
                        ${p.submission_status
                            ? `<span class="badge badge-submitted">提出済</span>`
                            : `<span class="badge badge-open">未提出</span>`
                        }
                    </div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><p>読み込みに失敗しました</p></div>`;
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

        await loadAvailabilityData();
    } catch (e) {
        showToast('データの読み込みに失敗しました', 'error');
    }
};

async function loadAvailabilityData() {
    const openingHours = await api.get(`/api/worker/periods/${currentPeriod.id}/opening-hours`);

    let calendarEvents = [];
    try {
        calendarEvents = await getCalendarEvents(currentPeriod.start_date, currentPeriod.end_date);
    } catch (e) {
        console.warn('Could not fetch calendar events:', e);
    }

    // Check for existing submission
    const existing = await api.get(`/api/worker/periods/${currentPeriod.id}/availability`);

    // Build slot data for each date
    slotData = {};
    const start = new Date(currentPeriod.start_date);
    const end = new Date(currentPeriod.end_date);

    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const dateStr = d.toISOString().split('T')[0];
        const hours = openingHours[dateStr];

        if (!hours) {
            slotData[dateStr] = { is_available: false, closed: true };
            continue;
        }

        // Get events for this day
        const dayEvents = calendarEvents.filter(e => {
            const eventDate = (e.start || '').substring(0, 10);
            return eventDate === dateStr;
        }).map(e => ({
            start: (e.start || '').substring(11, 16) || '00:00',
            end: (e.end || '').substring(11, 16) || '23:59',
        }));

        const availableSlots = calculateAvailableSlots(
            hours.start_time, hours.end_time, dayEvents,
            { bufferTime: 30, minGapTime: 60 }
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
            };
        } else {
            slotData[dateStr] = {
                is_available: false,
                opening_start: hours.start_time,
                opening_end: hours.end_time,
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

    renderAvailabilityCalendar();
    updateSlotSummary();
}

function renderAvailabilityCalendar() {
    const container = document.getElementById('calendar-container');
    renderCalendar(container, currentPeriod.start_date, currentPeriod.end_date, slotData, {
        onDayClick: (dateStr, data) => {
            if (data.closed) return;
            toggleDay(dateStr);
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
                timeEl.textContent = `${data.start_time}-${data.end_time}`;
                cell.appendChild(timeEl);
            } else {
                cell.classList.add('unavailable');
            }
        },
    });
}

function toggleDay(dateStr) {
    const data = slotData[dateStr];
    if (!data || data.closed) return;

    data.is_available = !data.is_available;
    renderAvailabilityCalendar();
    updateSlotSummary();
}

function updateSlotSummary() {
    const available = Object.values(slotData).filter(d => d.is_available).length;
    const total = Object.values(slotData).filter(d => !d.closed).length;
    document.getElementById('slot-summary').textContent = `${available}/${total} 日勤務可能`;
}

window.showPeriodList = function() {
    document.getElementById('period-select-section').style.display = 'block';
    document.getElementById('availability-section').style.display = 'none';
    currentPeriod = null;
};

window.submitAvailability = async function() {
    if (!currentPeriod) return;

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
        showToast('シフト希望を提出しました', 'success');
        showPeriodList();
        await loadPeriods();
    } catch (e) {
        showToast(`提出に失敗しました: ${e.message}`, 'error');
    }
};

init();
