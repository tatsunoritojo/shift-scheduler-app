/**
 * Shared UI dialog components.
 */

/**
 * Show a confirmation dialog overlay.
 * @param {string} title - Dialog title
 * @param {string} message - Dialog message
 * @param {string} btnClass - CSS class for the confirm button (e.g. 'btn-primary', 'btn-danger')
 * @param {string} btnLabel - Label for the confirm button
 * @param {Function} onConfirm - Callback when confirmed
 * @param {Function} [onCancel] - Optional callback when cancelled
 */
export function showConfirmDialog(title, message, btnClass, btnLabel, onConfirm, onCancel) {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-dialog-overlay';
    overlay.innerHTML = `
        <div class="confirm-dialog">
            <h3>${title}</h3>
            <p>${message}</p>
            <div class="confirm-dialog-actions">
                <button class="btn btn-outline" id="confirm-cancel">キャンセル</button>
                <button class="btn ${btnClass}" id="confirm-ok">${btnLabel}</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    const dismiss = () => {
        overlay.remove();
        if (onCancel) onCancel();
    };
    overlay.querySelector('#confirm-cancel').onclick = dismiss;
    overlay.querySelector('#confirm-ok').onclick = () => {
        overlay.remove();
        onConfirm();
    };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) dismiss(); });
}
