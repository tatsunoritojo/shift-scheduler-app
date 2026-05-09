/**
 * 欠員補充管理 + 変更履歴 (シフト構築タブのサイドバー).
 *
 * Admin が確定済みシフトに対して特定エントリの欠員を募集し、候補者を選択して
 * 通知を送信する。受け入れた候補者がいれば差し替え、変更履歴に記録される。
 * 変更履歴はサイドバーで時系列に表示する。
 *
 * 依存: api / showToast / escapeHtml / showConfirmDialog のみ。state 共有なし。
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { showConfirmDialog } from '../modules/ui-dialogs.js';

/**
 * 欠員補充リクエスト一覧を取得して #vacancy-list に描画する。
 */
export async function loadVacancies() {
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
                ${v.status === 'open' || v.status === 'notified' ? `<button class="btn btn-state-warning btn-sm" data-action="cancelVacancy" data-id="${v.id}" title="キャンセル"><i data-lucide="x" style="width:13px;height:13px;"></i></button>` : ''}
            </div>
        `).join('');
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        container.innerHTML = '<p class="help-text">読み込みに失敗しました</p>';
    }
}

/**
 * シフトエントリに対する欠員補充ダイアログを開く。候補者を選んで通知を送信する。
 * @param {number} entryId 対象 ShiftScheduleEntry の ID
 */
export async function openVacancyDialog(entryId) {
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
                    <button class="btn btn-secondary" id="vacancy-dialog-cancel">キャンセル</button>
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

/**
 * 欠員補充リクエストをキャンセルする（候補者通知を無効化）。
 * @param {number} id VacancyRequest ID
 */
export async function cancelVacancy(id) {
    showConfirmDialog(
        '欠員補充リクエストをキャンセルしますか？',
        'キャンセルすると、候補者への通知は無効になります。',
        'btn-state-warning',
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

/**
 * シフト変更履歴一覧を #change-log-list に描画する。
 */
export async function loadChangeLog() {
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
