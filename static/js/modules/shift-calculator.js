/**
 * Core shift availability calculation logic.
 */
import { timeToMinutes, minutesToTime } from './time-utils.js';

/**
 * Calculate available time slots given a work window and a list of events.
 * @param {string} startTime - Work window start (HH:MM)
 * @param {string} endTime - Work window end (HH:MM)
 * @param {Array} events - Array of { start: 'HH:MM', end: 'HH:MM' }
 * @param {Object} settings - { bufferTime: minutes, minGapTime: minutes }
 * @returns {Array} Array of { start, end, duration }
 */
export function calculateAvailableSlots(startTime, endTime, events, settings) {
    const slots = [];
    const workStart = timeToMinutes(startTime);
    const workEnd = timeToMinutes(endTime);

    const sorted = [...events].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));

    let currentStart = workStart;

    for (const event of sorted) {
        const eventStart = Math.max(workStart, timeToMinutes(event.start) - settings.bufferTime);
        const eventEnd = Math.min(workEnd, timeToMinutes(event.end) + settings.bufferTime);

        if (currentStart < eventStart) {
            const slotDuration = (eventStart - currentStart) / 60;
            if (slotDuration >= settings.minGapTime / 60) {
                slots.push({
                    start: minutesToTime(currentStart),
                    end: minutesToTime(eventStart),
                    duration: slotDuration,
                });
            }
        }
        currentStart = Math.max(currentStart, eventEnd);
    }

    if (currentStart < workEnd) {
        const slotDuration = (workEnd - currentStart) / 60;
        if (slotDuration >= settings.minGapTime / 60) {
            slots.push({
                start: minutesToTime(currentStart),
                end: minutesToTime(workEnd),
                duration: slotDuration,
            });
        }
    }

    return slots;
}
