"""Integration tests for Phase A settings API endpoints."""

import pytest

from app.models.membership import OrganizationMember


# ---------------------------------------------------------------------------
# Level Settings
# ---------------------------------------------------------------------------

class TestLevelSettingsAuth:

    def test_worker_forbidden(self, client, auth, worker_user, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.get('/api/admin/settings/levels')
        assert resp.status_code == 403

    def test_owner_forbidden(self, client, auth, owner_user, db_session):
        db_session.commit()
        auth.login_as(owner_user)
        resp = client.get('/api/admin/settings/levels')
        assert resp.status_code == 403


class TestLevelSettings:

    def test_get_defaults(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/settings/levels')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is False
        assert data['tiers'] == []

    def test_put_and_persist(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/settings/levels', json={
            'enabled': True,
            'tiers': [
                {'key': 'senior', 'label': 'シニア', 'order': 1},
                {'key': 'junior', 'label': 'ジュニア', 'order': 2},
            ],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['enabled'] is True
        assert len(data['tiers']) == 2
        # member_count helper included
        assert 'member_count' in data['tiers'][0]

        # Reload and verify persistence
        resp2 = client.get('/api/admin/settings/levels')
        data2 = resp2.get_json()
        assert data2['enabled'] is True
        assert [t['key'] for t in data2['tiers']] == ['senior', 'junior']

    def test_invalid_key_rejected(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/settings/levels', json={
            'enabled': True,
            'tiers': [{'key': 'Bad Key!', 'label': 'Bad'}],
        })
        assert resp.status_code == 400

    def test_delete_in_use_tier_conflict(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        # Setup tier + assign member
        client.put('/api/admin/settings/levels', json={
            'enabled': True,
            'tiers': [{'key': 'senior', 'label': 'シニア', 'order': 1}],
        })
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        client.put(f'/api/admin/members/{member.id}/attributes', json={'level_key': 'senior'})

        # Attempt to remove tier without consent
        resp = client.put('/api/admin/settings/levels', json={
            'enabled': True,
            'tiers': [],
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['code'] == 'TIER_IN_USE'
        assert data['tiers_in_use']['senior'] == 1

    def test_delete_in_use_tier_with_consent(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.put('/api/admin/settings/levels', json={
            'enabled': True,
            'tiers': [{'key': 'senior', 'label': 'シニア', 'order': 1}],
        })
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        client.put(f'/api/admin/members/{member.id}/attributes', json={'level_key': 'senior'})

        resp = client.put('/api/admin/settings/levels', json={
            'enabled': True,
            'tiers': [],
            'removed_tier_keys': ['senior'],
        })
        assert resp.status_code == 200

        # Member's level_key is cleared
        updated = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        assert updated.level_key is None


# ---------------------------------------------------------------------------
# Overlap Check Settings
# ---------------------------------------------------------------------------

class TestOverlapCheck:

    def test_get_defaults(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/settings/overlap-check')
        assert resp.status_code == 200
        assert resp.get_json() == {'enabled': False, 'scope': 'same_tier'}

    def test_toggle(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/settings/overlap-check', json={
            'enabled': True, 'scope': 'same_tier',
        })
        assert resp.status_code == 200
        assert resp.get_json()['enabled'] is True


# ---------------------------------------------------------------------------
# Min Attendance Settings
# ---------------------------------------------------------------------------

class TestMinAttendance:

    def test_get_defaults(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/settings/min-attendance')
        data = resp.get_json()
        assert data['mode'] == 'disabled'
        assert data['unit'] == 'count'

    def test_put_org_wide(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/settings/min-attendance', json={
            'mode': 'org_wide', 'unit': 'both',
            'org_wide_count_per_week': 2, 'org_wide_hours_per_week': 10.0,
            'count_drafts': False, 'lookback_periods': 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['mode'] == 'org_wide'
        assert data['unit'] == 'both'
        assert data['org_wide_count_per_week'] == 2

    def test_invalid_mode(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/settings/min-attendance', json={'mode': 'bogus'})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Member Attributes
# ---------------------------------------------------------------------------

class TestMemberAttributes:

    def _setup_with_tier(self, client):
        client.put('/api/admin/settings/levels', json={
            'enabled': True,
            'tiers': [{'key': 'senior', 'label': 'シニア', 'order': 1}],
        })

    def test_set_level_key(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        self._setup_with_tier(client)
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        resp = client.put(f'/api/admin/members/{member.id}/attributes', json={
            'level_key': 'senior',
        })
        assert resp.status_code == 200
        assert resp.get_json()['level_key'] == 'senior'

    def test_invalid_level_key_rejected(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        self._setup_with_tier(client)
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        resp = client.put(f'/api/admin/members/{member.id}/attributes', json={
            'level_key': 'nonexistent',
        })
        assert resp.status_code == 400

    def test_clear_level_key(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        self._setup_with_tier(client)
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        client.put(f'/api/admin/members/{member.id}/attributes', json={'level_key': 'senior'})
        resp = client.put(f'/api/admin/members/{member.id}/attributes', json={'level_key': None})
        assert resp.status_code == 200
        assert resp.get_json()['level_key'] is None

    def test_set_min_attendance_values(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        resp = client.put(f'/api/admin/members/{member.id}/attributes', json={
            'min_attendance_count_per_week': 3,
            'min_attendance_hours_per_week': 12.5,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['min_attendance_count_per_week'] == 3
        assert data['min_attendance_hours_per_week'] == 12.5

    def test_negative_count_rejected(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        member = OrganizationMember.query.filter_by(user_id=admin_user.id).first()
        resp = client.put(f'/api/admin/members/{member.id}/attributes', json={
            'min_attendance_count_per_week': -1,
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DTO compatibility (backwards-compatible extension)
# ---------------------------------------------------------------------------

class TestMemberDTO:

    def test_members_list_includes_new_fields(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/members')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 1
        m = data[0]
        assert 'level_key' in m
        assert 'min_attendance_count_per_week' in m
        assert 'min_attendance_hours_per_week' in m
        # Existing fields still present (backwards compat)
        assert 'role' in m
        assert 'user_email' in m
