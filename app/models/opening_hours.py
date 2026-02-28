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
