"""Organization membership and invitation models for RBAC."""

import secrets
from datetime import datetime, timedelta

from app.extensions import db


class OrganizationMember(db.Model):
    """Authoritative source for who belongs to which org with what role.

    User.role and User.organization_id are kept in sync as denormalized caches
    so that existing middleware (require_role) continues to work unchanged.
    """
    __tablename__ = 'organization_members'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='worker')  # admin, owner, worker
    invited_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('memberships', lazy='dynamic'))
    organization = db.relationship('Organization', backref=db.backref('members', lazy='dynamic'))
    inviter = db.relationship('User', foreign_keys=[invited_by])

    __table_args__ = (
        db.UniqueConstraint('user_id', 'organization_id', name='uq_member_user_org'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_email': self.user.email if self.user else None,
            'user_name': self.user.display_name if self.user else None,
            'organization_id': self.organization_id,
            'role': self.role,
            'is_active': self.is_active,
            'invited_by': self.invited_by,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
        }

    def sync_to_user(self):
        """Sync this membership's role/org to the User model (denormalized cache)."""
        self.user.role = self.role
        self.user.organization_id = self.organization_id

    def __repr__(self):
        return f'<OrganizationMember user={self.user_id} org={self.organization_id} role={self.role}>'


class InvitationToken(db.Model):
    """Token for inviting users to an organization with a specific role."""
    __tablename__ = 'invitation_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='worker')
    email = db.Column(db.String(255), nullable=True)  # If set, only this email can use the token
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    used_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization')
    creator = db.relationship('User', foreign_keys=[created_by])
    consumer = db.relationship('User', foreign_keys=[used_by])

    @property
    def is_valid(self):
        """Token is valid if unused and not expired."""
        return self.used_at is None and self.expires_at > datetime.utcnow()

    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'organization_id': self.organization_id,
            'role': self.role,
            'email': self.email,
            'is_valid': self.is_valid,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<InvitationToken org={self.organization_id} role={self.role} valid={self.is_valid}>'
