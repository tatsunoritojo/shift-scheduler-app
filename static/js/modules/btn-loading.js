/**
 * Button loading state helpers.
 *
 * Usage:
 *   import { setLoading, withLoading } from './modules/btn-loading.js';
 *   setLoading(btn, true);     // show spinner
 *   setLoading(btn, false);    // restore
 *   await withLoading(btn, async () => { ... });
 */

/**
 * Toggle loading state on a button.
 * Saves/restores original text content automatically.
 */
export function setLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
        if (!btn.dataset.originalText) {
            btn.dataset.originalText = btn.innerHTML;
        }
        btn.classList.add('btn-loading');
        btn.disabled = true;
    } else {
        btn.classList.remove('btn-loading');
        btn.disabled = false;
        if (btn.dataset.originalText) {
            btn.innerHTML = btn.dataset.originalText;
            delete btn.dataset.originalText;
        }
    }
}

/**
 * Execute an async function with button loading state.
 * Automatically sets loading before and restores after.
 */
export async function withLoading(btn, asyncFn) {
    setLoading(btn, true);
    try {
        return await asyncFn();
    } finally {
        setLoading(btn, false);
    }
}
