"""Unit tests for organization_settings service (Phase A)."""

import pytest

from app.models.membership import OrganizationMember
from app.services import organization_settings as org_settings
from tests.conftest import _make_user


class TestDefaults:

    def test_level_system_defaults_when_unset(self, org, db_session):
        cfg = org_settings.get_level_system(org)
        assert cfg == {'enabled': False, 'tiers': []}

    def test_overlap_check_defaults_when_unset(self, org, db_session):
        cfg = org_settings.get_overlap_check(org)
        assert cfg == {'enabled': False, 'scope': 'same_tier'}

    def test_min_attendance_defaults_when_unset(self, org, db_session):
        cfg = org_settings.get_min_attendance(org)
        assert cfg['mode'] == 'disabled'
        assert cfg['unit'] == 'count'
        assert cfg['count_drafts'] is True
        assert cfg['lookback_periods'] == 1


class TestLevelSystem:

    def test_enable_and_add_tiers(self, org, db_session):
        cfg = org_settings.set_level_system(org, {
            'enabled': True,
            'tiers': [
                {'key': 'senior', 'label': 'シニア', 'order': 1},
                {'key': 'junior', 'label': 'ジュニア', 'order': 2},
            ],
        })
        db_session.commit()
        assert cfg['enabled'] is True
        assert len(cfg['tiers']) == 2
        assert cfg['tiers'][0]['key'] == 'senior'
        assert cfg['tiers'][1]['key'] == 'junior'

    def test_tiers_normalized_by_order(self, org, db_session):
        cfg = org_settings.set_level_system(org, {
            'enabled': True,
            'tiers': [
                {'key': 'b', 'label': 'B', 'order': 5},
                {'key': 'a', 'label': 'A', 'order': 1},
            ],
        })
        assert [t['key'] for t in cfg['tiers']] == ['a', 'b']
        # Orders reassigned to 1..N
        assert cfg['tiers'][0]['order'] == 1
        assert cfg['tiers'][1]['order'] == 2

    def test_invalid_key_rejected(self, org, db_session):
        with pytest.raises(ValueError):
            org_settings.set_level_system(org, {
                'enabled': True,
                'tiers': [{'key': 'INVALID KEY', 'label': 'x'}],
            })

    def test_duplicate_keys_rejected(self, org, db_session):
        with pytest.raises(ValueError):
            org_settings.set_level_system(org, {
                'enabled': True,
                'tiers': [
                    {'key': 'a', 'label': 'A'},
                    {'key': 'a', 'label': 'B'},
                ],
            })

    def test_empty_label_rejected(self, org, db_session):
        with pytest.raises(ValueError):
            org_settings.set_level_system(org, {
                'enabled': True,
                'tiers': [{'key': 'senior', 'label': ''}],
            })


class TestTierDeletion:

    def _setup_tiers(self, org, db_session, admin_user):
        org_settings.set_level_system(org, {
            'enabled': True,
            'tiers': [
                {'key': 'senior', 'label': 'シニア', 'order': 1},
                {'key': 'junior', 'label': 'ジュニア', 'order': 2},
            ],
        })
        # Assign a member to the 'senior' tier
        member = OrganizationMember.query.filter_by(
            organization_id=org.id, user_id=admin_user.id,
        ).first()
        member.level_key = 'senior'
        db_session.flush()

    def test_remove_unused_tier_succeeds(self, org, db_session, admin_user):
        self._setup_tiers(org, db_session, admin_user)
        cfg = org_settings.set_level_system(org, {
            'enabled': True,
            'tiers': [{'key': 'senior', 'label': 'シニア', 'order': 1}],
        })  # junior dropped, unused
        assert [t['key'] for t in cfg['tiers']] == ['senior']

    def test_remove_in_use_tier_without_confirmation_fails(self, org, db_session, admin_user):
        self._setup_tiers(org, db_session, admin_user)
        with pytest.raises(ValueError, match='used by'):
            org_settings.set_level_system(org, {
                'enabled': True,
                'tiers': [{'key': 'junior', 'label': 'ジュニア', 'order': 1}],
            })  # senior (in use) dropped without consent

    def test_remove_in_use_tier_with_confirmation_clears_members(self, org, db_session, admin_user):
        self._setup_tiers(org, db_session, admin_user)
        org_settings.set_level_system(org, {
            'enabled': True,
            'tiers': [{'key': 'junior', 'label': 'ジュニア', 'order': 1}],
        }, removed_tier_keys=['senior'])
        db_session.commit()
        member = OrganizationMember.query.filter_by(
            organization_id=org.id, user_id=admin_user.id,
        ).first()
        assert member.level_key is None


class TestOverlapCheck:

    def test_enable_toggle(self, org, db_session):
        cfg = org_settings.set_overlap_check(org, {'enabled': True, 'scope': 'same_tier'})
        assert cfg == {'enabled': True, 'scope': 'same_tier'}

    def test_invalid_scope_rejected(self, org, db_session):
        with pytest.raises(ValueError):
            org_settings.set_overlap_check(org, {'enabled': True, 'scope': 'invalid'})


class TestMinAttendance:

    def test_org_wide_mode(self, org, db_session):
        cfg = org_settings.set_min_attendance(org, {
            'mode': 'org_wide', 'unit': 'count',
            'org_wide_count_per_week': 2, 'org_wide_hours_per_week': 10.0,
            'count_drafts': False, 'lookback_periods': 2,
        })
        assert cfg['mode'] == 'org_wide'
        assert cfg['org_wide_count_per_week'] == 2
        assert cfg['count_drafts'] is False

    def test_both_unit(self, org, db_session):
        cfg = org_settings.set_min_attendance(org, {
            'mode': 'org_wide', 'unit': 'both',
            'org_wide_count_per_week': 1, 'org_wide_hours_per_week': 8.0,
        })
        assert cfg['unit'] == 'both'

    def test_negative_count_rejected(self, org, db_session):
        with pytest.raises(ValueError):
            org_settings.set_min_attendance(org, {
                'mode': 'org_wide', 'unit': 'count',
                'org_wide_count_per_week': -1, 'org_wide_hours_per_week': 0,
            })

    def test_invalid_mode_rejected(self, org, db_session):
        with pytest.raises(ValueError):
            org_settings.set_min_attendance(org, {
                'mode': 'unknown', 'unit': 'count',
            })

    def test_lookback_out_of_range_rejected(self, org, db_session):
        with pytest.raises(ValueError):
            org_settings.set_min_attendance(org, {
                'mode': 'org_wide', 'unit': 'count',
                'lookback_periods': 10,
            })
