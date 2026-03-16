from datetime import datetime
from app.extensions import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    display_name = db.Column(db.String(255))
    role = db.Column(db.String(20), nullable=False, default='worker')
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    token = db.relationship('UserToken', backref='user', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.email} ({self.role})>'


class LinkedCalendarAccount(db.Model):
    """Secondary Google account linked for read-only calendar access."""
    __tablename__ = 'linked_calendar_accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    google_email = db.Column(db.String(255), nullable=False)
    google_sub = db.Column(db.String(255), nullable=False)
    refresh_token = db.Column(db.String(512), nullable=False)  # Encrypted
    scopes = db.Column(db.Text, nullable=True)
    label = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('linked_calendars', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'google_sub', name='uq_linked_cal_user_google'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'google_email': self.google_email,
            'label': self.label,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<LinkedCalendarAccount user_id={self.user_id} email={self.google_email}>'


class UserToken(db.Model):
    __tablename__ = 'user_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    refresh_token = db.Column(db.String(512), nullable=False)
    scopes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<UserToken user_id={self.user_id}>'
