from datetime import datetime
from app.extensions import db


class ApprovalHistory(db.Model):
    __tablename__ = 'approval_history'

    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('shift_schedules.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # submitted, approved, rejected, confirmed
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    performed_at = db.Column(db.DateTime, default=datetime.utcnow)

    performer = db.relationship('User', foreign_keys=[performed_by])

    def to_dict(self):
        return {
            'id': self.id,
            'schedule_id': self.schedule_id,
            'action': self.action,
            'performed_by': self.performed_by,
            'performer_name': self.performer.display_name if self.performer else None,
            'comment': self.comment,
            'performed_at': self.performed_at.isoformat() if self.performed_at else None,
        }

    def __repr__(self):
        return f'<ApprovalHistory {self.action} schedule={self.schedule_id}>'
