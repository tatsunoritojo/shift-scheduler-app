/**
 * メンバー管理タブ: 招待コード (組織共通リンク + QR) / 個別招待 / メンバー一覧
 * (ロール変更・除外).
 *
 * ⚠ settings.js と相互依存:
 *   - changeMemberRole / removeMember → loadWorkflowSettings (settings.js)
 *     ロール変更・除外で承認プロセスの owner_count が変わるため再読込が必要
 *   - settings.js inviteOwner → loadInvitations (members.js)
 *     事業主招待を作成したら一覧を更新するため
 *   ES module の循環 import は関数本体 (lazy) のみで解決するので問題なし.
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { showConfirmDialog } from '../modules/ui-dialogs.js';
import { withLoading } from '../modules/btn-loading.js';
import { state } from './state.js';
import { setTabBadge } from './tabs.js';
import { loadWorkflowSettings } from './settings.js';

export async function loadMembersTab() {
    if (state.membersTabLoaded) return;
    state.membersTabLoaded = true;
    await Promise.all([loadInviteCode(), loadInvitations(), loadMembers()]);
    if (window.lucide) lucide.createIcons();
}

export async function loadInviteCode() {
    try {
        const data = await api.get('/api/admin/invite-code');
        if (data.organization_name) state.currentOrgName = data.organization_name;
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
    const orgName = state.currentOrgName || 'シフリー';
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

export async function generateInviteCode() {
    const hasExisting = document.getElementById('invite-code-content')?.style.display !== 'none';
    const doGenerate = async () => {
        const btn = document.getElementById('btn-regenerate-invite-code') || document.getElementById('btn-generate-invite-code');
        await withLoading(btn, async () => {
            await api.post('/api/admin/invite-code');
            showToast('招待コードを生成しました', 'success');
            state.membersTabLoaded = false;
            await loadMembersTab();
        });
    };
    if (hasExisting) {
        showConfirmDialog(
            '招待コードを再生成しますか？',
            '現在のコードは無効になり、既存の招待リンクやQRコードが使えなくなります。',
            'btn-state-warning',
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

export function copyInviteUrl() {
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

export async function toggleInviteCode(enabled) {
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

export async function loadInvitations() {
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
                <td>${valid && !t.used_at ? `<button class="btn btn-state-warning btn-sm" data-action="revokeInvitation" data-id="${t.id}" title="取消"><i data-lucide="x" style="width:13px;height:13px;"></i></button>` : ''}</td>
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

export async function createInvitation() {
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

export async function revokeInvitation(id) {
    showConfirmDialog(
        '招待を取り消しますか？',
        '取り消すと、このリンクは使えなくなります。',
        'btn-state-warning',
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

export async function loadMembers() {
    try {
        const data = await api.get('/api/admin/members');
        const container = document.getElementById('members-table');
        if (!data || data.length === 0) {
            container.innerHTML = '<p style="color:var(--color-neutral-400);font-size:0.9em;">メンバーはいません</p>';
            return;
        }
        const ROLE_LABELS = { admin: '管理者', owner: '事業主', worker: 'アルバイト' };
        const showLevel = state.levelSystemState.enabled && state.levelSystemState.tiers.length > 0;
        const showPerMemberAttendance = state.minAttendanceState.mode === 'per_member';
        const showCount = showPerMemberAttendance && (state.minAttendanceState.unit === 'count' || state.minAttendanceState.unit === 'both');
        const showHours = showPerMemberAttendance && (state.minAttendanceState.unit === 'hours' || state.minAttendanceState.unit === 'both');
        const rows = data.map(m => {
            const isSelf = state.currentUser && m.user_id === state.currentUser.id;
            const joined = m.joined_at ? new Date(m.joined_at).toLocaleDateString('ja-JP') : '-';
            const levelCell = showLevel ? `<td>
                <select class="form-control form-control-sm" data-action="changeMemberLevel" data-member-id="${m.id}">
                    <option value="">—</option>
                    ${state.levelSystemState.tiers.map(t => `<option value="${escapeHtml(t.key)}" ${m.level_key === t.key ? 'selected' : ''}>${escapeHtml(t.label)}</option>`).join('')}
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
                <td>${!isSelf ? `<button class="btn btn-state-warning btn-sm" data-action="removeMember" data-id="${m.id}" data-name="${escapeHtml(m.user_name || m.user_email || '')}" title="除外"><i data-lucide="user-x" style="width:13px;height:13px;"></i></button>` : ''}</td>
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

export async function changeMemberRole(memberId, newRole) {
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

export async function removeMember(id, name) {
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
        'btn-state-warning',
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

/**
 * メンバー属性 (level_key / min_attendance_*) の更新.
 * 各属性入力 (changeMemberLevel / changeMemberMinCount / changeMemberMinHours) から呼ばれる.
 * @param {number} memberId
 * @param {object} updates
 */
export async function updateMemberAttributes(memberId, updates) {
    try {
        await api.put(`/api/admin/members/${memberId}/attributes`, updates);
    } catch (e) {
        showToast(`メンバー属性の更新に失敗しました: ${e.message}`, 'error');
        throw e;
    }
}

