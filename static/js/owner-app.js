import { api, getCurrentUser } from './modules/api-client.js';
import { showToast } from './modules/notification.js';

let currentUser = null;
let currentScheduleId = null;

async function init() {
    try {
        currentUser = await getCurrentUser();
        document.getElementById('user-name').textContent = currentUser.display_name || currentUser.email;
        await loadPendingApprovals();
    } catch (e) {
        console.error('Init error:', e);
    }
}

async function loadPendingApprovals() {
    const container = document.getElementById('pending-list');
    try {
        const approvals = await api.get('/api/owner/pending-approvals');

        if (!approvals || approvals.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>承認待ちのスケジュールはありません</p></div>';
            container.classList.remove('loading');
            return;
        }

        container.classList.remove('loading');
        container.innerHTML = approvals.map(a => `
            <div class="card" style="cursor:pointer;" onclick="window.viewSchedule(${a.id})">
                <div class="flex-between">
                    <div>
                        <strong>${a.period ? a.period.name : 'スケジュール #' + a.id}</strong>
                        <div style="color:#666;font-size:0.9em;">
                            ${a.period ? `${a.period.start_date} 〜 ${a.period.end_date}` : ''}
                        </div>
                        <div style="color:#666;font-size:0.85em;">作成: ${a.creator_name || '不明'}</div>
                    </div>
                    <span class="badge badge-pending">承認待ち</span>
                </div>
            </div>
        `).join('');
    } catch (e) {
        container.classList.remove('loading');
        container.innerHTML = '<div class="empty-state"><p>読み込みに失敗しました</p></div>';
    }
}

window.viewSchedule = async function(scheduleId) {
    currentScheduleId = scheduleId;

    try {
        const data = await api.get(`/api/owner/schedules/${scheduleId}`);

        document.getElementById('pending-list').style.display = 'none';
        document.getElementById('schedule-detail').style.display = 'block';
        document.getElementById('detail-title').textContent = data.period ? data.period.name : `スケジュール #${scheduleId}`;

        // Summary
        document.getElementById('detail-summary').innerHTML = `
            <div class="grid-2">
                <div><strong>期間:</strong> ${data.period ? `${data.period.start_date} 〜 ${data.period.end_date}` : '-'}</div>
                <div><strong>ステータス:</strong> <span class="badge badge-${data.status}">${data.status}</span></div>
                <div><strong>作成日:</strong> ${data.created_at ? data.created_at.substring(0, 10) : '-'}</div>
            </div>
        `;

        // Entries
        const WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'];
        if (data.entries && data.entries.length > 0) {
            const sorted = data.entries.sort((a, b) => a.shift_date.localeCompare(b.shift_date) || a.start_time.localeCompare(b.start_time));
            document.getElementById('detail-entries').innerHTML = `
                <table class="data-table">
                    <thead><tr><th>日付</th><th>曜日</th><th>スタッフ</th><th>時間</th></tr></thead>
                    <tbody>
                        ${sorted.map(e => {
                            const dt = new Date(e.shift_date);
                            return `<tr>
                                <td>${e.shift_date}</td>
                                <td>${WEEKDAYS[dt.getDay()]}</td>
                                <td>${e.user_name || `User ${e.user_id}`}</td>
                                <td>${e.start_time} - ${e.end_time}</td>
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            `;
        } else {
            document.getElementById('detail-entries').innerHTML = '<p style="color:#999;">エントリなし</p>';
        }

        // Hours summary
        if (data.hours_summary && data.hours_summary.length > 0) {
            document.getElementById('detail-hours').innerHTML = `
                <table class="data-table">
                    <thead><tr><th>スタッフ</th><th>合計時間</th><th>シフト数</th></tr></thead>
                    <tbody>
                        ${data.hours_summary.map(h => `
                            <tr>
                                <td>${h.user_name || `User ${h.user_id}`}</td>
                                <td>${h.total_hours.toFixed(1)} 時間</td>
                                <td>${h.shift_count} 日</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } else {
            document.getElementById('detail-hours').innerHTML = '<p style="color:#999;">データなし</p>';
        }

        // History
        if (data.history && data.history.length > 0) {
            const actionLabels = {
                submitted: '承認申請',
                approved: '承認',
                rejected: '差戻し',
                confirmed: '確定',
            };
            document.getElementById('detail-history').innerHTML = data.history.map(h => `
                <div class="flex-between mb-8" style="padding:8px;background:#f8f9fa;border-radius:8px;">
                    <div>
                        <span class="badge badge-${h.action}">${actionLabels[h.action] || h.action}</span>
                        <span style="color:#666;margin-left:8px;">${h.performer_name || ''}</span>
                    </div>
                    <span style="color:#999;font-size:0.85em;">${h.performed_at ? h.performed_at.substring(0, 16).replace('T', ' ') : ''}</span>
                </div>
                ${h.comment ? `<p style="color:#666;font-size:0.9em;margin:4px 0 8px 8px;">${h.comment}</p>` : ''}
            `).join('');
        } else {
            document.getElementById('detail-history').innerHTML = '<p style="color:#999;">履歴なし</p>';
        }

    } catch (e) {
        showToast('スケジュールの読み込みに失敗しました', 'error');
    }
};

window.showPendingList = function() {
    document.getElementById('pending-list').style.display = 'block';
    document.getElementById('schedule-detail').style.display = 'none';
    currentScheduleId = null;
};

window.approveSchedule = async function() {
    if (!currentScheduleId) return;
    const comment = document.getElementById('approval-comment').value;
    try {
        await api.post(`/api/owner/schedules/${currentScheduleId}/approve`, { comment });
        showToast('スケジュールを承認しました', 'success');
        showPendingList();
        await loadPendingApprovals();
    } catch (e) {
        showToast(`承認に失敗しました: ${e.message}`, 'error');
    }
};

window.rejectSchedule = async function() {
    if (!currentScheduleId) return;
    const comment = document.getElementById('approval-comment').value;
    if (!comment) {
        showToast('差戻しの理由を入力してください', 'warning');
        return;
    }
    try {
        await api.post(`/api/owner/schedules/${currentScheduleId}/reject`, { comment });
        showToast('スケジュールを差戻しました', 'success');
        showPendingList();
        await loadPendingApprovals();
    } catch (e) {
        showToast(`差戻しに失敗しました: ${e.message}`, 'error');
    }
};

init();
