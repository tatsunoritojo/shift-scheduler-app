from datetime import datetime
from app.extensions import db


class ShiftPeriod(db.Model):
    __tablename__ = 'shift_periods'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    submission_deadline = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='draft')  # draft, open, closed, finalized
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by])
    submissions = db.relationship('ShiftSubmission', backref='period', lazy='dynamic',
                                  cascade='all, delete-orphan')
    schedules = db.relationship('ShiftSchedule', backref='period', lazy='dynamic',
                                cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'submission_deadline': self.submission_deadline.isoformat() if self.submission_deadline else None,
            'status': self.status,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<ShiftPeriod {self.name}>'


class ShiftSubmission(db.Model):
    __tablename__ = 'shift_submissions'

    id = db.Column(db.Integer, primary_key=True)
    shift_period_id = db.Column(db.Integer, db.ForeignKey('shift_periods.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='draft')  # draft, submitted, revised
    submitted_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    slots = db.relationship('ShiftSubmissionSlot', backref='submission', lazy='dynamic',
                            cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('shift_period_id', 'user_id', name='uq_submission_period_user'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'shift_period_id': self.shift_period_id,
            'user_id': self.user_id,
            'user_name': self.user.display_name if self.user else None,
            'user_email': self.user.email if self.user else None,
            'status': self.status,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'notes': self.notes,
        }

    def __repr__(self):
        return f'<ShiftSubmission period={self.shift_period_id} user={self.user_id}>'


class ShiftSubmissionSlot(db.Model):
    __tablename__ = 'shift_submission_slots'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('shift_submissions.id'), nullable=False)
    slot_date = db.Column(db.Date, nullable=False)
    is_available = db.Column(db.Boolean, nullable=False, default=False)
    start_time = db.Column(db.String(5), nullable=True)  # HH:MM
    end_time = db.Column(db.String(5), nullable=True)    # HH:MM
    is_custom_time = db.Column(db.Boolean, default=False)
    auto_calculated_start = db.Column(db.String(5), nullable=True)
    auto_calculated_end = db.Column(db.String(5), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'slot_date': self.slot_date.isoformat(),
            'is_available': self.is_available,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'is_custom_time': self.is_custom_time,
            'auto_calculated_start': self.auto_calculated_start,
            'auto_calculated_end': self.auto_calculated_end,
            'notes': self.notes,
        }

    def __repr__(self):
        return f'<ShiftSubmissionSlot {self.slot_date}>'


class ShiftSchedule(db.Model):
    __tablename__ = 'shift_schedules'

    id = db.Column(db.Integer, primary_key=True)
    shift_period_id = db.Column(db.Integer, db.ForeignKey('shift_periods.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='draft')
    # draft, pending_approval, approved, rejected, confirmed
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', foreign_keys=[created_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    entries = db.relationship('ShiftScheduleEntry', backref='schedule', lazy='dynamic',
                              cascade='all, delete-orphan')
    history = db.relationship('ApprovalHistory', backref='schedule', lazy='dynamic',
                              cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'shift_period_id': self.shift_period_id,
            'status': self.status,
            'created_by': self.created_by,
            'approved_by': self.approved_by,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'confirmed_at': self.confirmed_at.isoformat() if self.confirmed_at else None,
            'rejection_reason': self.rejection_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<ShiftSchedule period={self.shift_period_id} status={self.status}>'


class ShiftScheduleEntry(db.Model):
    __tablename__ = 'shift_schedule_entries'

    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('shift_schedules.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shift_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)  # HH:MM
    end_time = db.Column(db.String(5), nullable=False)    # HH:MM
    calendar_event_id = db.Column(db.String(255), nullable=True)
    synced_at = db.Column(db.DateTime, nullable=True)
    sync_error = db.Column(db.String(50), nullable=True)
    last_sync_attempt_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    @property
    def is_synced(self):
        return self.calendar_event_id is not None

    @property
    def can_sync(self):
        return not self.is_synced

    def get_sync_status(self):
        """Derive sync status from persisted fields.

        Returns one of: 'synced', 'reauth_required', 'failed', 'pending'.
        """
        if self.is_synced:
            return 'synced'
        if self.sync_error in ('CREDENTIALS_EXPIRED', 'NO_CREDENTIALS'):
            return 'reauth_required'
        if self.sync_error is not None:
            return 'failed'
        return 'pending'

    def to_dict(self):
        return {
            'id': self.id,
            'schedule_id': self.schedule_id,
            'user_id': self.user_id,
            'user_name': self.user.display_name if self.user else None,
            'shift_date': self.shift_date.isoformat(),
            'start_time': self.start_time,
            'end_time': self.end_time,
            'calendar_event_id': self.calendar_event_id,
            'synced_at': self.synced_at.isoformat() if self.synced_at else None,
            'sync_error': self.sync_error,
            'last_sync_attempt_at': self.last_sync_attempt_at.isoformat() if self.last_sync_attempt_at else None,
        }

    def __repr__(self):
        return f'<ShiftScheduleEntry {self.shift_date} user={self.user_id}>'
