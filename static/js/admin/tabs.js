/**
 * Admin タブ切替・タブバッジ・補助ナビゲーションのユーティリティ。
 *
 * 設計メモ: switchTab はタブ切替時の追加アクション（例: builder タブを開いたら
 * loadBuilderPeriodSelect / loadChangeLog / loadVacancies を実行）を必要とする。
 * これらは admin-app.js / 各サブモジュール側に定義されるため、循環 import を
 * 避けるためフック登録方式を採る。各モジュールが registerTabHook で副作用を登録し、
 * switchTab はそれを呼び出すだけにする。
 */

/** @type {Record<string, () => void>} */
const tabHooks = {};

/**
 * 指定タブが切替対象になったときに呼ばれる副作用を登録する。
 * 同じタブに対して複数回呼ぶと後勝ちで上書きされる。
 * @param {string} tabName
 * @param {() => void | Promise<void>} fn
 */
export function registerTabHook(tabName, fn) {
    tabHooks[tabName] = fn;
}

/**
 * タブを切り替える。.tab-content / .tab-btn の active クラスを付替し、
 * 登録済みフックがあれば実行する（fire-and-forget）。
 * @param {string} tabName
 */
export function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const tabContent = document.getElementById(`tab-${tabName}`);
    if (tabContent) tabContent.classList.add('active');
    const tabBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (tabBtn) tabBtn.classList.add('active');
    const hook = tabHooks[tabName];
    if (hook) hook();
}

/**
 * タブバッジに件数を表示する。0 以下なら非表示。
 * @param {string} tabName
 * @param {number} count
 */
export function setTabBadge(tabName, count) {
    const el = document.getElementById(`badge-${tabName}`);
    if (!el) return;
    if (count > 0) {
        el.textContent = String(count);
        el.hidden = false;
    } else {
        el.textContent = '';
        el.hidden = true;
    }
}

/**
 * タブバッジをドット表示（数字なし）にする。
 * @param {string} tabName
 * @param {boolean} show
 */
export function setTabBadgeDot(tabName, show) {
    const el = document.getElementById(`badge-${tabName}`);
    if (!el) return;
    el.textContent = '';
    el.hidden = !show;
}

/**
 * 手動設定の <details> を開いてから指定セクションへスクロールする。
 * @param {string} sectionId
 */
export function openManualAndScroll(sectionId) {
    const details = document.getElementById('manual-settings-details');
    if (details) {
        details.open = true;
        setTimeout(() => {
            const target = document.getElementById(sectionId);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    }
}

export function goToAddException() { openManualAndScroll('section-add-exception'); }
export function goToExceptionsList() { openManualAndScroll('section-exceptions-list'); }
export function goToOpeningHours() { openManualAndScroll('section-opening-hours'); }

/**
 * シフト期間名のデフォルト文字列を生成する。
 * @param {string} startStr YYYY-MM-DD
 * @param {string} endStr   YYYY-MM-DD
 */
export function generatePeriodName(startStr, endStr) {
    return `${startStr}〜${endStr} 自習室シフト`;
}
