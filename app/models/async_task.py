"""DB-backed async task queue for serverless environments.

Tasks are stored in PostgreSQL and processed via a cron endpoint,
making this compatible with Vercel's serverless deployment.
"""

from datetime import datetime, timedelta
from app.extensions import db


class AsyncTask(db.Model):
    __tablename__ = 'async_tasks'

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False, index=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(
        db.String(20), nullable=False, default='pending', index=True,
    )  # pending | running | completed | failed | dead
    priority = db.Column(db.Integer, nullable=False, default=0)  # higher = more urgent

    # Retry
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    max_retries = db.Column(db.Integer, nullable=False, default=3)
    next_run_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Tracking
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

    # Ownership (who/what triggered this task)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'task_type': self.task_type,
            'status': self.status,
            'priority': self.priority,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
        }

    def mark_running(self):
        self.status = 'running'
        self.started_at = datetime.utcnow()

    def mark_completed(self):
        self.status = 'completed'
        self.completed_at = datetime.utcnow()

    def mark_failed(self, error_message):
        self.retry_count += 1
        self.error_message = str(error_message)[:2000]
        if self.retry_count >= self.max_retries:
            self.status = 'dead'
            self.completed_at = datetime.utcnow()
        else:
            self.status = 'pending'
            # Exponential backoff: 30s, 2min, 8min
            delay = 30 * (4 ** (self.retry_count - 1))
            self.next_run_at = datetime.utcnow() + timedelta(seconds=delay)

    def __repr__(self):
        return f'<AsyncTask {self.id} {self.task_type} [{self.status}]>'
