/**
 * 募集案内カレンダーの PNG / PDF / テキストメッセージ書き出しモーダル.
 *
 * Admin が「期間タブ」または「期間作成成功時」から起動する。html2canvas + jspdf
 * を使ってカレンダーカードを画像化する。コピー用テンプレ文も提供する。
 *
 * 依存:
 *  - state.currentOrgName, state.shareModalData (admin/state.js)
 *  - api / showToast / escapeHtml (modules/)
 *  - window.html2canvas, window.jspdf (admin.html で <script> 読込済の外部ライブラリ)
 */

import { api } from '../modules/api-client.js';
import { showToast } from '../modules/notification.js';
import { escapeHtml } from '../modules/escape-html.js';
import { state } from './state.js';

const SHARE_WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土'];

/**
 * 期間 ID を受け取り、必要データをまとめて取得して share モーダルを開く。
 * @param {number} periodId
 */
export async function openShareModal(periodId) {
    try {
        // Ensure org name is available for the card header
        const orgPromise = state.currentOrgName
            ? Promise.resolve({ organization_name: state.currentOrgName })
            : api.get('/api/admin/invite-code').catch(() => ({}));
        const [periods, openingHours, exceptions, orgData] = await Promise.all([
            api.get('/api/admin/periods'),
            api.get('/api/admin/opening-hours'),
            api.get('/api/admin/opening-hours/exceptions'),
            orgPromise,
        ]);
        if (orgData && orgData.organization_name) {
            state.currentOrgName = orgData.organization_name;
        }
        const period = periods.find(p => p.id === periodId);
        if (!period) {
            showToast('期間が見つかりません', 'error');
            return;
        }
        state.shareModalData = { period, openingHours, exceptions };
        renderShareModal();
        const modal = document.getElementById('period-share-modal');
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        showToast(`読み込みに失敗しました: ${e.message}`, 'error');
    }
}

export function closeShareModal() {
    const modal = document.getElementById('period-share-modal');
    modal.hidden = true;
    document.body.style.overflow = '';
    state.shareModalData = null;
}

function renderShareModal() {
    const { period, openingHours, exceptions } = state.shareModalData;
    const target = document.getElementById('share-export-target');
    target.innerHTML = buildShareCardHtml(period, openingHours, exceptions);
    document.getElementById('share-template-text').textContent = buildShareTemplate(period);
}

function buildShareCardHtml(period, openingHours, exceptions) {
    const hoursByDow = {};
    for (const h of (openingHours || [])) hoursByDow[h.day_of_week] = h;
    const excByDate = {};
    for (const e of (exceptions || [])) {
        if (e.exception_date) excByDate[e.exception_date] = e;
    }

    const start = parseLocalDate(period.start_date);
    const end = parseLocalDate(period.end_date);
    const months = shareGetMonthsInRange(start, end);
    const monthsHtml = months.map(m => buildShareMonthHtml(m, start, end, hoursByDow, excByDate)).join('');

    const titleHtml = escapeHtml(period.name) + ' シフト希望提出のご案内';
    const orgHtml = state.currentOrgName ? `<p class="shcard-org">${escapeHtml(state.currentOrgName)}</p>` : '';
    const rangeLabel = `対象期間: ${formatJpDate(start)} 〜 ${formatJpDate(end)}`;
    let deadlineLabel = '';
    if (period.submission_deadline) {
        const deadline = new Date(period.submission_deadline);
        deadlineLabel = `<span class="shcard-pill deadline">提出期限: ${formatJpDateTime(deadline)}まで</span>`;
    }
    const loginUrl = `${window.location.origin}/login`;

    return `
        <div class="shcard-brand">
            <div class="shcard-brand-icon">シ</div>
            <div class="shcard-brand-text">SHIFREE</div>
        </div>
        <h1 class="shcard-title">${titleHtml}</h1>
        ${orgHtml}
        <div class="shcard-info-row">
            <span class="shcard-pill">${escapeHtml(rangeLabel)}</span>
            ${deadlineLabel}
        </div>
        <div class="shcard-calendar-container">${monthsHtml}</div>
        <div class="shcard-legend">
            <div class="shcard-legend-item"><span class="shcard-legend-swatch in-range"></span>希望提出対象日</div>
            <div class="shcard-legend-item"><span class="shcard-legend-swatch out-of-range"></span>期間外</div>
            <div class="shcard-legend-item"><span class="shcard-legend-swatch closed"></span>休業日</div>
        </div>
        <div class="shcard-footer">
            <p>下記URLからログインして希望シフトをご提出ください</p>
            <p><span class="shcard-url">${escapeHtml(loginUrl)}</span></p>
        </div>
    `;
}

function buildShareMonthHtml(month, periodStart, periodEnd, hoursByDow, excByDate) {
    const year = month.getFullYear();
    const mo = month.getMonth();
    const firstDow = new Date(year, mo, 1).getDay();
    const daysInMonth = new Date(year, mo + 1, 0).getDate();

    const headers = SHARE_WEEKDAYS.map((d, i) => {
        const cls = i === 0 ? 'sun' : i === 6 ? 'sat' : '';
        return `<div class="shcard-header ${cls}">${d}</div>`;
    }).join('');

    let cells = '';
    for (let i = 0; i < firstDow; i++) {
        cells += '<div class="shcard-day empty"></div>';
    }
    for (let d = 1; d <= daysInMonth; d++) {
        const date = new Date(year, mo, d);
        const dateStr = `${year}-${String(mo + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const inRange = date >= periodStart && date <= periodEnd;
        const dow = date.getDay();

        // Resolve time: exception > regular opening hours
        const exc = excByDate[dateStr];
        const regular = hoursByDow[dow];
        let timeLabel = null;
        let isClosed = false;
        if (exc) {
            if (exc.is_closed) isClosed = true;
            else if (exc.start_time && exc.end_time) timeLabel = `${formatShortTime(exc.start_time)}〜${formatShortTime(exc.end_time)}`;
        } else if (regular) {
            if (regular.is_closed) isClosed = true;
            else if (regular.start_time && regular.end_time) timeLabel = `${formatShortTime(regular.start_time)}〜${formatShortTime(regular.end_time)}`;
        }

        const classes = ['shcard-day'];
        if (!inRange) classes.push('out-of-range');
        else if (isClosed) classes.push('closed');
        else classes.push('in-range');
        if (dow === 0) classes.push('sun');
        if (dow === 6) classes.push('sat');

        const timeHtml = inRange
            ? (isClosed
                ? '<span class="shcard-day-time closed-label">休</span>'
                : (timeLabel ? `<span class="shcard-day-time">${escapeHtml(timeLabel)}</span>` : ''))
            : '';

        cells += `
            <div class="${classes.join(' ')}">
                <span class="shcard-day-num">${d}</span>
                ${timeHtml}
            </div>
        `;
    }

    return `
        <div class="shcard-month">
            <div class="shcard-month-title">${year}年${mo + 1}月</div>
            <div class="shcard-grid">${headers}${cells}</div>
        </div>
    `;
}

function buildShareTemplate(period) {
    const start = parseLocalDate(period.start_date);
    const end = parseLocalDate(period.end_date);
    const startStr = formatJpDate(start);
    const endStr = formatJpDate(end);
    let deadlineLine = '';
    if (period.submission_deadline) {
        deadlineLine = `\n提出期限: ${formatJpDateTime(new Date(period.submission_deadline))}まで`;
    }
    const loginUrl = `${window.location.origin}/login`;
    return `【シフト希望提出のお願い】

期間: ${startStr} 〜 ${endStr}${deadlineLine}

下記リンクからシフリーにログインして、
希望シフトをご提出ください。

${loginUrl}

添付のカレンダー画像もご参照ください。
よろしくお願いします。`;
}

export async function shareDownloadPng() {
    if (!state.shareModalData || !window.html2canvas) {
        showToast('ダウンロードライブラリの読み込み中です', 'warning');
        return;
    }
    try {
        const target = document.getElementById('share-export-target');
        const canvas = await window.html2canvas(target, { scale: 2, backgroundColor: '#ffffff' });
        const link = document.createElement('a');
        link.download = sharedFileName(state.shareModalData.period.name, 'png');
        link.href = canvas.toDataURL('image/png');
        link.click();
        showToast('PNGを保存しました', 'success');
    } catch (e) {
        showToast(`PNG保存に失敗: ${e.message || e}`, 'error');
    }
}

export async function shareDownloadPdf() {
    if (!state.shareModalData || !window.html2canvas || !window.jspdf) {
        showToast('ダウンロードライブラリの読み込み中です', 'warning');
        return;
    }
    try {
        const target = document.getElementById('share-export-target');
        const canvas = await window.html2canvas(target, { scale: 2, backgroundColor: '#ffffff' });
        const imgData = canvas.toDataURL('image/png');
        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
        const pageWidth = 210;
        const pageHeight = 297;
        const imgWidth = pageWidth - 20;
        const imgHeight = canvas.height * imgWidth / canvas.width;
        pdf.addImage(imgData, 'PNG', 10, 10, imgWidth, Math.min(imgHeight, pageHeight - 20));
        pdf.save(sharedFileName(state.shareModalData.period.name, 'pdf'));
        showToast('PDFを保存しました', 'success');
    } catch (e) {
        showToast(`PDF保存に失敗: ${e.message || e}`, 'error');
    }
}

export async function shareCopyMessage() {
    const text = document.getElementById('share-template-text').textContent;
    try {
        await navigator.clipboard.writeText(text);
        showToast('メッセージをコピーしました', 'success');
    } catch (e) {
        showToast('コピーに失敗しました', 'error');
    }
}

// --- Share helpers (private to this module) ---

function sharedFileName(periodName, ext) {
    const safe = (periodName || '募集案内').replace(/[\\/:*?"<>|]/g, '_');
    return `shifree-${safe}-募集案内.${ext}`;
}

function parseLocalDate(str) {
    // 'YYYY-MM-DD' → local Date at midnight (avoid UTC shift from `new Date(str)`)
    if (!str) return null;
    const parts = str.split('-').map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2]);
}

function shareGetMonthsInRange(start, end) {
    const months = [];
    const current = new Date(start.getFullYear(), start.getMonth(), 1);
    const last = new Date(end.getFullYear(), end.getMonth(), 1);
    while (current <= last) {
        months.push(new Date(current));
        current.setMonth(current.getMonth() + 1);
    }
    return months;
}

function formatJpDate(d) {
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

function formatJpDateTime(d) {
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatShortTime(timeStr) {
    // '17:00:00' or '17:00' → '17:00'
    if (!timeStr) return '';
    return timeStr.slice(0, 5);
}
