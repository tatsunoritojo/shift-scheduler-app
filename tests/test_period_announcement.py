"""期間公開メール通知 + 募集文面フィールドのテスト (Phase 2a-3 B)."""

from datetime import date
from unittest.mock import patch

from app.extensions import db
from app.models.shift import ShiftPeriod
from app.models.membership import OrganizationMember
from tests.conftest import _make_user


# ---------------------------------------------------------------------------
# 募集文面 (announcement_text) の保存・編集
# ---------------------------------------------------------------------------

class TestAnnouncementText:

    def test_create_period_saves_announcement_text(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "May 2026",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "announcement_text": "5月のシフト募集です。よろしくお願いします。",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["announcement_text"] == "5月のシフト募集です。よろしくお願いします。"

    def test_create_period_without_announcement_text(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "May 2026",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
        })
        assert resp.status_code == 201
        assert resp.get_json()["announcement_text"] is None

    def test_create_period_announcement_text_too_long(self, client, auth, admin_user, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "May 2026",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "announcement_text": "x" * 4001,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_update_period_edits_announcement_text(self, client, auth, admin_user, period, db_session):
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/periods/{period.id}", json={
            "announcement_text": "後から追加した文面",
        })
        assert resp.status_code == 200
        assert resp.get_json()["announcement_text"] == "後から追加した文面"

    def test_update_period_can_clear_announcement_text(self, client, auth, admin_user, period, db_session):
        period.announcement_text = "元の文面"
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.put(f"/api/admin/periods/{period.id}", json={
            "announcement_text": None,
        })
        assert resp.status_code == 200
        assert resp.get_json()["announcement_text"] is None


# ---------------------------------------------------------------------------
# status 遷移時の Worker 全員への通知
# ---------------------------------------------------------------------------

class TestPeriodOpenNotification:

    def test_draft_to_open_notifies_active_workers(self, client, auth, admin_user, period, org, db_session):
        # 2 名のアクティブな Worker を組織に追加
        _make_user(db_session, org, email="w1@test.com", role="worker")
        _make_user(db_session, org, email="w2@test.com", role="worker")
        db_session.commit()
        auth.login_as(admin_user)

        with patch("app.blueprints.api_admin.notify_period_open") as mock_notify:
            resp = client.put(f"/api/admin/periods/{period.id}", json={"status": "open"})

        assert resp.status_code == 200
        assert resp.get_json()["notified_count"] == 2
        assert mock_notify.call_count == 2
        emails = {call.args[0] for call in mock_notify.call_args_list}
        assert emails == {"w1@test.com", "w2@test.com"}

    def test_open_to_open_does_not_notify(self, client, auth, admin_user, period, org, db_session):
        _make_user(db_session, org, email="w1@test.com", role="worker")
        period.status = "open"
        db_session.commit()
        auth.login_as(admin_user)

        with patch("app.blueprints.api_admin.notify_period_open") as mock_notify:
            resp = client.put(f"/api/admin/periods/{period.id}", json={"status": "open"})

        assert resp.status_code == 200
        assert resp.get_json()["notified_count"] == 0
        mock_notify.assert_not_called()

    def test_closed_to_open_does_not_notify(self, client, auth, admin_user, period, org, db_session):
        # 「draft → open」のみが新規公開と扱われる。
        # 一度 closed にして再 open するのは「再公開」で、Worker 混乱を避けるため通知しない仕様。
        _make_user(db_session, org, email="w1@test.com", role="worker")
        period.status = "closed"
        db_session.commit()
        auth.login_as(admin_user)

        with patch("app.blueprints.api_admin.notify_period_open") as mock_notify:
            resp = client.put(f"/api/admin/periods/{period.id}", json={"status": "open"})

        assert resp.status_code == 200
        assert resp.get_json()["notified_count"] == 0
        mock_notify.assert_not_called()

    def test_open_skips_inactive_workers(self, client, auth, admin_user, period, org, db_session):
        active = _make_user(db_session, org, email="active@test.com", role="worker")
        inactive = _make_user(db_session, org, email="inactive@test.com", role="worker")
        # OrganizationMember を非アクティブ化
        membership = OrganizationMember.query.filter_by(
            user_id=inactive.id, organization_id=org.id
        ).first()
        membership.is_active = False
        db_session.commit()
        auth.login_as(admin_user)

        with patch("app.blueprints.api_admin.notify_period_open") as mock_notify:
            resp = client.put(f"/api/admin/periods/{period.id}", json={"status": "open"})

        assert resp.status_code == 200
        assert resp.get_json()["notified_count"] == 1
        emails = {call.args[0] for call in mock_notify.call_args_list}
        assert emails == {"active@test.com"}

    def test_open_skips_non_workers(self, client, auth, admin_user, owner_user, period, org, db_session):
        _make_user(db_session, org, email="w1@test.com", role="worker")
        # admin_user, owner_user は worker ではない → 通知対象外
        db_session.commit()
        auth.login_as(admin_user)

        with patch("app.blueprints.api_admin.notify_period_open") as mock_notify:
            resp = client.put(f"/api/admin/periods/{period.id}", json={"status": "open"})

        assert resp.status_code == 200
        assert resp.get_json()["notified_count"] == 1
        emails = {call.args[0] for call in mock_notify.call_args_list}
        assert emails == {"w1@test.com"}

    def test_open_passes_announcement_text_to_notify(self, client, auth, admin_user, period, org, db_session):
        _make_user(db_session, org, email="w1@test.com", role="worker")
        period.announcement_text = "今月もよろしく。"
        db_session.commit()
        auth.login_as(admin_user)

        with patch("app.blueprints.api_admin.notify_period_open") as mock_notify:
            client.put(f"/api/admin/periods/{period.id}", json={"status": "open"})

        assert mock_notify.call_count == 1
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["announcement_text"] == "今月もよろしく。"

    def test_partial_notify_failure_does_not_break_status_change(
        self, client, auth, admin_user, period, org, db_session
    ):
        _make_user(db_session, org, email="w1@test.com", role="worker")
        _make_user(db_session, org, email="w2@test.com", role="worker")
        db_session.commit()
        auth.login_as(admin_user)

        # 1 通目を失敗させる
        def side_effect(email, *args, **kwargs):
            if email == "w1@test.com":
                raise RuntimeError("simulated SMTP failure")
            return True

        with patch("app.blueprints.api_admin.notify_period_open", side_effect=side_effect):
            resp = client.put(f"/api/admin/periods/{period.id}", json={"status": "open"})

        # status 変更は成功、通知は 1 件のみカウント
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "open"
        assert body["notified_count"] == 1

        # DB に反映されているか念のため確認
        refreshed = db.session.get(ShiftPeriod, period.id)
        assert refreshed.status == "open"


# ---------------------------------------------------------------------------
# エッジケース: 入力正規化 / 越境 / 異常系
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_create_period_empty_string_normalized_to_none(self, client, auth, admin_user, db_session):
        """空文字の announcement_text は DB に None として保存される（クリーンネス確保）。"""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "May 2026",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "announcement_text": "",
        })
        assert resp.status_code == 201
        assert resp.get_json()["announcement_text"] is None

    def test_create_period_whitespace_only_normalized_to_none(self, client, auth, admin_user, db_session):
        """空白文字のみの announcement_text も None に正規化される。"""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "May 2026",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "announcement_text": "   \n\t  ",
        })
        assert resp.status_code == 201
        assert resp.get_json()["announcement_text"] is None

    def test_create_period_announcement_text_at_boundary(self, client, auth, admin_user, db_session):
        """4000 文字ピッタリは許可される（境界値）。"""
        db_session.commit()
        auth.login_as(admin_user)
        resp = client.post("/api/admin/periods", json={
            "name": "May 2026",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "announcement_text": "x" * 4000,
        })
        assert resp.status_code == 201
        assert len(resp.get_json()["announcement_text"]) == 4000

    def test_update_period_returns_404_for_other_org(self, client, auth, db_session):
        """他組織の period_id を update しようとすると 404。"""
        from tests.conftest import _make_org
        from datetime import date as _date
        org_a = _make_org(db_session, name="Org A")
        org_b = _make_org(db_session, name="Org B")
        admin_a = _make_user(db_session, org_a, email="a@x.com", role="admin")
        admin_b = _make_user(db_session, org_b, email="b@x.com", role="admin")
        period_a = ShiftPeriod(
            organization_id=org_a.id, name="P", start_date=_date(2026, 5, 1),
            end_date=_date(2026, 5, 31), status="draft", created_by=admin_a.id,
        )
        db_session.add(period_a)
        db_session.commit()
        # admin_b（別組織の admin）が period_a を update しようとする
        auth.login_as(admin_b)
        resp = client.put(f"/api/admin/periods/{period_a.id}", json={
            "announcement_text": "別組織から書き換え",
        })
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"

