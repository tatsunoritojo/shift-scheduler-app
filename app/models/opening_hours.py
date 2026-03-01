from datetime import datetime
from app.extensions import db


class OpeningHours(db.Model):
    __tablename__ = 'opening_hours'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Sunday, 6=Saturday
    start_time = db.Column(db.String(5), nullable=False)  # HH:MM
    end_time = db.Column(db.String(5), nullable=False)    # HH:MM
    is_closed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('organization_id', 'day_of_week', name='uq_opening_hours_org_day'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'day_of_week': self.day_of_week,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'is_closed': self.is_closed,
        }

    def __repr__(self):
        return f'<OpeningHours day={self.day_of_week}>'


class OpeningHoursException(db.Model):
    __tablename__ = 'opening_hours_exceptions'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    exception_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=True)   # HH:MM, null if closed
    end_time = db.Column(db.String(5), nullable=True)     # HH:MM, null if closed
    is_closed = db.Column(db.Boolean, default=False, nullable=False)
    reason = db.Column(db.String(255))
    source = db.Column(db.String(20), default='manual')  # 'manual' or 'calendar'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('organization_id', 'exception_date', name='uq_exception_org_date'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'exception_date': self.exception_date.isoformat() if self.exception_date else None,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'is_closed': self.is_closed,
            'reason': self.reason,
            'source': self.source,
        }

    def __repr__(self):
        return f'<OpeningHoursException {self.exception_date}>'


class OpeningHoursCalendarSync(db.Model):
    __tablename__ = 'opening_hours_calendar_sync'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    sync_date = db.Column(db.Date, nullable=False)
    calendar_event_id = db.Column(db.String(255), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)  # HH:MM
    end_time = db.Column(db.String(5), nullable=False)     # HH:MM
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('organization_id', 'sync_date', name='uq_calendar_sync_org_date'),
    )

    def __repr__(self):
        return f'<OpeningHoursCalendarSync {self.sync_date}>'


class SyncOperationLog(db.Model):
    __tablename__ = 'sync_operation_logs'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    operation_type = db.Column(db.String(10), nullable=False)  # 'import' or 'export'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    result_summary = db.Column(db.JSON)
    performed_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'operation_type': self.operation_type,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'result_summary': self.result_summary,
            'performed_at': self.performed_at.isoformat() if self.performed_at else None,
        }

    def __repr__(self):
        return f'<SyncOperationLog {self.operation_type} {self.performed_at}>'
