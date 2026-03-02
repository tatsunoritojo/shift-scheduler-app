from datetime import datetime
from app.extensions import db


class Organization(db.Model):
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    admin_email = db.Column(db.String(255))
    owner_email = db.Column(db.String(255))
    settings_json = db.Column(db.Text, default='{}')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    invite_code = db.Column(db.String(64), unique=True, nullable=True)
    invite_code_created_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = db.relationship('User', backref='organization', lazy='dynamic')
    opening_hours = db.relationship('OpeningHours', backref='organization', lazy='dynamic',
                                    cascade='all, delete-orphan')
    opening_hours_exceptions = db.relationship('OpeningHoursException', backref='organization',
                                               lazy='dynamic', cascade='all, delete-orphan')
    shift_periods = db.relationship('ShiftPeriod', backref='organization', lazy='dynamic',
                                    cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Organization {self.name}>'
