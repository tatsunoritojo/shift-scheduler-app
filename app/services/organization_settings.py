"""Organization settings service for level system, overlap check, and min attendance.

These settings live in Organization.settings_json under dedicated keys. This module
handles reading, validation, normalization, and tier lifecycle (deletion with member
cleanup).

Design notes:
- Each setting has an `enabled` flag that doubles as a feature flag.
- When a feature is disabled, consumers should treat the rest of the config as absent.
- Tier keys are stable identifiers (English, snake_case); labels are display names.
- Validation raises ValueError; callers are expected to catch and translate to HTTP 400.
"""

import logging
import re

from app.extensions import db
from app.models.membership import OrganizationMember

logger = logging.getLogger(__name__)


# ---------- Setting keys ----------

KEY_LEVEL_SYSTEM = 'level_system'
KEY_OVERLAP_CHECK = 'overlap_check'
KEY_MIN_ATTENDANCE = 'min_attendance'

# ---------- Defaults ----------

DEFAULT_LEVEL_SYSTEM = {
    'enabled': False,
    'tiers': [],
}

DEFAULT_OVERLAP_CHECK = {
    'enabled': False,
    'scope': 'same_tier',
}

DEFAULT_MIN_ATTENDANCE = {
    'mode': 'disabled',            # disabled | org_wide | per_member
    'unit': 'count',               # count | hours | both
    'org_wide_count_per_week': 1,
    'org_wide_hours_per_week': 8.0,
    'count_drafts': True,
    'lookback_periods': 1,
}

# Allowed values (for validation)
_MIN_ATTENDANCE_MODES = {'disabled', 'org_wide', 'per_member'}
_MIN_ATTENDANCE_UNITS = {'count', 'hours', 'both'}
_OVERLAP_SCOPES = {'same_tier'}

# Tier key: 1-32 chars, lowercase alphanumeric + underscore, must start with letter
_TIER_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


# ---------- Level system ----------

def get_level_system(org) -> dict:
    """Return the level system config, merged with defaults."""
    raw = org.get_setting(KEY_LEVEL_SYSTEM) or {}
    return _merge_with_defaults(raw, DEFAULT_LEVEL_SYSTEM)


def set_level_system(org, data: dict, removed_tier_keys=None) -> dict:
    """Persist level system config after validation.

    If removed_tier_keys is provided, members using those tiers will have
    their level_key cleared (set to NULL). Callers must confirm removal
    before passing this argument.

    Raises ValueError if validation fails or an in-use tier is removed
    without being in removed_tier_keys.
    """
    removed_tier_keys = set(removed_tier_keys or [])
    normalized = _validate_level_system(data)

    current = get_level_system(org)
    current_keys = {t['key'] for t in current.get('tiers', [])}
    new_keys = {t['key'] for t in normalized['tiers']}
    disappeared = current_keys - new_keys

    unauthorized_removals = disappeared - removed_tier_keys
    for key in unauthorized_removals:
        in_use = count_members_using_tier(org, key)
        if in_use > 0:
            raise ValueError(
                f"tier '{key}' is used by {in_use} member(s); "
                f"include it in removed_tier_keys to confirm removal"
            )

    # Persist first, then clear members for removed tiers.
    org.set_setting(KEY_LEVEL_SYSTEM, normalized)
    for key in disappeared:
        clear_tier_from_members(org, key)

    return normalized


def count_members_using_tier(org, tier_key) -> int:
    """Count active members whose level_key matches."""
    return OrganizationMember.query.filter_by(
        organization_id=org.id,
        level_key=tier_key,
        is_active=True,
    ).count()


def clear_tier_from_members(org, tier_key) -> int:
    """Set level_key = NULL for all members currently assigned to this tier.

    Returns the number of rows updated.
    """
    updated = OrganizationMember.query.filter_by(
        organization_id=org.id,
        level_key=tier_key,
    ).update({'level_key': None})
    return updated


# ---------- Overlap check ----------

def get_overlap_check(org) -> dict:
    raw = org.get_setting(KEY_OVERLAP_CHECK) or {}
    return _merge_with_defaults(raw, DEFAULT_OVERLAP_CHECK)


def set_overlap_check(org, data: dict) -> dict:
    normalized = _validate_overlap_check(data)
    org.set_setting(KEY_OVERLAP_CHECK, normalized)
    return normalized


# ---------- Min attendance ----------

def get_min_attendance(org) -> dict:
    raw = org.get_setting(KEY_MIN_ATTENDANCE) or {}
    return _merge_with_defaults(raw, DEFAULT_MIN_ATTENDANCE)


def set_min_attendance(org, data: dict) -> dict:
    normalized = _validate_min_attendance(data)
    org.set_setting(KEY_MIN_ATTENDANCE, normalized)
    return normalized


# ---------- Validation ----------

def _validate_level_system(data) -> dict:
    if not isinstance(data, dict):
        raise ValueError('level_system must be an object')

    enabled = data.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('level_system.enabled must be a boolean')

    raw_tiers = data.get('tiers', [])
    if not isinstance(raw_tiers, list):
        raise ValueError('level_system.tiers must be a list')

    seen_keys = set()
    normalized_tiers = []
    for i, tier in enumerate(raw_tiers):
        if not isinstance(tier, dict):
            raise ValueError(f'tiers[{i}] must be an object')

        key = tier.get('key')
        label = tier.get('label')
        order = tier.get('order', i + 1)

        if not isinstance(key, str) or not _TIER_KEY_PATTERN.match(key):
            raise ValueError(
                f'tiers[{i}].key must be 1-32 chars of lowercase letters, '
                f'digits, underscores, starting with a letter'
            )
        if key in seen_keys:
            raise ValueError(f'duplicate tier key: {key}')
        seen_keys.add(key)

        if not isinstance(label, str) or not (1 <= len(label) <= 64):
            raise ValueError(f'tiers[{i}].label must be 1-64 chars')

        if not isinstance(order, int):
            raise ValueError(f'tiers[{i}].order must be an integer')

        normalized_tiers.append({
            'key': key,
            'label': label.strip(),
            'order': order,
        })

    normalized_tiers.sort(key=lambda t: t['order'])
    # Reassign orders to 1..N for stability
    for i, t in enumerate(normalized_tiers):
        t['order'] = i + 1

    return {'enabled': enabled, 'tiers': normalized_tiers}


def _validate_overlap_check(data) -> dict:
    if not isinstance(data, dict):
        raise ValueError('overlap_check must be an object')

    enabled = data.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('overlap_check.enabled must be a boolean')

    scope = data.get('scope', 'same_tier')
    if scope not in _OVERLAP_SCOPES:
        raise ValueError(f'overlap_check.scope must be one of {sorted(_OVERLAP_SCOPES)}')

    return {'enabled': enabled, 'scope': scope}


def _validate_min_attendance(data) -> dict:
    if not isinstance(data, dict):
        raise ValueError('min_attendance must be an object')

    mode = data.get('mode', 'disabled')
    if mode not in _MIN_ATTENDANCE_MODES:
        raise ValueError(f'min_attendance.mode must be one of {sorted(_MIN_ATTENDANCE_MODES)}')

    unit = data.get('unit', 'count')
    if unit not in _MIN_ATTENDANCE_UNITS:
        raise ValueError(f'min_attendance.unit must be one of {sorted(_MIN_ATTENDANCE_UNITS)}')

    count_per_week = data.get('org_wide_count_per_week', 1)
    if not isinstance(count_per_week, int) or isinstance(count_per_week, bool) or count_per_week < 0:
        raise ValueError('min_attendance.org_wide_count_per_week must be a non-negative integer')

    hours_per_week = data.get('org_wide_hours_per_week', 8.0)
    if isinstance(hours_per_week, bool) or not isinstance(hours_per_week, (int, float)):
        raise ValueError('min_attendance.org_wide_hours_per_week must be a number')
    hours_per_week = float(hours_per_week)
    if hours_per_week < 0:
        raise ValueError('min_attendance.org_wide_hours_per_week must be non-negative')

    count_drafts = data.get('count_drafts', True)
    if not isinstance(count_drafts, bool):
        raise ValueError('min_attendance.count_drafts must be a boolean')

    lookback = data.get('lookback_periods', 1)
    if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 0 or lookback > 4:
        raise ValueError('min_attendance.lookback_periods must be an integer in [0, 4]')

    return {
        'mode': mode,
        'unit': unit,
        'org_wide_count_per_week': count_per_week,
        'org_wide_hours_per_week': hours_per_week,
        'count_drafts': count_drafts,
        'lookback_periods': lookback,
    }


# ---------- Internal helpers ----------

def _merge_with_defaults(raw: dict, defaults: dict) -> dict:
    """Shallow merge: missing keys filled from defaults."""
    if not isinstance(raw, dict):
        return dict(defaults)
    merged = dict(defaults)
    merged.update({k: v for k, v in raw.items() if k in defaults})
    return merged
