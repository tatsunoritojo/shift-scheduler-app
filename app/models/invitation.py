import secrets
from datetime import datetime, timedelta
from app.extensions import db


class Invitation(db.Model):
    __tablename__ = 'invitations'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    invite_type = db.Column(db.String(20), nullable=False)  # 'email' or 'link'
    token = db.Column(db.String(512), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    invited_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    accepted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = db.relationship('Organization', backref=db.backref('invitations', lazy='dynamic'))
    inviter = db.relationship('User', foreign_keys=[invited_by])
    accepter = db.relationship('User', foreign_keys=[accepted_by])

    __table_args__ = (
        db.Index('ix_invitation_token', 'token'),
        db.Index('ix_invitation_email_org', 'email', 'organization_id'),
    )

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'email': self.email,
            'invite_type': self.invite_type,
            'status': self.status,
            'invited_by': self.invited_by,
            'inviter_name': self.inviter.display_name if self.inviter else None,
            'accepted_by': self.accepted_by,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<Invitation {self.id} type={self.invite_type} status={self.status}>'
