"""Shared fixtures for the test suite."""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db as _db
from app.models.user import User
from app.models.organization import Organization
from app.models.shift import ShiftPeriod, ShiftSchedule, ShiftScheduleEntry


# ---------------------------------------------------------------------------
# App / DB / Client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Create the Flask application with test config."""
    # Patch notification service globally so SMTP is never attempted
    with patch("app.services.notification_service.send_email"):
        application = create_app("testing")
        yield application


@pytest.fixture(autouse=True)
def _setup_db(app):
    """Create all tables before each test, drop after."""
    with app.app_context():
        _db.create_all()
        yield
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def db_session(app):
    """Provide the SQLAlchemy session inside an app context."""
    with app.app_context():
        yield _db.session


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _make_org(session, name="Test Org"):
    org = Organization(name=name, admin_email="admin@test.com", owner_email="owner@test.com")
    session.add(org)
    session.flush()
    return org


def _make_user(session, org, *, email, role, display_name=None):
    user = User(
        google_id=f"gid_{email}",
        email=email,
        display_name=display_name or email.split("@")[0],
        role=role,
        organization_id=org.id,
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# Ready-made entities
# ---------------------------------------------------------------------------

@pytest.fixture()
def org(db_session):
    return _make_org(db_session)


@pytest.fixture()
def admin_user(db_session, org):
    return _make_user(db_session, org, email="admin@test.com", role="admin")


@pytest.fixture()
def owner_user(db_session, org):
    return _make_user(db_session, org, email="owner@test.com", role="owner")


@pytest.fixture()
def worker_user(db_session, org):
    return _make_user(db_session, org, email="worker@test.com", role="worker")


@pytest.fixture()
def period(db_session, org, admin_user):
    p = ShiftPeriod(
        organization_id=org.id,
        name="March 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        status="draft",
        created_by=admin_user.id,
    )
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture()
def schedule(db_session, period, admin_user):
    s = ShiftSchedule(
        shift_period_id=period.id,
        status="draft",
        created_by=admin_user.id,
    )
    db_session.add(s)
    db_session.flush()
    return s


# ---------------------------------------------------------------------------
# Auth helpers — set session['user_id'] via the test client
# ---------------------------------------------------------------------------

class AuthActions:
    """Helper to authenticate as a specific user in the test client."""

    def __init__(self, client):
        self._client = client

    def login_as(self, user):
        with self._client.session_transaction() as sess:
            sess["user_id"] = user.id


@pytest.fixture()
def auth(client):
    return AuthActions(client)
