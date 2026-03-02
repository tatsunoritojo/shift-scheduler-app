from datetime import datetime
from app.extensions import db


class Reminder(db.Model):
    __tablename__ = 'reminders'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    reminder_type = db.Column(db.String(30), nullable=False)  # 'submission_deadline' | 'preshift'
    reference_id = db.Column(db.Integer, nullable=False)  # shift_period_id or schedule_entry_id
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint('reminder_type', 'reference_id', 'user_id',
                            name='uq_reminder_type_ref_user'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'reminder_type': self.reminder_type,
            'reference_id': self.reference_id,
            'user_id': self.user_id,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<Reminder {self.reminder_type} ref={self.reference_id} user={self.user_id}>'
