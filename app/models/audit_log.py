"""Audit log for security-sensitive operations."""

from datetime import datetime

from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    resource_type = db.Column(db.String(50), nullable=False)
    resource_id = db.Column(db.Integer, nullable=True)
    old_values = db.Column(db.JSON, nullable=True)
    new_values = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    status = db.Column(db.String(10), nullable=False, default='SUCCESS')  # SUCCESS / FAILED
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    actor = db.relationship('User', foreign_keys=[actor_id])

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'actor_id': self.actor_id,
            'actor_name': self.actor.display_name if self.actor else None,
            'actor_email': self.actor.email if self.actor else None,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'old_values': self.old_values,
            'new_values': self.new_values,
            'ip_address': self.ip_address,
            'status': self.status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<AuditLog {self.action} {self.resource_type}:{self.resource_id}>'
