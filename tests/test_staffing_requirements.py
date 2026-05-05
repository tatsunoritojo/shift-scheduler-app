"""Integration tests for the StaffingRequirement API (Phase 2a-3 D)."""

from app.models.staffing import StaffingRequirement


# ---------------------------------------------------------------------------
# 認可
# ---------------------------------------------------------------------------

class TestStaffingRequirementsAuth:

    def test_worker_forbidden_get(self, client, auth, worker_user, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.get('/api/admin/staffing-requirements')
        assert resp.status_code == 403

    def test_worker_forbidden_put(self, client, auth, worker_user, db_session):
        db_session.commit()
        auth.login_as(worker_user)
        resp = client.put('/api/admin/staffing-requirements', json={'items': []})
        assert resp.status_code == 403

    def test_owner_forbidden(self, client, auth, owner_user, db_session):
        db_session.commit()
        auth.login_as(owner_user)
        resp = client.get('/api/admin/staffing-requirements')
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self, client, db_session):
        db_session.commit()
        resp = client.get('/api/admin/staffing-requirements')
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 基本 CRUD
# ---------------------------------------------------------------------------

class TestStaffingRequirementsBasic:

    def test_get_empty_initially(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.get('/api/admin/staffing-requirements')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_put_single_item(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '13:00', 'required_count': 2},
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['day_of_week'] == 1
        assert data[0]['start_time'] == '09:00'
        assert data[0]['required_count'] == 2

    def test_put_multiple_slots_same_day(self, client, auth, admin_user, db_session):
        """同じ曜日に複数の時間帯スロットを許可する（時間帯分割）。"""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '13:00', 'required_count': 2},
                {'day_of_week': 1, 'start_time': '13:00', 'end_time': '17:00', 'required_count': 3},
                {'day_of_week': 1, 'start_time': '17:00', 'end_time': '22:00', 'required_count': 2},
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3
        # 時刻順に返される
        assert data[0]['start_time'] == '09:00'
        assert data[1]['start_time'] == '13:00'
        assert data[2]['start_time'] == '17:00'

    def test_put_replaces_existing(self, client, auth, admin_user, db_session):
        """PUT は一括 upsert: 既存全削除 → 新規 insert。"""
        db_session.commit()
        auth.login_as(admin_user)
        # 1 回目
        client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 3},
                {'day_of_week': 2, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 2},
            ]
        })
        # 2 回目（上書き）
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 3, 'start_time': '10:00', 'end_time': '20:00', 'required_count': 4},
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['day_of_week'] == 3

    def test_get_returns_sorted_by_day_then_time(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 3, 'start_time': '13:00', 'end_time': '17:00', 'required_count': 2},
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '13:00', 'required_count': 2},
                {'day_of_week': 1, 'start_time': '13:00', 'end_time': '17:00', 'required_count': 3},
            ]
        })
        resp = client.get('/api/admin/staffing-requirements')
        data = resp.get_json()
        assert [(d['day_of_week'], d['start_time']) for d in data] == [
            (1, '09:00'), (1, '13:00'), (3, '13:00')
        ]

    def test_put_can_clear_all(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 2},
            ]
        })
        resp = client.put('/api/admin/staffing-requirements', json={'items': []})
        assert resp.status_code == 200
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------

class TestStaffingRequirementsValidation:

    def test_missing_items_returns_400(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'VALIDATION_ERROR'

    def test_items_not_list(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={'items': 'not-a-list'})
        assert resp.status_code == 400

    def test_invalid_day_of_week(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        for invalid_day in [-1, 7, 'Monday', None]:
            resp = client.put('/api/admin/staffing-requirements', json={
                'items': [
                    {'day_of_week': invalid_day, 'start_time': '09:00',
                     'end_time': '17:00', 'required_count': 2}
                ]
            })
            assert resp.status_code == 400, f"day_of_week={invalid_day!r} should be rejected"

    def test_invalid_time_format(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '9:00', 'end_time': '17:00', 'required_count': 2}
            ]
        })
        assert resp.status_code == 400

    def test_start_must_precede_end(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '17:00', 'end_time': '09:00', 'required_count': 2}
            ]
        })
        assert resp.status_code == 400

    def test_negative_required_count(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': -1}
            ]
        })
        assert resp.status_code == 400

    def test_required_count_zero_is_allowed(self, client, auth, admin_user, db_session):
        """0 名は許可（その時間帯は無人運用、明示的にゼロを置きたい）。"""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 0}
            ]
        })
        assert resp.status_code == 200

    def test_required_count_too_large(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 1000}
            ]
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# マルチテナント分離
# ---------------------------------------------------------------------------

class TestStaffingRequirementsTenantIsolation:

    def test_different_orgs_isolated(self, client, auth, db_session):
        from tests.conftest import _make_org, _make_user
        org_a = _make_org(db_session, name="Org A")
        org_b = _make_org(db_session, name="Org B")
        admin_a = _make_user(db_session, org_a, email="a@x.com", role="admin")
        admin_b = _make_user(db_session, org_b, email="b@x.com", role="admin")
        db_session.commit()

        # admin_a が org_a に設定
        auth.login_as(admin_a)
        client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 5}
            ]
        })

        # admin_b は自組織を見る → org_a の設定は見えない
        auth.login_as(admin_b)
        resp = client.get('/api/admin/staffing-requirements')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_orgs_can_have_independent_settings(self, client, auth, db_session):
        from tests.conftest import _make_org, _make_user
        org_a = _make_org(db_session, name="Org A")
        org_b = _make_org(db_session, name="Org B")
        admin_a = _make_user(db_session, org_a, email="a@x.com", role="admin")
        admin_b = _make_user(db_session, org_b, email="b@x.com", role="admin")
        db_session.commit()

        auth.login_as(admin_a)
        client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 2}
            ]
        })
        auth.login_as(admin_b)
        client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 2, 'start_time': '10:00', 'end_time': '20:00', 'required_count': 5}
            ]
        })

        # それぞれ独立して保持
        auth.login_as(admin_a)
        data_a = client.get('/api/admin/staffing-requirements').get_json()
        assert len(data_a) == 1 and data_a[0]['day_of_week'] == 1

        auth.login_as(admin_b)
        data_b = client.get('/api/admin/staffing-requirements').get_json()
        assert len(data_b) == 1 and data_b[0]['day_of_week'] == 2


# ---------------------------------------------------------------------------
# 監査ログ (audit_log)
# ---------------------------------------------------------------------------

class TestStaffingRequirementsAudit:

    def test_update_writes_audit_log(self, client, auth, admin_user, db_session):
        from app.models.audit_log import AuditLog
        db_session.commit()
        auth.login_as(admin_user)
        client.put('/api/admin/staffing-requirements', json={
            'items': [
                {'day_of_week': 1, 'start_time': '09:00', 'end_time': '17:00', 'required_count': 2}
            ]
        })
        log = AuditLog.query.filter_by(action='STAFFING_REQUIREMENTS_UPDATED').first()
        assert log is not None
        assert log.actor_id == admin_user.id
