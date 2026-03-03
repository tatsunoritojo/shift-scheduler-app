/**
 * API client with authentication handling.
 */

const BASE_URL = '';

async function request(method, path, data = null) {
    const opts = {
        method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
    };
    if (data && method !== 'GET') {
        opts.body = JSON.stringify(data);
    }

    const res = await fetch(`${BASE_URL}${path}`, opts);

    if (res.status === 401) {
        const body = await res.json().catch(() => ({}));
        if (body.code === 'CREDENTIALS_EXPIRED') {
            showReauthModal(body.error || 'Google認証の有効期限が切れました。再ログインしてください。');
        } else {
            window.location.href = '/auth/google/login';
        }
        throw new Error(body.error || 'Unauthorized');
    }

    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `HTTP ${res.status}`);
    }

    if (res.status === 204) return null;
    return res.json();
}

function showReauthModal(message) {
    // Prevent duplicate modals
    if (document.getElementById('reauth-overlay')) return;

    const overlay = document.createElement('div');
    overlay.id = 'reauth-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:10001;';
    overlay.innerHTML = `
        <div style="background:#fff;border-radius:16px;padding:32px 28px;max-width:380px;width:90%;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,0.2);">
            <h3 style="margin:0 0 12px;font-size:1.15em;color:#1f2937;">再認証が必要です</h3>
            <p style="margin:0 0 24px;color:#6b7280;font-size:0.9em;line-height:1.6;">${message}</p>
            <a href="/auth/google/login" style="display:inline-block;padding:12px 28px;background:#3b82f6;color:#fff;border-radius:8px;text-decoration:none;font-weight:500;font-size:0.95em;">Googleで再ログイン</a>
        </div>
    `;
    document.body.appendChild(overlay);
}

export const api = {
    get: (path) => request('GET', path),
    post: (path, data) => request('POST', path, data),
    put: (path, data) => request('PUT', path, data),
    delete: (path) => request('DELETE', path),
};

export async function getCurrentUser() {
    return api.get('/auth/me');
}

export async function getCalendarEvents(startDate, endDate, calendarId = 'primary') {
    const params = new URLSearchParams({ startDate, endDate, calendarId });
    return api.get(`/api/calendar/events?${params}`);
}

export async function getCalendarList() {
    return api.get('/api/worker/calendars');
}
