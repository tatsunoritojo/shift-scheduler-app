/**
 * Calendar grid rendering module.
 */
import { WEEKDAY_NAMES } from './date-constants.js';

/**
 * Render a multi-month calendar in the target container.
 * @param {HTMLElement} container - Target container element
 * @param {string} startDate - YYYY-MM-DD
 * @param {string} endDate - YYYY-MM-DD
 * @param {Map|Object} dataMap - Map of dateStr -> data object
 * @param {Object} options - { onDayClick, renderDayContent }
 */
export function renderCalendar(container, startDate, endDate, dataMap, options = {}) {
    const start = new Date(startDate);
    const end = new Date(endDate);

    container.innerHTML = '';

    const months = getMonthsInRange(start, end);
    months.forEach(month => {
        const monthEl = createMonthCalendar(month, dataMap, options);
        container.appendChild(monthEl);
    });
}

function getMonthsInRange(start, end) {
    const months = [];
    const current = new Date(start.getFullYear(), start.getMonth(), 1);
    const endMonth = new Date(end.getFullYear(), end.getMonth(), 1);
    while (current <= endMonth) {
        months.push(new Date(current));
        current.setMonth(current.getMonth() + 1);
    }
    return months;
}

function createMonthCalendar(month, dataMap, options) {
    const monthContainer = document.createElement('div');
    monthContainer.className = 'month-container';

    const monthTitle = document.createElement('div');
    monthTitle.className = 'month-title';
    monthTitle.textContent = `${month.getFullYear()}年${month.getMonth() + 1}月`;
    monthContainer.appendChild(monthTitle);

    const grid = document.createElement('div');
    grid.className = 'calendar-grid';

    WEEKDAY_NAMES.forEach(day => {
        const header = document.createElement('div');
        header.className = 'calendar-header';
        header.textContent = day;
        grid.appendChild(header);
    });

    const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
    const startDayOfWeek = firstDay.getDay();
    const lastDay = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const daysInMonth = lastDay.getDate();

    for (let i = 0; i < startDayOfWeek; i++) {
        const emptyCell = document.createElement('div');
        emptyCell.className = 'calendar-day empty';
        grid.appendChild(emptyCell);
    }

    for (let day = 1; day <= daysInMonth; day++) {
        const cell = createDayCell(month.getFullYear(), month.getMonth(), day, dataMap, options);
        grid.appendChild(cell);
    }

    monthContainer.appendChild(grid);
    return monthContainer;
}

function createDayCell(year, month, day, dataMap, options) {
    const cell = document.createElement('div');
    cell.className = 'calendar-day';

    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    cell.setAttribute('data-date', dateStr);

    const dayNumber = document.createElement('div');
    dayNumber.className = 'day-number';
    dayNumber.textContent = day;
    cell.appendChild(dayNumber);

    const data = dataMap instanceof Map ? dataMap.get(dateStr) : (dataMap && dataMap[dateStr]);

    if (data) {
        if (options.renderDayContent) {
            options.renderDayContent(cell, dateStr, data);
        }

        if (options.onDayClick) {
            cell.style.cursor = 'pointer';
            cell.addEventListener('click', () => options.onDayClick(dateStr, data, cell));
        }
    }

    return cell;
}
