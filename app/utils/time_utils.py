from datetime import time


def time_to_minutes(t):
    """Convert a time object or 'HH:MM' string to minutes since midnight."""
    if isinstance(t, str):
        parts = t.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    if isinstance(t, time):
        return t.hour * 60 + t.minute
    return 0


def minutes_to_time_str(minutes):
    """Convert minutes since midnight to 'HH:MM' string."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"
