import { api, getCurrentUser } from './modules/api-client.js';
import { showToast } from './modules/notification.js';

let currentUser = null;
let scheduleEntries = [];  // Current schedule being built
let submissionsData = {};  // period submissions

const WEEKDAY_NAMES = ['日', '月', '火', '水', '木', '金', '土'];

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
        container.innerHTML = '<p style="color:#999;">例外日はありません</p>';
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
        container.innerHTML = '<p style="color:#999;">シフト期間はありません</p>';
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
        return;
    }

    document.getElementById('builder-content').style.display = 'block';

    const [submissions, schedule, workers] = await Promise.all([
        api.get(`/api/admin/periods/${periodId}/submissions`),
        api.get(`/api/admin/periods/${periodId}/schedule`),
        api.get('/api/admin/workers'),
    ]);

    submissionsData = submissions;
    scheduleEntries = schedule && schedule.entries ? schedule.entries : [];

    // Show confirm button if schedule is approved
    if (schedule && schedule.status === 'approved') {
        document.getElementById('confirm-btn').style.display = 'inline-block';
    } else {
        document.getElementById('confirm-btn').style.display = 'none';
    }

    renderSubmissionsSummary(submissions);
    renderScheduleGrid(periodId, submissions, workers);
    renderHoursSummary();
};

function renderSubmissionsSummary(submissions) {
    const container = document.getElementById('submissions-summary');
    if (!submissions || submissions.length === 0) {
        container.innerHTML = '<p style="color:#999;">提出なし</p>';
        return;
    }
    container.innerHTML = submissions.map(s => `
        <div class="flex-between mb-8">
            <span>${s.user_name || s.user_email}</span>
            <span class="badge badge-${s.status}">${s.status === 'submitted' ? '提出済' : s.status}</span>
        </div>
    `).join('');
}

function renderScheduleGrid(periodId, submissions, workers) {
    const container = document.getElementById('schedule-grid');

    if (!submissions || submissions.length === 0) {
        container.innerHTML = '<p style="color:#999;">提出データがありません。アルバイトにシフト希望を提出してもらってください。</p>';
        return;
    }

    // Collect all dates from submissions
    const allDates = new Set();
    submissions.forEach(sub => {
        (sub.slots || []).forEach(slot => allDates.add(slot.slot_date));
    });
    const sortedDates = [...allDates].sort();

    // Build grid: rows = workers, columns = dates
    let html = '<div style="overflow-x:auto;"><table class="data-table" style="font-size:0.85em;">';
    html += '<thead><tr><th>名前</th>';
    sortedDates.forEach(d => {
        const dt = new Date(d);
        html += `<th style="text-align:center;min-width:60px;">${dt.getMonth()+1}/${dt.getDate()}<br>${WEEKDAY_NAMES[dt.getDay()]}</th>`;
    });
    html += '</tr></thead><tbody>';

    submissions.forEach(sub => {
        html += `<tr><td style="white-space:nowrap;">${sub.user_name || sub.user_email || 'User'}</td>`;
        const slotMap = {};
        (sub.slots || []).forEach(s => slotMap[s.slot_date] = s);

        sortedDates.forEach(d => {
            const slot = slotMap[d];
            const isAssigned = scheduleEntries.some(e => e.user_id === sub.user_id && e.shift_date === d);

            if (!slot || !slot.is_available) {
                html += '<td style="text-align:center;background:#ffebee;">-</td>';
            } else {
                const bg = isAssigned ? '#c8e6c9' : '#e3f2fd';
                const border = isAssigned ? '2px solid #4caf50' : 'none';
                html += `<td style="text-align:center;background:${bg};border:${border};cursor:pointer;"
                    onclick="window.toggleAssignment(${sub.user_id}, '${d}', '${slot.start_time}', '${slot.end_time}')">
                    ${slot.start_time ? `<div style="font-size:0.75em;">${slot.start_time}-${slot.end_time}</div>` : 'OK'}
                </td>`;
            }
        });
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

window.toggleAssignment = function(userId, date, startTime, endTime) {
    const idx = scheduleEntries.findIndex(e => e.user_id === userId && e.shift_date === date);
    if (idx >= 0) {
        scheduleEntries.splice(idx, 1);
    } else {
        scheduleEntries.push({
            user_id: userId,
            shift_date: date,
            start_time: startTime || '09:00',
            end_time: endTime || '17:00',
        });
    }

    // Re-render
    const periodId = document.getElementById('builder-period-select').value;
    renderScheduleGrid(periodId, submissionsData, []);
    renderHoursSummary();
};

function renderHoursSummary() {
    const container = document.getElementById('hours-summary');
    const summary = {};
    scheduleEntries.forEach(e => {
        const uid = e.user_id;
        if (!summary[uid]) {
            // Find user name from submissions
            const sub = submissionsData.find(s => s.user_id === uid);
            summary[uid] = {
                name: sub ? (sub.user_name || sub.user_email) : `User ${uid}`,
                hours: 0,
                shifts: 0,
            };
        }
        const startMins = parseInt(e.start_time.split(':')[0]) * 60 + parseInt(e.start_time.split(':')[1]);
        const endMins = parseInt(e.end_time.split(':')[0]) * 60 + parseInt(e.end_time.split(':')[1]);
        summary[uid].hours += (endMins - startMins) / 60;
        summary[uid].shifts++;
    });

    if (Object.keys(summary).length === 0) {
        container.innerHTML = '<p style="color:#999;">割当なし</p>';
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
    // Save first, then submit
    try {
        await api.post(`/api/admin/periods/${periodId}/schedule`, { entries: scheduleEntries });
        await api.post(`/api/admin/periods/${periodId}/schedule/submit`);
        showToast('承認申請を送信しました', 'success');
    } catch (e) {
        showToast(`承認申請に失敗しました: ${e.message}`, 'error');
    }
};

window.confirmSchedule = async function() {
    const periodId = document.getElementById('builder-period-select').value;
    if (!periodId) return;
    try {
        const result = await api.post(`/api/admin/periods/${periodId}/schedule/confirm`);
        const syncResults = result.sync_results || [];
        const success = syncResults.filter(r => r.success).length;
        const failed = syncResults.filter(r => r.error).length;
        showToast(`確定完了: ${success}件同期成功, ${failed}件失敗`, success > 0 ? 'success' : 'warning');
    } catch (e) {
        showToast(`確定に失敗しました: ${e.message}`, 'error');
    }
};

init();
