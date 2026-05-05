from datetime import datetime
from app.extensions import db


class StaffingRequirement(db.Model):
    """組織ごとの曜日 × 時間帯ごとの必要人数。

    1 つの曜日に複数レコードを許可することで、時間帯分割
    （例: 月曜 09-13 で 2 名、月曜 13-22 で 3 名）を表現する。
    OpeningHours は曜日ごとに単一の時間帯しか持たないが、
    StaffingRequirement は OpeningHours の中で時間帯を細分化できる。
    """
    __tablename__ = 'staffing_requirements'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Sunday, 6=Saturday (OpeningHours と同じ規則)
    start_time = db.Column(db.String(5), nullable=False)  # HH:MM
    end_time = db.Column(db.String(5), nullable=False)    # HH:MM
    required_count = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_staffing_org_day', 'organization_id', 'day_of_week'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'day_of_week': self.day_of_week,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'required_count': self.required_count,
        }

    def __repr__(self):
        return f'<StaffingRequirement org={self.organization_id} day={self.day_of_week} {self.start_time}-{self.end_time} need={self.required_count}>'
