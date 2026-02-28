/**
 * Simple toast notification system.
 */

let container = null;

function ensureContainer() {
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;display:flex;flex-direction:column;gap:8px;';
        document.body.appendChild(container);
    }
    return container;
}

export function showToast(message, type = 'info', duration = 3000) {
    const c = ensureContainer();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    const colors = {
        success: '#4caf50',
        error: '#f44336',
        warning: '#ff9800',
        info: '#2196f3',
    };
    toast.style.cssText = `
        padding: 12px 20px; border-radius: 8px; color: white; font-size: 14px;
        background: ${colors[type] || colors.info}; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        opacity: 0; transform: translateX(100%); transition: all 0.3s ease;
    `;

    c.appendChild(toast);
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(0)';
    });

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}
