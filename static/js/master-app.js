import { api, getCurrentUser } from './modules/api-client.js';
import { showToast } from './modules/notification.js';
import { escapeHtml } from './modules/escape-html.js';
import { showConfirmDialog } from './modules/ui-dialogs.js';

// ============================================================
// State
// ============================================================
let currentUser = null;
let usersData = [];
let membersData = [];

// ============================================================
// Init
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
    try {
        currentUser = await getCurrentUser();
        if (!currentUser) { window.location.href = '/login'; return; }
        document.getElementById('user-name').textContent = currentUser.display_name || currentUser.email;
    } catch {
        window.location.href = '/login';
        return;
    }

    setupTabs();
    setupLogout();
    setupSearch();
    setupFilters();
    setupQuery();
    setupTaskActions();
    setupHealthCheck();

    await Promise.all([loadStats(), loadUsers(), runHealthBanner()]);
});

// ============================================================
// Tabs
// ============================================================
function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const tab = btn.dataset.tab;
            document.getElementById(`tab-${tab}`).classList.add('active');
            onTabActivated(tab);
        });
    });
}

const loadedTabs = new Set(['users']);
function onTabActivated(tab) {
    if (loadedTabs.has(tab)) return;
    loadedTabs.add(tab);
    const loaders = {
        organizations: loadOrganizations,
        members: loadMembers,
        periods: loadPeriods,
        schedules: loadSchedules,
        tasks: loadTasks,
        health: () => {},
        audit: loadAuditLogs,
    };
    if (loaders[tab]) loaders[tab]();
}

function activateTab(tab) {
    document.querySelector(`.tab-btn[data-tab="${tab}"]`).click();
}

// ============================================================
// Logout
// ============================================================
function setupLogout() {
    document.getElementById('btn-logout').addEventListener('click', async () => {
        await api.post('/auth/logout');
        window.location.href = '/login';
    });
}

// ============================================================
// Stats
// ============================================================
async function loadStats() {
    try {
        const s = await api.get('/api/master/stats');
        document.getElementById('stat-users').textContent = `${s.users.active}/${s.users.total}`;
        document.getElementById('stat-orgs').textContent = `${s.organizations.active}/${s.organizations.total}`;
        document.getElementById('stat-members').textContent = `${s.members.active}/${s.members.total}`;
        document.getElementById('stat-periods').textContent = s.periods;
        document.getElementById('stat-tasks-pending').textContent = s.tasks.pending;
        document.getElementById('stat-tasks-failed').textContent = s.tasks.failed;
    } catch (e) {
        showToast('統計の読み込みに失敗: ' + e.message, 'error');
    }
}

// ============================================================
// Health Banner (Scenario 6 — always-visible alert)
// ============================================================
async function runHealthBanner() {
    try {
        const h = await api.get('/api/master/health-check');
        if (h.total_issues > 0) {
            const banner = document.getElementById('health-banner');
            document.getElementById('health-banner-text').textContent = `${h.total_issues} 件のデータ整合性問題が検出されました`;
            banner.style.display = 'block';
            document.getElementById('btn-go-health').addEventListener('click', () => activateTab('health'));
        }
    } catch { /* silent */ }
}

// ============================================================
// Users (Scenario 2 — token health column)
// ============================================================
async function loadUsers() {
    try {
        usersData = await api.get('/api/master/users');
        renderUsers(usersData);
    } catch (e) {
        showToast('ユーザーの読み込みに失敗: ' + e.message, 'error');
    }
}

function renderUsers(users) {
    const tbody = document.querySelector('#table-users tbody');
    if (!users.length) { tbody.innerHTML = '<tr><td colspan="9" class="empty-state">ユーザーがいません</td></tr>'; return; }
    tbody.innerHTML = users.map(u => `
        <tr>
            <td>${u.id}</td>
            <td>${escapeHtml(u.display_name)}</td>
            <td class="cell-truncate">${escapeHtml(u.email)}</td>
            <td><span class="badge badge-${u.role || 'worker'}">${escapeHtml(u.role || '-')}</span></td>
            <td>${escapeHtml(u.organization_name || '-')}</td>
            <td><span class="token-dot ${u.has_token ? 'token-dot-ok' : 'token-dot-ng'}" title="${u.has_token ? 'トークンあり' : 'トークンなし'}"></span></td>
            <td><span class="status-dot ${u.is_active ? 'status-dot-active' : 'status-dot-inactive'}"></span>${u.is_active ? '有効' : '無効'}</td>
            <td>${formatDate(u.created_at)}</td>
            <td class="table-actions">
                <button class="btn btn-outline btn-xs" onclick="masterApp.editUser(${u.id})">編集</button>
                ${u.is_active
                    ? `<button class="btn btn-danger btn-xs" onclick="masterApp.deactivateUser(${u.id})">無効化</button>`
                    : `<button class="btn btn-success btn-xs" onclick="masterApp.activateUser(${u.id})">有効化</button>`}
            </td>
        </tr>
    `).join('');
}

// ============================================================
// Organizations
// ============================================================
async function loadOrganizations() {
    try {
        const orgs = await api.get('/api/master/organizations');
        const tbody = document.querySelector('#table-organizations tbody');
        if (!orgs.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-state">組織がありません</td></tr>'; return; }
        tbody.innerHTML = orgs.map(o => `
            <tr>
                <td>${o.id}</td>
                <td>${escapeHtml(o.name)}</td>
                <td>${o.member_count}</td>
                <td class="cell-truncate-sm">${o.invite_code_enabled ? escapeHtml(o.invite_code || '-') : '<span style="color:var(--color-neutral-400)">無効</span>'}</td>
                <td><span class="status-dot ${o.is_active ? 'status-dot-active' : 'status-dot-inactive'}"></span>${o.is_active ? '有効' : '無効'}</td>
                <td>${formatDate(o.created_at)}</td>
                <td class="table-actions">
                    <button class="btn btn-outline btn-xs" onclick="masterApp.editOrg(${o.id})">編集</button>
                </td>
            </tr>
        `).join('');
    } catch (e) { showToast('組織の読み込みに失敗: ' + e.message, 'error'); }
}

// ============================================================
// Members
// ============================================================
async function loadMembers() {
    try {
        membersData = await api.get('/api/master/members');
        renderMembers(membersData);
    } catch (e) { showToast('メンバーの読み込みに失敗: ' + e.message, 'error'); }
}

function renderMembers(members) {
    const tbody = document.querySelector('#table-members tbody');
    if (!members.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-state">メンバーがいません</td></tr>'; return; }
    tbody.innerHTML = members.map(m => `
        <tr>
            <td>${m.id}</td>
            <td>${escapeHtml(m.user_name || m.user_email)}</td>
            <td>${escapeHtml(m.organization_name || '-')}</td>
            <td><span class="badge badge-${m.role}">${escapeHtml(m.role)}</span></td>
            <td><span class="status-dot ${m.is_active ? 'status-dot-active' : 'status-dot-inactive'}"></span>${m.is_active ? '有効' : '無効'}</td>
            <td>${formatDate(m.joined_at)}</td>
            <td class="table-actions">
                <button class="btn btn-outline btn-xs" onclick="masterApp.editMember(${m.id})">編集</button>
            </td>
        </tr>
    `).join('');
}

// ============================================================
// Periods (Scenario 3 & 5)
// ============================================================
async function loadPeriods() {
    try {
        const periods = await api.get('/api/master/periods');
        const tbody = document.querySelector('#table-periods tbody');
        if (!periods.length) { tbody.innerHTML = '<tr><td colspan="9" class="empty-state">シフト期間がありません</td></tr>'; return; }
        tbody.innerHTML = periods.map(p => `
            <tr>
                <td>${p.id}</td>
                <td>${escapeHtml(p.name)}</td>
                <td>${escapeHtml(p.organization_name || '-')}</td>
                <td>${formatDate(p.start_date)} ~ ${formatDate(p.end_date)}</td>
                <td>${p.submission_deadline ? formatDateTime(p.submission_deadline) : '-'}</td>
                <td><span class="badge badge-${p.status}">${escapeHtml(p.status)}</span></td>
                <td>${p.submissions_count}</td>
                <td>${p.schedule_status ? `<span class="badge badge-${p.schedule_status}">${escapeHtml(p.schedule_status)}</span>` : '-'}</td>
                <td class="table-actions">
                    <button class="btn btn-outline btn-xs" onclick="masterApp.overridePeriodStatus(${p.id}, '${escapeHtml(p.status)}')">状態変更</button>
                    <button class="btn btn-outline btn-xs" onclick="masterApp.showCompliance(${p.id})">提出状況</button>
                </td>
            </tr>
        `).join('');
    } catch (e) { showToast('シフト期間の読み込みに失敗: ' + e.message, 'error'); }
}

// ============================================================
// Schedules (Scenario 3 & 4)
// ============================================================
async function loadSchedules() {
    try {
        const schedules = await api.get('/api/master/schedules');
        const tbody = document.querySelector('#table-schedules tbody');
        if (!schedules.length) { tbody.innerHTML = '<tr><td colspan="8" class="empty-state">スケジュールがありません</td></tr>'; return; }
        tbody.innerHTML = schedules.map(s => {
            const syncPct = s.entries_count ? Math.round(s.synced_count / s.entries_count * 100) : 0;
            const syncClass = syncPct === 100 ? 'synced' : 'unsynced';
            return `
            <tr>
                <td>${s.id}</td>
                <td>${escapeHtml(s.period_name || '-')}</td>
                <td>${escapeHtml(s.organization_name || '-')}</td>
                <td><span class="badge badge-${s.status}">${escapeHtml(s.status)}</span></td>
                <td>${s.entries_count}</td>
                <td><span class="sync-indicator"><span class="${syncClass}">${s.synced_count}/${s.entries_count}</span> (${syncPct}%)</span></td>
                <td>${formatDate(s.created_at)}</td>
                <td class="table-actions">
                    <button class="btn btn-outline btn-xs" onclick="masterApp.overrideScheduleStatus(${s.id}, '${escapeHtml(s.status)}')">状態変更</button>
                    ${s.status === 'confirmed' && s.synced_count < s.entries_count ? `<button class="btn btn-primary btn-xs" onclick="masterApp.resyncSchedule(${s.id})">再同期</button>` : ''}
                    <button class="btn btn-outline btn-xs" onclick="masterApp.showSyncStatus(${s.id})">同期詳細</button>
                </td>
            </tr>`;
        }).join('');
    } catch (e) { showToast('スケジュールの読み込みに失敗: ' + e.message, 'error'); }
}

// ============================================================
// Tasks (Scenario 1)
// ============================================================
async function loadTasks() {
    try {
        const status = document.getElementById('filter-task-status').value;
        const params = status ? `?status=${status}` : '';
        const tasks = await api.get(`/api/master/tasks${params}`);
        const tbody = document.querySelector('#table-tasks tbody');
        if (!tasks.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-state">タスクがありません</td></tr>'; return; }
        tbody.innerHTML = tasks.map(t => `
            <tr>
                <td>${t.id}</td>
                <td>${escapeHtml(t.task_type)}</td>
                <td><span class="badge badge-${t.status}">${escapeHtml(t.status)}</span></td>
                <td>${t.retry_count}/${t.max_retries}</td>
                <td class="cell-truncate" title="${escapeHtml(t.error_message || '')}">${escapeHtml(t.error_message || '-')}</td>
                <td>${formatDateTime(t.created_at)}</td>
                <td class="table-actions">
                    <button class="btn btn-outline btn-xs" onclick="masterApp.showTaskDetail(${t.id})">詳細</button>
                    ${['dead', 'failed'].includes(t.status) ? `<button class="btn btn-primary btn-xs" onclick="masterApp.retryTask(${t.id})">リトライ</button>` : ''}
                </td>
            </tr>
        `).join('');
    } catch (e) { showToast('タスクの読み込みに失敗: ' + e.message, 'error'); }
}

function setupTaskActions() {
    document.getElementById('btn-process-now').addEventListener('click', async () => {
        showConfirmDialog('タスク手動処理', '保留中のタスクを今すぐ処理しますか？（通常はCronで毎日9時に実行されます）', 'btn-primary', '実行', async () => {
            try {
                const stats = await api.post('/api/master/tasks/process-now');
                showToast(`処理完了: ${stats.succeeded}成功, ${stats.failed}失敗, ${stats.dead}デッド`, stats.failed ? 'warning' : 'success');
                loadedTabs.delete('tasks');
                loadTasks();
                loadStats();
            } catch (e) { showToast('処理失敗: ' + e.message, 'error'); }
        });
    });
}

// ============================================================
// Health Check (Scenario 6)
// ============================================================
function setupHealthCheck() {
    document.getElementById('btn-run-health').addEventListener('click', runHealthCheck);
}

async function runHealthCheck() {
    const container = document.getElementById('health-results');
    container.innerHTML = '<div class="loading"><div class="loading-spinner"></div><p>チェック中...</p></div>';
    try {
        const h = await api.get('/api/master/health-check');
        const checks = [
            { key: 'role_drift', title: 'ロール不整合', desc: 'User.roleとOrganizationMember.roleが異なるユーザー', fixable: true },
            { key: 'org_id_drift', title: '組織ID不整合', desc: 'User.organization_idとメンバーシップの組織IDが異なる', fixable: true },
            { key: 'stale_memberships', title: '無効ユーザーの有効メンバーシップ', desc: '無効化されたユーザーの有効なメンバーシップ', fixable: true },
            { key: 'orphaned_users', title: '孤立ユーザー', desc: '組織IDがあるがメンバーシップがないユーザー', fixable: true },
            { key: 'expired_invitations', title: '期限切れ招待', desc: '未使用の期限切れ招待トークン', fixable: true },
            { key: 'dead_tasks', title: 'デッドタスク', desc: '最大リトライ回数を超えたタスク', fixable: false },
            { key: 'unsynced_entries', title: '未同期エントリ', desc: '確定済みスケジュールの未同期カレンダーエントリ', fixable: false },
        ];
        container.innerHTML = checks.map(c => {
            const data = h.checks[c.key];
            const count = data.count;
            const cls = count > 0 ? (c.fixable ? 'has-issues' : 'has-warning') : '';
            return `
                <div class="health-card ${cls}">
                    <div class="health-card-info">
                        <div class="health-card-title">${c.title}</div>
                        <div class="health-card-desc">${c.desc}</div>
                    </div>
                    <div class="health-card-count ${count > 0 ? 'bad' : 'ok'}">${count}</div>
                    ${count > 0 && c.fixable ? `<button class="btn btn-danger btn-sm" onclick="masterApp.healthFix('${c.key}')">修正</button>` : ''}
                    ${count > 0 && data.items ? `<button class="btn btn-outline btn-sm" onclick='masterApp.showHealthDetail(${JSON.stringify(JSON.stringify(data.items))})'>詳細</button>` : ''}
                </div>
            `;
        }).join('');
    } catch (e) {
        container.innerHTML = `<div class="error-box"><div class="error-box-title">エラー</div><div class="error-box-message">${escapeHtml(e.message)}</div></div>`;
    }
}

// ============================================================
// Audit logs
// ============================================================
async function loadAuditLogs() {
    try {
        const action = document.getElementById('filter-audit-action').value;
        const params = action ? `?action=${action}` : '';
        const logs = await api.get(`/api/master/audit-logs${params}`);
        const tbody = document.querySelector('#table-audit tbody');
        if (!logs.length) { tbody.innerHTML = '<tr><td colspan="7" class="empty-state">ログがありません</td></tr>'; return; }
        tbody.innerHTML = logs.map(l => `
            <tr>
                <td>${l.id}</td>
                <td>${formatDateTime(l.created_at)}</td>
                <td>${escapeHtml(l.actor_email || '-')}</td>
                <td><span class="badge">${escapeHtml(l.action)}</span></td>
                <td>${escapeHtml(l.resource_type || '')} ${l.resource_id ? '#' + l.resource_id : ''}</td>
                <td><span class="badge badge-${l.status === 'SUCCESS' ? 'completed' : 'failed'}">${escapeHtml(l.status)}</span></td>
                <td>
                    ${(l.old_values || l.new_values) ? `<button class="btn btn-outline btn-xs" onclick='masterApp.showAuditDetail(${JSON.stringify(JSON.stringify({old: l.old_values, new: l.new_values}))})'>詳細</button>` : '-'}
                </td>
            </tr>
        `).join('');
    } catch (e) { showToast('監査ログの読み込みに失敗: ' + e.message, 'error'); }
}

// ============================================================
// SQL Query
// ============================================================
function setupQuery() {
    document.getElementById('btn-run-query').addEventListener('click', runQuery);
    document.getElementById('sql-input').addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runQuery();
    });
}

async function runQuery() {
    const sql = document.getElementById('sql-input').value.trim();
    if (!sql) return;
    const resultDiv = document.getElementById('query-result');
    const errorDiv = document.getElementById('query-error');
    resultDiv.style.display = 'none';
    errorDiv.style.display = 'none';
    try {
        const data = await api.post('/api/master/query', { sql });
        if (!data.columns.length) { showToast('結果なし', 'info'); return; }
        document.getElementById('query-count').textContent = `${data.count} 件`;
        document.querySelector('#table-query thead tr').innerHTML = data.columns.map(c => `<th>${escapeHtml(c)}</th>`).join('');
        document.querySelector('#table-query tbody').innerHTML = data.rows.map(row =>
            '<tr>' + data.columns.map(c => `<td class="cell-truncate">${escapeHtml(String(row[c] ?? ''))}</td>`).join('') + '</tr>'
        ).join('');
        resultDiv.style.display = 'block';
    } catch (e) {
        document.getElementById('query-error-msg').textContent = e.message;
        errorDiv.style.display = 'block';
    }
}

// ============================================================
// Search / Filter
// ============================================================
function setupSearch() {
    document.getElementById('search-users').addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase();
        renderUsers(usersData.filter(u => (u.email || '').toLowerCase().includes(q) || (u.display_name || '').toLowerCase().includes(q)));
    });
    document.getElementById('search-members').addEventListener('input', (e) => {
        const q = e.target.value.toLowerCase();
        renderMembers(membersData.filter(m => (m.user_email || '').toLowerCase().includes(q) || (m.user_name || '').toLowerCase().includes(q) || (m.organization_name || '').toLowerCase().includes(q)));
    });
}

function setupFilters() {
    document.getElementById('filter-task-status').addEventListener('change', () => { loadedTabs.delete('tasks'); loadTasks(); });
    document.getElementById('btn-refresh-tasks').addEventListener('click', () => { loadedTabs.delete('tasks'); loadTasks(); });
    document.getElementById('filter-audit-action').addEventListener('change', () => { loadedTabs.delete('audit'); loadAuditLogs(); });
    document.getElementById('btn-refresh-audit').addEventListener('click', () => { loadedTabs.delete('audit'); loadAuditLogs(); });
}

// ============================================================
// Shared: Edit modal
// ============================================================
function showEditModal(title, fields, onSave) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    let fieldsHtml = fields.map(f => {
        if (f.type === 'select') {
            const opts = f.options.map(o => `<option value="${escapeHtml(o.value)}" ${o.value === f.value ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('');
            return `<div class="edit-modal-field"><label>${escapeHtml(f.label)}</label><select class="form-control" data-field="${f.key}">${opts}</select></div>`;
        }
        if (f.type === 'checkbox') {
            return `<div class="edit-modal-field"><label><input type="checkbox" data-field="${f.key}" ${f.value ? 'checked' : ''}> ${escapeHtml(f.label)}</label></div>`;
        }
        if (f.type === 'datetime-local') {
            return `<div class="edit-modal-field"><label>${escapeHtml(f.label)}</label><input type="datetime-local" class="form-control" data-field="${f.key}" value="${f.value || ''}"></div>`;
        }
        return `<div class="edit-modal-field"><label>${escapeHtml(f.label)}</label><input type="text" class="form-control" data-field="${f.key}" value="${escapeHtml(f.value || '')}"></div>`;
    }).join('');
    overlay.innerHTML = `<div class="modal"><h3>${escapeHtml(title)}</h3>${fieldsHtml}<div class="modal-actions"><button class="btn btn-outline" id="edit-cancel">キャンセル</button><button class="btn btn-primary" id="edit-save">保存</button></div></div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#edit-cancel').onclick = () => overlay.remove();
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.querySelector('#edit-save').onclick = () => {
        const result = {};
        fields.forEach(f => {
            const el = overlay.querySelector(`[data-field="${f.key}"]`);
            result[f.key] = f.type === 'checkbox' ? el.checked : el.value;
        });
        overlay.remove();
        onSave(result);
    };
}

function showDetailModal(title, content) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `<div class="modal" style="max-width:600px;">${content}<div class="modal-actions"><button class="btn btn-outline" id="detail-close">閉じる</button></div></div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#detail-close').onclick = () => overlay.remove();
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    return overlay;
}

// ============================================================
// Global action handlers
// ============================================================
window.masterApp = {
    // --- Users ---
    async editUser(id) {
        const user = usersData.find(u => u.id === id);
        if (!user) return;
        showEditModal(`ユーザー編集: ${user.email}`, [
            { key: 'display_name', label: '表示名', type: 'text', value: user.display_name },
            { key: 'is_active', label: '有効', type: 'checkbox', value: user.is_active },
        ], async (data) => {
            try { await api.put(`/api/master/users/${id}`, data); showToast('更新しました', 'success'); await loadUsers(); loadStats(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    async deactivateUser(id) {
        const user = usersData.find(u => u.id === id);
        showConfirmDialog('ユーザー無効化', `${user?.display_name || user?.email} を無効化しますか？`, 'btn-danger', '無効化', async () => {
            try { await api.delete(`/api/master/users/${id}`); showToast('無効化しました', 'success'); await loadUsers(); loadStats(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    async activateUser(id) {
        try { await api.put(`/api/master/users/${id}`, { is_active: true }); showToast('有効化しました', 'success'); await loadUsers(); loadStats(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
    },

    // --- Organizations ---
    async editOrg(id) {
        let orgs; try { orgs = await api.get('/api/master/organizations'); } catch { return; }
        const org = orgs.find(o => o.id === id);
        if (!org) return;
        showEditModal(`組織編集: ${org.name}`, [
            { key: 'name', label: '組織名', type: 'text', value: org.name },
            { key: 'is_active', label: '有効', type: 'checkbox', value: org.is_active },
            { key: 'invite_code_enabled', label: '招待コード有効', type: 'checkbox', value: org.invite_code_enabled },
        ], async (data) => {
            try { await api.put(`/api/master/organizations/${id}`, data); showToast('更新しました', 'success'); loadedTabs.delete('organizations'); loadOrganizations(); loadStats(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    // --- Members ---
    async editMember(id) {
        const m = membersData.find(m => m.id === id);
        if (!m) return;
        showEditModal(`メンバー編集: ${m.user_name || m.user_email}`, [
            { key: 'role', label: 'ロール', type: 'select', value: m.role, options: [
                { value: 'admin', label: '管理者' }, { value: 'owner', label: 'オーナー' }, { value: 'worker', label: 'ワーカー' },
            ]},
            { key: 'is_active', label: '有効', type: 'checkbox', value: m.is_active },
        ], async (data) => {
            try { await api.put(`/api/master/members/${id}`, data); showToast('更新しました', 'success'); loadedTabs.delete('members'); loadMembers(); loadStats(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    // --- Scenario 1: Tasks ---
    async showTaskDetail(id) {
        try {
            const t = await api.get(`/api/master/tasks/${id}`);
            showDetailModal('タスク詳細', `
                <h3>タスク #${t.id}: ${escapeHtml(t.task_type)}</h3>
                <div class="edit-modal-field"><label>ステータス</label><span class="badge badge-${t.status}">${escapeHtml(t.status)}</span></div>
                <div class="edit-modal-field"><label>リトライ</label>${t.retry_count} / ${t.max_retries}</div>
                <div class="edit-modal-field"><label>エラー</label><div class="json-detail">${escapeHtml(t.error_message || 'なし')}</div></div>
                <div class="edit-modal-field"><label>ペイロード</label><div class="json-detail">${escapeHtml(JSON.stringify(t.payload, null, 2))}</div></div>
                <div class="edit-modal-field"><label>作成日</label>${formatDateTime(t.created_at)}</div>
                <div class="edit-modal-field"><label>開始日</label>${formatDateTime(t.started_at)}</div>
                <div class="edit-modal-field"><label>完了日</label>${formatDateTime(t.completed_at)}</div>
                <div class="edit-modal-field"><label>次回実行</label>${formatDateTime(t.next_run_at)}</div>
            `);
        } catch (e) { showToast('読み込み失敗: ' + e.message, 'error'); }
    },

    async retryTask(id) {
        showConfirmDialog('タスクリトライ', `タスク #${id} をリトライキューに戻しますか？`, 'btn-primary', 'リトライ', async () => {
            try { await api.post(`/api/master/tasks/${id}/retry`); showToast('リトライキューに追加しました', 'success'); loadedTabs.delete('tasks'); loadTasks(); loadStats(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    // --- Scenario 3: Period status override ---
    overridePeriodStatus(id, current) {
        showEditModal(`シフト期間 #${id} ステータス変更`, [
            { key: 'status', label: 'ステータス', type: 'select', value: current, options: [
                { value: 'draft', label: 'draft' }, { value: 'open', label: 'open' }, { value: 'closed', label: 'closed' }, { value: 'finalized', label: 'finalized' },
            ]},
            { key: 'submission_deadline', label: '提出締切 (延長する場合)', type: 'datetime-local', value: '' },
        ], async (data) => {
            if (!data.submission_deadline) delete data.submission_deadline;
            try { await api.put(`/api/master/periods/${id}/status`, data); showToast('ステータスを変更しました', 'success'); loadedTabs.delete('periods'); loadPeriods(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    // --- Scenario 3: Schedule status override ---
    overrideScheduleStatus(id, current) {
        showEditModal(`スケジュール #${id} ステータス変更`, [
            { key: 'status', label: 'ステータス', type: 'select', value: current, options: [
                { value: 'draft', label: 'draft' }, { value: 'pending_approval', label: 'pending_approval' }, { value: 'approved', label: 'approved' }, { value: 'rejected', label: 'rejected' }, { value: 'confirmed', label: 'confirmed' },
            ]},
        ], async (data) => {
            try { await api.put(`/api/master/schedules/${id}/status`, data); showToast('ステータスを変更しました', 'success'); loadedTabs.delete('schedules'); loadSchedules(); } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    // --- Scenario 4: Calendar re-sync ---
    async resyncSchedule(id) {
        showConfirmDialog('カレンダー再同期', `スケジュール #${id} の未同期エントリをタスクキューに追加しますか？`, 'btn-primary', '再同期', async () => {
            try {
                const res = await api.post(`/api/master/schedules/${id}/resync`);
                showToast(`${res.enqueued} 件をキューに追加しました`, 'success');
                loadedTabs.delete('schedules'); loadSchedules();
            } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    async showSyncStatus(id) {
        try {
            const entries = await api.get(`/api/master/schedules/${id}/sync-status`);
            const rows = entries.map(e => `
                <tr>
                    <td>${escapeHtml(e.user_name || e.user_email)}</td>
                    <td>${e.shift_date}</td>
                    <td>${e.start_time} ~ ${e.end_time}</td>
                    <td>${e.is_synced ? '<span class="badge badge-completed">同期済</span>' : '<span class="badge badge-failed">未同期</span>'}</td>
                </tr>
            `).join('');
            showDetailModal(`スケジュール #${id} 同期状況`, `
                <h3>同期状況</h3>
                <div class="table-wrap"><table class="data-table"><thead><tr><th>ワーカー</th><th>日付</th><th>時間</th><th>同期</th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="empty-state">エントリなし</td></tr>'}</tbody></table></div>
            `);
        } catch (e) { showToast('読み込み失敗: ' + e.message, 'error'); }
    },

    // --- Scenario 5: Submission compliance ---
    async showCompliance(periodId) {
        try {
            const c = await api.get(`/api/master/periods/${periodId}/compliance`);
            const overlay = showDetailModal(`${c.period_name} — 提出状況`, `
                <h3>提出状況: ${escapeHtml(c.period_name)}</h3>
                <div class="compliance-section">
                    <div class="compliance-bar"><div class="compliance-bar-fill" style="width:${c.submission_rate}%"></div></div>
                    <div style="font-size:0.9em;color:var(--color-neutral-600);">${c.submitted_count} / ${c.total_workers} 名提出済 (${c.submission_rate}%)</div>
                </div>
                ${c.missing.length ? `
                <div class="compliance-section">
                    <div class="compliance-section-title" style="color:var(--color-danger-600);">未提出 (${c.missing.length}名)</div>
                    ${c.missing.map(m => `
                        <div class="compliance-user">
                            <span>${escapeHtml(m.user_name || m.email)} ${m.draft_exists ? '<span class="badge badge-draft">下書きあり</span>' : ''}</span>
                            <button class="btn btn-danger btn-xs" data-proxy-user="${m.user_id}">代理提出（全日不可）</button>
                        </div>
                    `).join('')}
                </div>` : ''}
                ${c.submitted.length ? `
                <div class="compliance-section">
                    <div class="compliance-section-title" style="color:var(--color-success-600);">提出済 (${c.submitted.length}名)</div>
                    ${c.submitted.map(s => `<div class="compliance-user"><span>${escapeHtml(s.user_name || s.email)}</span><span style="font-size:0.82em;color:var(--color-neutral-400);">${formatDateTime(s.submitted_at)}</span></div>`).join('')}
                </div>` : ''}
            `);
            // Bind proxy submit buttons
            overlay.querySelectorAll('[data-proxy-user]').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const userId = parseInt(btn.dataset.proxyUser);
                    showConfirmDialog('代理提出', 'このワーカーを全日不可として代理提出しますか？', 'btn-danger', '代理提出', async () => {
                        try {
                            await api.post(`/api/master/periods/${periodId}/submit-for-user`, { user_id: userId });
                            showToast('代理提出しました', 'success');
                            overlay.remove();
                            loadedTabs.delete('periods');
                            loadPeriods();
                        } catch (e) { showToast('失敗: ' + e.message, 'error'); }
                    });
                });
            });
        } catch (e) { showToast('読み込み失敗: ' + e.message, 'error'); }
    },

    // --- Scenario 6: Health fix ---
    async healthFix(fixType) {
        showConfirmDialog('修正の実行', `「${fixType}」の自動修正を実行しますか？`, 'btn-danger', '修正', async () => {
            try {
                const res = await api.post('/api/master/health-check/fix', { fix_type: fixType });
                showToast(`${res.fixed} 件を修正しました`, 'success');
                runHealthCheck();
                runHealthBanner();
                loadStats();
            } catch (e) { showToast('失敗: ' + e.message, 'error'); }
        });
    },

    showHealthDetail(jsonStr) {
        const items = JSON.parse(jsonStr);
        showDetailModal('問題の詳細', `<h3>検出された問題</h3><div class="json-detail">${escapeHtml(JSON.stringify(items, null, 2))}</div>`);
    },

    // --- Audit detail ---
    showAuditDetail(jsonStr) {
        const data = JSON.parse(jsonStr);
        showDetailModal('監査ログ詳細', `
            <h3>監査ログ詳細</h3>
            <div class="edit-modal-field"><label>変更前</label><div class="json-detail">${escapeHtml(JSON.stringify(data.old, null, 2) || 'なし')}</div></div>
            <div class="edit-modal-field"><label>変更後</label><div class="json-detail">${escapeHtml(JSON.stringify(data.new, null, 2) || 'なし')}</div></div>
        `);
    },
};

// ============================================================
// Helpers
// ============================================================
function formatDate(iso) { return iso ? iso.substring(0, 10) : '-'; }
function formatDateTime(iso) { return iso ? iso.substring(0, 16).replace('T', ' ') : '-'; }
