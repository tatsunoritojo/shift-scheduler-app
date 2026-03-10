/**
 * Time utility functions shared across the shift management system.
 */
import { WEEKDAY_NAMES } from './date-constants.js';

export function timeToMinutes(timeStr) {
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
}

export function minutesToTime(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
}

export function calculateDuration(startTime, endTime) {
    return (timeToMinutes(endTime) - timeToMinutes(startTime)) / 60;
}

export function addHours(timeStr, hours) {
    const startMinutes = timeToMinutes(timeStr);
    const endMinutes = startMinutes + (hours * 60);
    return minutesToTime(Math.round(endMinutes));
}

export function formatDate(date) {
    const d = new Date(date);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

export function formatDateJP(dateStr) {
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}(${WEEKDAY_NAMES[d.getDay()]})`;
}
