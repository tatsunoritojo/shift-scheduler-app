from datetime import datetime
from app.extensions import db


class VacancyRequest(db.Model):
    __tablename__ = 'vacancy_requests'

    id = db.Column(db.Integer, primary_key=True)
    schedule_entry_id = db.Column(db.Integer, db.ForeignKey('shift_schedule_entries.id'), nullable=False)
    original_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='open')
    # open → notified → accepted / expired / cancelled
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    accepted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    schedule_entry = db.relationship('ShiftScheduleEntry', foreign_keys=[schedule_entry_id])
    original_user = db.relationship('User', foreign_keys=[original_user_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    acceptor = db.relationship('User', foreign_keys=[accepted_by])
    candidates = db.relationship('VacancyCandidate', backref='vacancy_request', lazy='dynamic',
                                 cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'schedule_entry_id': self.schedule_entry_id,
            'original_user_id': self.original_user_id,
            'original_user_name': self.original_user.display_name if self.original_user else None,
            'reason': self.reason,
            'status': self.status,
            'created_by': self.created_by,
            'accepted_by': self.accepted_by,
            'accepted_by_name': self.acceptor.display_name if self.acceptor else None,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'shift_date': self.schedule_entry.shift_date.isoformat() if self.schedule_entry else None,
            'start_time': self.schedule_entry.start_time if self.schedule_entry else None,
            'end_time': self.schedule_entry.end_time if self.schedule_entry else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class VacancyCandidate(db.Model):
    __tablename__ = 'vacancy_candidates'

    id = db.Column(db.Integer, primary_key=True)
    vacancy_request_id = db.Column(db.Integer, db.ForeignKey('vacancy_requests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    # pending → notified → accepted / declined / expired
    response_token = db.Column(db.String(512), unique=True, nullable=True)
    notified_at = db.Column(db.DateTime, nullable=True)
    responded_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint('vacancy_request_id', 'user_id', name='uq_vacancy_candidate_request_user'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'vacancy_request_id': self.vacancy_request_id,
            'user_id': self.user_id,
            'user_name': self.user.display_name if self.user else None,
            'user_email': self.user.email if self.user else None,
            'status': self.status,
            'notified_at': self.notified_at.isoformat() if self.notified_at else None,
            'responded_at': self.responded_at.isoformat() if self.responded_at else None,
        }


class ShiftChangeLog(db.Model):
    __tablename__ = 'shift_change_logs'

    id = db.Column(db.Integer, primary_key=True)
    schedule_entry_id = db.Column(db.Integer, db.ForeignKey('shift_schedule_entries.id'), nullable=False)
    vacancy_request_id = db.Column(db.Integer, db.ForeignKey('vacancy_requests.id'), nullable=True)
    change_type = db.Column(db.String(30), nullable=False)  # vacancy_fill
    original_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    new_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    performed_at = db.Column(db.DateTime, default=datetime.utcnow)

    schedule_entry = db.relationship('ShiftScheduleEntry', foreign_keys=[schedule_entry_id])
    vacancy_request = db.relationship('VacancyRequest', foreign_keys=[vacancy_request_id])
    original_user = db.relationship('User', foreign_keys=[original_user_id])
    new_user = db.relationship('User', foreign_keys=[new_user_id])
    performer = db.relationship('User', foreign_keys=[performed_by])

    def to_dict(self):
        return {
            'id': self.id,
            'schedule_entry_id': self.schedule_entry_id,
            'vacancy_request_id': self.vacancy_request_id,
            'change_type': self.change_type,
            'original_user_id': self.original_user_id,
            'original_user_name': self.original_user.display_name if self.original_user else None,
            'new_user_id': self.new_user_id,
            'new_user_name': self.new_user.display_name if self.new_user else None,
            'reason': self.reason,
            'performed_by': self.performed_by,
            'performed_by_name': self.performer.display_name if self.performer else None,
            'shift_date': self.schedule_entry.shift_date.isoformat() if self.schedule_entry else None,
            'performed_at': self.performed_at.isoformat() if self.performed_at else None,
        }
