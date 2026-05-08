/**
 * シフト期間 (ShiftPeriod) 一覧の管理 + 募集文面エディタ + リマインド送信.
 *
 * 機能:
 *  - 期間タブ: 一覧表示 / 新規作成 / 公開 (open) / 締切 / アーカイブ / 完全削除
 *  - 募集文面エディタ: 期間ごとに「募集開始メール」に含まれる文面を編集
 *  - 未提出者へのリマインド送信
 *
 * 設計メモ: アーカイブ/削除/復元時に builder の期間ドロップダウンを再描画する
 * 必要があるが、loadBuilderPeriodSelect は builder.js (PR10 で抽出予定) にある。
 * 循環 import を避けるため CustomEvent 'admin:periods-changed' で通知する。
 * 受信側 (admin-app.js または将来の builder.js) で document.addEventListener する。
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { showConfirmDialog } from '../modules/ui-dialogs.js';
import { state } from './state.js';
import { setTabBadge, switchTab } from './tabs.js';
import { openShareModal } from './share.js';

/** builder 等への変更通知。document level の CustomEvent を投げる. */
function notifyPeriodsChanged() {
    document.dispatchEvent(new CustomEvent('admin:periods-changed'));
}

// ---- Period list ----

export async function loadPeriods() {
    const url = state.periodsIncludeArchived
        ? '/api/admin/periods?include_archived=true'
        : '/api/admin/periods';
    const data = await api.get(url);
    state.cachedPeriods = data || [];
    const container = document.getElementById('periods-table-container');

    // バッジ ⑤ は閉鎖中（status=closed）かつ未アーカイブの期間数を表示
    const buildPending = state.cachedPeriods.filter(
        p => p.status === 'closed' && !p.is_archived
    ).length;
    setTabBadge('builder', buildPending);

    if (!data || data.length === 0) {
        const msg = state.periodsIncludeArchived
            ? '<p>シフト期間はまだありません</p><p class="empty-state-hint">上のフォームから新しいシフト期間を作成してください</p>'
            : '<p>表示できるシフト期間はありません</p><p class="empty-state-hint">「アーカイブ済を表示」を有効にするとアーカイブ済みも見られます</p>';
        container.innerHTML = `<div class="empty-state">${msg}</div>`;
        return;
    }

    const statusLabels = {
        draft: '下書き', open: '募集中', closed: '締切', finalized: '確定済',
    };

    container.innerHTML = `
        <table class="data-table">
            <thead><tr><th>名前</th><th>期間</th><th>ステータス</th><th>操作</th></tr></thead>
            <tbody>
                ${data.map(p => renderPeriodRow(p, statusLabels)).join('')}
            </tbody>
        </table>
    `;
}

function renderPeriodRow(p, statusLabels) {
    const archivedBadge = p.is_archived
        ? '<span class="badge" style="background:var(--color-neutral-200);color:var(--color-neutral-700);margin-left:6px;">アーカイブ済</span>'
        : '';
    const rowStyle = p.is_archived ? 'opacity:0.65;' : '';
    const statusBadge = `<span class="badge badge-${p.status}">${statusLabels[p.status] || p.status}</span>${archivedBadge}`;

    if (p.is_archived) {
        // アーカイブ済の場合: 復元・完全削除のみ
        return `
            <tr style="${rowStyle}">
                <td>${escapeHtml(p.name)}</td>
                <td>${p.start_date} 〜 ${p.end_date}</td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;" data-action="unarchivePeriod" data-id="${p.id}" title="アーカイブを解除して通常表示に戻します"><i data-lucide="archive-restore" style="width:13px;height:13px;"></i> 復元</button>
                    <button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;color:var(--color-danger-600,#dc2626);border-color:var(--color-danger-300,#fca5a5);" data-action="deletePeriod" data-id="${p.id}" data-name="${escapeHtml(p.name)}" title="シフト期間と関連データを完全に削除します"><i data-lucide="trash-2" style="width:13px;height:13px;"></i> 完全削除</button>
                </td>
            </tr>
        `;
    }

    // 通常表示（完全削除はアーカイブ後のみ可能なため、ここには配置しない — フェールセーフ）
    return `
        <tr>
            <td>${escapeHtml(p.name)}</td>
            <td>${p.start_date} 〜 ${p.end_date}</td>
            <td>${statusBadge}</td>
            <td>
                <button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;" data-action="editPeriodAnnouncement" data-period-id="${p.id}" title="募集文面を編集（メールに含まれる本文）"><i data-lucide="message-square" style="width:13px;height:13px;"></i> 文面</button>
                ${p.status === 'draft' ? `<button class="btn btn-primary" style="padding:4px 12px;font-size:0.85em;" data-action="publishPeriod" data-period-id="${p.id}">募集開始</button>` : ''}
                ${p.status === 'open' ? `<button class="btn btn-warning" style="padding:4px 12px;font-size:0.85em;" data-action="updatePeriodStatus" data-id="${p.id}" data-status="closed">締切</button>` : ''}
                ${p.status === 'open' ? `<button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;" data-action="sendPeriodReminder" data-period-id="${p.id}" title="未提出者にリマインド送信"><i data-lucide="bell" style="width:13px;height:13px;"></i> リマインド</button>` : ''}
                <button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;" data-action="openShareModal" data-period-id="${p.id}" title="募集案内をPNG/PDFで保存"><i data-lucide="download" style="width:13px;height:13px;"></i> 案内DL</button>
                <button class="btn btn-outline" style="padding:4px 12px;font-size:0.85em;" data-action="archivePeriod" data-id="${p.id}" data-name="${escapeHtml(p.name)}" title="一覧から非表示にします（後で復元・完全削除が可能）"><i data-lucide="archive" style="width:13px;height:13px;"></i> アーカイブ</button>
            </td>
        </tr>
    `;
}

export async function archivePeriod(periodId, periodName) {
    showConfirmDialog(
        `「${periodName}」をアーカイブしますか？`,
        'アーカイブ済の期間は一覧から非表示になります。「アーカイブ済を表示」トグルから後で確認・復元できます。',
        'btn-primary',
        'アーカイブする',
        async () => {
            try {
                await api.post(`/api/admin/periods/${periodId}/archive`, {});
                showToast('アーカイブしました', 'success');
                await loadPeriods();
                notifyPeriodsChanged();
            } catch (e) {
                showToast(`アーカイブに失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

export async function unarchivePeriod(periodId) {
    try {
        await api.post(`/api/admin/periods/${periodId}/unarchive`, {});
        showToast('アーカイブを解除しました', 'success');
        await loadPeriods();
        notifyPeriodsChanged();
    } catch (e) {
        showToast(`アーカイブ解除に失敗しました: ${e.message}`, 'error');
    }
}

export async function deletePeriod(periodId, periodName) {
    // 削除前に影響範囲を取得
    let impact;
    try {
        impact = await api.get(`/api/admin/periods/${periodId}/impact`);
    } catch (e) {
        showToast(`影響範囲の取得に失敗しました: ${e.message}`, 'error');
        return;
    }

    const lines = [];
    lines.push('<strong>この操作は取り消せません。</strong>');
    lines.push('');
    lines.push('削除される関連データ:');
    lines.push(`・提出されたシフト希望: ${impact.submissions} 件`);
    lines.push(`・確定済シフト枠: ${impact.entries} 件`);
    if (impact.synced_entries > 0) {
        lines.push(`　（うち Google カレンダー同期済: ${impact.synced_entries} 件 — best-effort で削除を試みます）`);
    }
    if (impact.vacancies > 0) {
        lines.push(`・急募リクエスト: ${impact.vacancies} 件`);
    }
    if (impact.change_logs > 0) {
        lines.push(`・シフト変更履歴: ${impact.change_logs} 件`);
    }
    if (impact.reminders > 0) {
        lines.push(`・リマインダ送信記録: ${impact.reminders} 件`);
    }

    showConfirmDialog(
        `「${periodName}」を完全に削除しますか？`,
        lines.join('<br>'),
        'btn-danger',
        '完全に削除する',
        async () => {
            try {
                const result = await api.delete(`/api/admin/periods/${periodId}`);
                const summary = result && result.cleanup_summary ? result.cleanup_summary : {};
                let msg = '完全に削除しました';
                const notes = [];
                if (summary.calendar_events_failed > 0) {
                    notes.push(`カレンダー削除失敗: ${summary.calendar_events_failed} 件`);
                }
                if (summary.calendar_events_skipped > 0) {
                    notes.push(`カレンダー未同期スキップ: ${summary.calendar_events_skipped} 件`);
                }
                if (notes.length > 0) {
                    msg += `（${notes.join('、')}）`;
                }
                showToast(msg, 'success');
                await loadPeriods();
                notifyPeriodsChanged();
            } catch (e) {
                showToast(`削除に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

export function gotoArchivedPeriods() {
    // シフト期間タブへ遷移し、アーカイブ済を表示する
    state.periodsIncludeArchived = true;
    const cb = document.getElementById('periods-include-archived');
    if (cb) cb.checked = true;
    switchTab('periods');
    loadPeriods();
}

export async function promptArchiveAfterConfirm(period) {
    if (!period || period.is_archived) return;
    showConfirmDialog(
        'シフトを確定しました',
        `このシフト期間「${escapeHtml(period.name)}」をアーカイブしますか？<br>アーカイブ済の期間は一覧から非表示になります（後で復元可能）。`,
        'btn-primary',
        'アーカイブする',
        async () => {
            try {
                await api.post(`/api/admin/periods/${period.id}/archive`, {});
                showToast('アーカイブしました', 'success');
                await loadPeriods();
                notifyPeriodsChanged();
            } catch (e) {
                showToast(`アーカイブに失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

export async function createPeriod() {
    const announcement = document.getElementById('period-announcement').value.trim();
    const data = {
        name: document.getElementById('period-name').value,
        start_date: document.getElementById('period-start').value,
        end_date: document.getElementById('period-end').value,
        status: document.getElementById('period-status').value,
        submission_deadline: document.getElementById('period-deadline').value || null,
        announcement_text: announcement || null,
    };
    if (!data.name || !data.start_date || !data.end_date) {
        showToast('名前と期間を入力してください', 'warning');
        return;
    }
    try {
        const created = await api.post('/api/admin/periods', data);
        showToast('シフト期間を作成しました', 'success');
        // 入力欄をリセット
        document.getElementById('period-announcement').value = '';
        await loadPeriods();
        // Auto-open share modal so the admin can download the recruitment
        // calendar immediately after creation.
        if (created && created.id) {
            openShareModal(created.id);
        }
    } catch (e) {
        showToast(`作成に失敗しました: ${e.message}`, 'error');
    }
}

export async function updatePeriodStatus(id, status) {
    try {
        await api.put(`/api/admin/periods/${id}`, { status });
        showToast('ステータスを更新しました', 'success');
        await loadPeriods();
    } catch (e) {
        showToast(`更新に失敗しました: ${e.message}`, 'error');
    }
}

// ---- Period announcement editor ----

export function editPeriodAnnouncement(periodId) {
    const period = state.cachedPeriods.find(p => p.id === periodId);
    if (!period) {
        showToast('対象の期間が見つかりません', 'error');
        return;
    }
    state.editingAnnouncementPeriodId = periodId;
    document.getElementById('announcement-target-name').textContent = period.name;
    const textarea = document.getElementById('announcement-textarea');
    textarea.value = period.announcement_text || '';
    updateAnnouncementCharCount();
    textarea.oninput = updateAnnouncementCharCount;
    const modal = document.getElementById('period-announcement-modal');
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    if (window.lucide) lucide.createIcons();
    textarea.focus();
}

function updateAnnouncementCharCount() {
    const len = document.getElementById('announcement-textarea').value.length;
    document.getElementById('announcement-charcount').textContent = `${len} / 4000 文字`;
}

export function closeAnnouncementEditor() {
    const modal = document.getElementById('period-announcement-modal');
    modal.hidden = true;
    document.body.style.overflow = '';
    const textarea = document.getElementById('announcement-textarea');
    if (textarea) textarea.oninput = null;
    state.editingAnnouncementPeriodId = null;
}

export async function saveAnnouncement() {
    if (state.editingAnnouncementPeriodId == null) return;
    const value = document.getElementById('announcement-textarea').value.trim();
    if (value.length > 4000) {
        showToast('募集文面は 4000 文字までです', 'warning');
        return;
    }
    try {
        await api.put(`/api/admin/periods/${state.editingAnnouncementPeriodId}`, {
            announcement_text: value || null,
        });
        showToast('募集文面を保存しました', 'success');
        closeAnnouncementEditor();
        await loadPeriods();
    } catch (e) {
        showToast(`保存に失敗しました: ${e.message}`, 'error');
    }
}

export async function publishPeriod(periodId) {
    const period = state.cachedPeriods.find(p => p.id === periodId);
    if (!period) {
        showToast('対象の期間が見つかりません', 'error');
        return;
    }
    const hasAnnouncement = !!(period.announcement_text && period.announcement_text.trim());
    const announceHint = hasAnnouncement
        ? '募集文面が設定されているので、メール本文に含まれます。'
        : '募集文面は未設定です。先に「文面」ボタンから入力できます。';
    showConfirmDialog(
        `「${escapeHtml(period.name)}」を募集中にしますか？`,
        `組織内の Worker 全員にシフト募集開始のメールが自動送信されます。${announceHint}`,
        'btn-primary',
        '募集を開始する',
        async () => {
            try {
                const result = await api.put(`/api/admin/periods/${periodId}`, { status: 'open' });
                const count = (result && typeof result.notified_count === 'number') ? result.notified_count : 0;
                showToast(`募集を開始しました（${count} 名にメール送信）`, 'success');
                await loadPeriods();
            } catch (e) {
                showToast(`公開に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}

// ---- Reminder send ----

export async function sendPeriodReminder(periodId) {
    showConfirmDialog(
        '未提出者にリマインドを送信しますか？',
        'まだシフト希望を提出していないアルバイトにメールで通知します。',
        'btn-primary',
        '送信する',
        async () => {
            try {
                const result = await api.post(`/api/admin/reminders/send/${periodId}`);
                showToast(`リマインド送信: ${result.sent}件送信, ${result.skipped}件スキップ`, 'success');
            } catch (e) {
                showToast(`送信に失敗しました: ${e.message}`, 'error');
            }
        }
    );
}
