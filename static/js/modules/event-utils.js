/**
 * Shared calendar event utility functions.
 */

/**
 * Check if a calendar event is an all-day event.
 * All-day events have date-only start values (YYYY-MM-DD, length 10).
 */
export function isAllDayEvent(event) {
    return event.start && event.start.length === 10;
}

/**
 * Filter events that overlap with a given date.
 * @param {Array} events - Array of calendar event objects with start/end properties
 * @param {string} dateStr - Date string in YYYY-MM-DD format
 * @returns {Array} Events occurring on the given date
 */
export function getEventsForDate(events, dateStr) {
    return events.filter(e => {
        const eventStart = (e.start || '').substring(0, 10);
        const eventEnd = (e.end || '').substring(0, 10);
        return eventStart === dateStr || (eventStart < dateStr && eventEnd > dateStr);
    });
}

/**
 * Format an ISO datetime string for display as submission timestamp.
 * @param {string} isoStr - ISO datetime string
 * @returns {string} Formatted string like "3/15 14:30"
 */
export function formatSubmittedAt(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
