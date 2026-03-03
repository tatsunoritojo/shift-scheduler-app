import re
from datetime import datetime, date, time

_TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def parse_date(date_str):
    """Parse a YYYY-MM-DD string to a date object. Returns None on failure."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def parse_time(time_str):
    """Parse an HH:MM string to a time object. Returns None on failure."""
    if not isinstance(time_str, str):
        return None
    try:
        parts = time_str.split(':')
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def validate_time_str(value, field_name='time'):
    """Validate that *value* is an HH:MM string (00:00-23:59).

    Raises ValueError with a message referencing *field_name* on failure.
    """
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise ValueError(f"{field_name} must be in HH:MM format (00:00-23:59)")


def validate_text_length(value, field_name='text', max_length=1000):
    """Validate that *value* (if not None) does not exceed *max_length*.

    None and empty strings are allowed.
    Raises ValueError with a message referencing *field_name* on failure.
    """
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer")
