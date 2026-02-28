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

/**
 * Calculate detailed slot breakdown for timeline visualization.
 * Returns all components: available slots, excluded gaps, buffer zones, and event blocks.
 */
export function calculateDetailedSlots(startTime, endTime, events, settings) {
    const workStart = timeToMinutes(startTime);
    const workEnd = timeToMinutes(endTime);

    const sorted = [...events].sort((a, b) => timeToMinutes(a.start) - timeToMinutes(b.start));

    const availableSlots = [];
    const excludedSlots = [];
    const bufferZones = [];
    const eventBlocks = [];

    // Build event blocks and buffer zones (clamped to work window)
    for (const event of sorted) {
        const rawStart = timeToMinutes(event.start);
        const rawEnd = timeToMinutes(event.end);
        const evStart = Math.max(workStart, rawStart);
        const evEnd = Math.min(workEnd, rawEnd);

        if (evStart < evEnd) {
            eventBlocks.push({
                start: minutesToTime(evStart),
                end: minutesToTime(evEnd),
                startMin: evStart,
                endMin: evEnd,
            });
        }

        // Pre-buffer
        const bufStart = Math.max(workStart, rawStart - settings.bufferTime);
        const bufEnd = Math.max(workStart, Math.min(workEnd, rawStart));
        if (bufStart < bufEnd) {
            bufferZones.push({
                start: minutesToTime(bufStart),
                end: minutesToTime(bufEnd),
                startMin: bufStart,
                endMin: bufEnd,
            });
        }

        // Post-buffer
        const postStart = Math.max(workStart, Math.min(workEnd, rawEnd));
        const postEnd = Math.min(workEnd, rawEnd + settings.bufferTime);
        if (postStart < postEnd) {
            bufferZones.push({
                start: minutesToTime(postStart),
                end: minutesToTime(postEnd),
                startMin: postStart,
                endMin: postEnd,
            });
        }
    }

    // Calculate gaps and classify as available or excluded
    let currentStart = workStart;
    for (const event of sorted) {
        const eventStart = Math.max(workStart, timeToMinutes(event.start) - settings.bufferTime);
        const eventEnd = Math.min(workEnd, timeToMinutes(event.end) + settings.bufferTime);

        if (currentStart < eventStart) {
            const gapMinutes = eventStart - currentStart;
            const slot = {
                start: minutesToTime(currentStart),
                end: minutesToTime(eventStart),
                startMin: currentStart,
                endMin: eventStart,
                duration: gapMinutes / 60,
            };
            if (gapMinutes >= settings.minGapTime) {
                availableSlots.push(slot);
            } else {
                excludedSlots.push(slot);
            }
        }
        currentStart = Math.max(currentStart, eventEnd);
    }

    // Final gap after last event
    if (currentStart < workEnd) {
        const gapMinutes = workEnd - currentStart;
        const slot = {
            start: minutesToTime(currentStart),
            end: minutesToTime(workEnd),
            startMin: currentStart,
            endMin: workEnd,
            duration: gapMinutes / 60,
        };
        if (gapMinutes >= settings.minGapTime) {
            availableSlots.push(slot);
        } else {
            excludedSlots.push(slot);
        }
    }

    return {
        availableSlots,
        excludedSlots,
        bufferZones,
        eventBlocks,
        workStart: minutesToTime(workStart),
        workEnd: minutesToTime(workEnd),
    };
}
