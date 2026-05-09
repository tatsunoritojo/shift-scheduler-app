/**
 * 設定タブのうち sync / opening-hours を除く全項目:
 *  - リマインダ設定 (reminder)
 *  - レベル設定 (Phase A: levels)
 *  - 重複チェック設定 (overlap-check)
 *  - 最低出勤設定 (min-attendance)
 *  - 必要人数設定 (Phase 2a-3 D: staffing)
 *  - 承認プロセス設定 (Phase A': workflow)
 *
 * ⚠ members.js と相互依存:
 *   - inviteOwner → loadInvitations (members.js)
 *     事業主招待を作成したら一覧を再描画するため
 *   - members.js changeMemberRole / removeMember → loadWorkflowSettings (本モジュール)
 *     ロール変更で owner_count が変わるため再読込
 *   ES module の循環 import は関数本体 (lazy) のみで解決するので問題なし.
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { showConfirmDialog } from '../modules/ui-dialogs.js';
import { state } from './state.js';
import { setDirty, setClean } from './dirty-tracker.js';
import { loadInvitations } from './members.js';
import { loadScheduleForPeriod } from './builder.js';

// ---- Reminder Settings ----

export async function loadReminderSettings() {
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

export async function saveReminderSettings() {
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

// ---- Level / Overlap / Min-Attendance Settings (Phase A) ----

export async function loadLevelSettings() {
    try {
        const data = await api.get('/api/admin/settings/levels');
        state.levelSystemState = {
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

export function renderLevelSettings() {
    const enabledToggle = document.getElementById('level-system-enabled');
    const tiersSection = document.getElementById('level-tiers-section');
    const list = document.getElementById('level-tiers-list');
    if (!enabledToggle || !tiersSection || !list) return;

    enabledToggle.checked = state.levelSystemState.enabled;
    tiersSection.style.display = state.levelSystemState.enabled ? '' : 'none';

    if (!state.levelSystemState.tiers.length) {
        list.innerHTML = '<p class="help-text" style="color:var(--color-neutral-400);">レベルがまだ設定されていません</p>';
    } else {
        list.innerHTML = state.levelSystemState.tiers.map((t, i) => `
            <div class="level-tier-row">
                <span class="tier-label"><strong>${escapeHtml(t.label)}</strong> <span style="color:var(--color-neutral-400);font-size:0.85em;">(${escapeHtml(t.key)})</span></span>
                <span class="tier-count">${t.member_count}名</span>
                <button class="btn btn-secondary btn-sm" data-action="moveLevelTierUp" data-key="${escapeHtml(t.key)}" ${i === 0 ? 'disabled' : ''} title="上へ"><i data-lucide="chevron-up" style="width:12px;height:12px;"></i></button>
                <button class="btn btn-secondary btn-sm" data-action="moveLevelTierDown" data-key="${escapeHtml(t.key)}" ${i === state.levelSystemState.tiers.length - 1 ? 'disabled' : ''} title="下へ"><i data-lucide="chevron-down" style="width:12px;height:12px;"></i></button>
                <button class="btn btn-destructive btn-sm" data-action="removeLevelTier" data-key="${escapeHtml(t.key)}" data-label="${escapeHtml(t.label)}" data-count="${t.member_count}" title="削除"><i data-lucide="trash-2" style="width:12px;height:12px;"></i></button>
            </div>
        `).join('');
    }
    if (window.lucide) lucide.createIcons();
}

export function addLevelTier() {
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
    if (state.levelSystemState.tiers.some(t => t.key === key)) {
        showToast('同じキーが既に存在します', 'warning');
        return;
    }
    state.levelSystemState.tiers.push({
        key, label, order: state.levelSystemState.tiers.length + 1, member_count: 0,
    });
    keyInput.value = '';
    labelInput.value = '';
    renderLevelSettings();
    setDirty('levels');
}

export function removeLevelTier(key, label, memberCount) {
    const proceed = () => {
        state.levelSystemState.tiers = state.levelSystemState.tiers.filter(t => t.key !== key);
        renderLevelSettings();
        setDirty('levels');
    };
    if (memberCount > 0) {
        showConfirmDialog(
            `「${label}」を削除しますか？`,
            `現在 ${memberCount}名のメンバーがこのレベルに割り当てられています。削除するとそのメンバーのレベルは未設定になります。`,
            'btn-destructive', '削除する', proceed,
        );
    } else {
        proceed();
    }
}

export function moveLevelTier(key, direction) {
    const idx = state.levelSystemState.tiers.findIndex(t => t.key === key);
    if (idx < 0) return;
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= state.levelSystemState.tiers.length) return;
    const tiers = state.levelSystemState.tiers;
    [tiers[idx], tiers[newIdx]] = [tiers[newIdx], tiers[idx]];
    tiers.forEach((t, i) => { t.order = i + 1; });
    renderLevelSettings();
    setDirty('levels');
}

export async function saveLevelSettings() {
    const enabled = document.getElementById('level-system-enabled').checked;
    const currentKeys = new Set(state.levelSystemState.tiers.map(t => t.key));

    try {
        const serverCfg = await api.get('/api/admin/settings/levels');
        const serverKeys = new Set((serverCfg.tiers || []).map(t => t.key));
        const removedTierKeys = [...serverKeys].filter(k => !currentKeys.has(k));

        await api.put('/api/admin/settings/levels', {
            enabled,
            tiers: state.levelSystemState.tiers.map(t => ({ key: t.key, label: t.label, order: t.order })),
            removed_tier_keys: removedTierKeys,
        });
        state.levelSystemState.enabled = enabled;
        showToast('レベル設定を保存しました', 'success');
        await loadLevelSettings();  // resets setClean('levels')
        state.membersTabLoaded = false;
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

export async function loadOverlapCheckSettings() {
    try {
        const data = await api.get('/api/admin/settings/overlap-check');
        state.overlapCheckState = {
            enabled: !!data.enabled,
            scope: data.scope || 'same_tier',
        };
        const el = document.getElementById('overlap-check-enabled');
        if (el) el.checked = state.overlapCheckState.enabled;
        setClean('overlap-check');
    } catch (e) {
        console.warn('Failed to load overlap check settings:', e);
    }
}

export async function saveOverlapCheckSettings() {
    const enabled = document.getElementById('overlap-check-enabled').checked;
    try {
        await api.put('/api/admin/settings/overlap-check', { enabled, scope: 'same_tier' });
        state.overlapCheckState.enabled = enabled;
        setClean('overlap-check');
        showToast('重複チェック設定を保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

export async function loadMinAttendanceSettings() {
    try {
        const data = await api.get('/api/admin/settings/min-attendance');
        state.minAttendanceState = {
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

export function renderMinAttendanceSettings() {
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
    modeEl.value = state.minAttendanceState.mode;
    unitEl.value = state.minAttendanceState.unit;
    countEl.value = state.minAttendanceState.org_wide_count_per_week;
    hoursEl.value = state.minAttendanceState.org_wide_hours_per_week;
    countDraftsEl.checked = state.minAttendanceState.count_drafts;
    lookbackEl.value = state.minAttendanceState.lookback_periods;

    configEl.style.display = state.minAttendanceState.mode === 'disabled' ? 'none' : '';
    orgWideEl.style.display = state.minAttendanceState.mode === 'org_wide' ? '' : 'none';

    const showCount = state.minAttendanceState.unit === 'count' || state.minAttendanceState.unit === 'both';
    const showHours = state.minAttendanceState.unit === 'hours' || state.minAttendanceState.unit === 'both';
    countFieldEl.style.display = showCount ? '' : 'none';
    hoursFieldEl.style.display = showHours ? '' : 'none';
}

export async function saveMinAttendanceSettings() {
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
        state.minAttendanceState = payload;
        setClean('min-attendance');
        showToast('最低出勤設定を保存しました', 'success');
        state.membersTabLoaded = false;
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

// ---- Staffing Requirements (Phase 2a-3 D) ----

const STAFFING_DAY_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

export async function loadStaffingRequirements() {
    try {
        const data = await api.get('/api/admin/staffing-requirements');
        state.staffingDraft = (data || []).map(d => ({...d}));
        renderStaffingList();
        setClean('staffing');
    } catch (e) {
        const container = document.getElementById('staffing-list');
        if (container) {
            container.innerHTML = `<p style="color:var(--color-danger-600);font-size:0.9em;">読み込みに失敗しました: ${escapeHtml(e.message)}</p>`;
        }
    }
}

export function renderStaffingList() {
    const container = document.getElementById('staffing-list');
    if (!container) return;
    if (state.staffingDraft.length === 0) {
        container.innerHTML = '<p style="color:var(--color-neutral-500);font-size:0.9em;">未設定です。「+ 時間帯を追加」から設定を始めてください。</p>';
        return;
    }
    container.innerHTML = state.staffingDraft.map((row, i) => `
        <div class="staffing-row" style="display:grid;grid-template-columns:110px 1fr 1fr 100px auto;gap:8px;align-items:center;margin-bottom:6px;">
            <select class="form-control form-control-sm" data-action="updateStaffingField" data-index="${i}" data-field="day_of_week" aria-label="${i+1}行目 曜日">
                ${STAFFING_DAY_LABELS.map((label, dow) => `<option value="${dow}"${row.day_of_week === dow ? ' selected' : ''}>${label}曜日</option>`).join('')}
            </select>
            <input type="time" class="form-control form-control-sm" value="${row.start_time}" data-action="updateStaffingField" data-index="${i}" data-field="start_time" aria-label="${i+1}行目 開始時刻">
            <input type="time" class="form-control form-control-sm" value="${row.end_time}" data-action="updateStaffingField" data-index="${i}" data-field="end_time" aria-label="${i+1}行目 終了時刻">
            <input type="number" min="0" max="999" class="form-control form-control-sm" value="${row.required_count}" data-action="updateStaffingField" data-index="${i}" data-field="required_count" aria-label="${i+1}行目 必要人数">
            <button class="btn btn-destructive btn-sm" data-action="removeStaffingRow" data-index="${i}" title="この時間帯を削除" aria-label="${i+1}行目を削除"><i data-lucide="x" style="width:13px;height:13px;"></i></button>
        </div>
    `).join('');
    if (window.lucide) lucide.createIcons();
}

export function addStaffingRow() {
    state.staffingDraft.push({
        day_of_week: 1,
        start_time: '09:00',
        end_time: '17:00',
        required_count: 1,
    });
    renderStaffingList();
    setDirty('staffing');
}

export function removeStaffingRow(index) {
    if (index < 0 || index >= state.staffingDraft.length) return;
    state.staffingDraft.splice(index, 1);
    renderStaffingList();
    setDirty('staffing');
}

export function updateStaffingField(index, field, value) {
    if (!state.staffingDraft[index]) return;
    if (field === 'day_of_week' || field === 'required_count') {
        state.staffingDraft[index][field] = Number(value);
    } else {
        state.staffingDraft[index][field] = value;
    }
    setDirty('staffing');
}

export async function saveStaffingRequirements() {
    // クライアント側で軽くバリデーション（API 側でも検証されるが、UX 改善）
    for (let i = 0; i < state.staffingDraft.length; i++) {
        const r = state.staffingDraft[i];
        if (!r.start_time || !r.end_time) {
            showToast(`${i + 1} 行目: 時刻を入力してください`, 'warning');
            return;
        }
        if (r.start_time >= r.end_time) {
            showToast(`${i + 1} 行目: 開始時刻は終了時刻より前にしてください`, 'warning');
            return;
        }
        if (r.required_count < 0 || r.required_count > 999) {
            showToast(`${i + 1} 行目: 必要人数は 0〜999 の範囲で指定してください`, 'warning');
            return;
        }
    }
    try {
        const data = await api.put('/api/admin/staffing-requirements', { items: state.staffingDraft });
        state.staffingDraft = (data || []).map(d => ({...d}));
        renderStaffingList();
        setClean('staffing');
        showToast('必要人数設定を保存しました', 'success');
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

// ---- Workflow Settings (Phase A') ----

export async function loadWorkflowSettings() {
    try {
        const data = await api.get('/api/admin/settings/workflow');
        state.workflowState = {
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
    toggle.checked = state.workflowState.approval_required;
    updateWorkflowWarning();
}

export function updateWorkflowWarning() {
    // Reflect warning banner based on CURRENT checkbox state (not server state),
    // so users see the warning while still toggling ON before saving.
    const toggle = document.getElementById('workflow-approval-required');
    const warning = document.getElementById('workflow-owner-warning');
    if (!toggle || !warning) return;
    const wantsApproval = toggle.checked;
    const needWarn = wantsApproval && state.workflowState.owner_count < 1;
    warning.style.display = needWarn ? '' : 'none';
}

function renderOwnerInviteCard() {
    const card = document.getElementById('owner-invite-card');
    if (!card) return;
    const show = state.workflowState.approval_required && state.workflowState.owner_count < 1;
    card.style.display = show ? '' : 'none';
}

export async function saveWorkflowSettings() {
    const enabled = document.getElementById('workflow-approval-required').checked;
    try {
        const result = await api.put('/api/admin/settings/workflow', {
            approval_required: enabled,
        });
        state.workflowState = {
            approval_required: !!result.approval_required,
            owner_count: result.owner_count ?? 0,
            pending_schedules_count: result.pending_schedules_count ?? 0,
        };
        renderWorkflowSettings();
        renderOwnerInviteCard();
        setClean('workflow');
        showToast('承認プロセス設定を保存しました', 'success');
        // Refresh schedule UI if a period is currently loaded
        if (state.currentPeriod) {
            loadScheduleForPeriod(state.currentPeriod.id);
        }
    } catch (e) {
        const msg = e.message || '保存に失敗しました';
        // Revert toggle state on failure
        const toggle = document.getElementById('workflow-approval-required');
        if (toggle) toggle.checked = state.workflowState.approval_required;
        showToast(msg, 'error');
    }
}

export async function inviteOwner() {
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

export function gotoOwnerInvite() {
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
