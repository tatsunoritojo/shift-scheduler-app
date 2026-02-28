from datetime import datetime, date, time


def parse_date(date_str):
    """Parse a YYYY-MM-DD string to a date object. Returns None on failure."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def parse_time(time_str):
    """Parse an HH:MM string to a time object. Returns None on failure."""
    try:
        parts = time_str.split(':')
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, TypeError, IndexError):
        return None
