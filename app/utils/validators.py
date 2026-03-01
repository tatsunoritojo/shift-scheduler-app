import re
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


_TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


def validate_time_str(time_str, field_name='time'):
    """Validate a time string in HH:MM format. Raises ValueError on invalid input."""
    if not isinstance(time_str, str) or not _TIME_RE.match(time_str):
        raise ValueError(f"Invalid {field_name}: expected HH:MM (00:00-23:59), got '{time_str}'")
    return time_str


def validate_text_length(value, field_name, max_length):
    """Validate that a text value does not exceed max_length. Raises ValueError if exceeded."""
    if value is not None and isinstance(value, str) and len(value) > max_length:
        raise ValueError(f"{field_name} exceeds maximum length of {max_length} characters")
    return value
