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
        window.location.href = '/auth/google/login';
        throw new Error('Unauthorized');
    }

    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `HTTP ${res.status}`);
    }

    if (res.status === 204) return null;
    return res.json();
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
