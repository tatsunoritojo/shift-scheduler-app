from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from flask import current_app

JST = ZoneInfo("Asia/Tokyo")

from app.extensions import db
from app.models.opening_hours import OpeningHoursException, OpeningHoursCalendarSync, SyncOperationLog
from app.services.shift_service import get_opening_hours_for_date
from app.services.calendar_service import create_event, update_event, delete_event, fetch_events


def export_opening_hours_to_calendar(org_id, credentials, start_date, end_date):
    """Export opening hours to Google Calendar as '開校時間' events.

    Priority (low → high):
      1. Weekly default (OpeningHours) — exported to calendar
      2. Calendar-imported exceptions (source='calendar') — skipped, calendar is source of truth
      3. Manual exceptions (source='manual') — exported to calendar
    """
    stats = {'created': 0, 'updated': 0, 'deleted': 0, 'skipped': 0, 'errors': []}

    existing_syncs = {
        s.sync_date: s
        for s in OpeningHoursCalendarSync.query.filter(
            OpeningHoursCalendarSync.organization_id == org_id,
            OpeningHoursCalendarSync.sync_date >= start_date,
            OpeningHoursCalendarSync.sync_date <= end_date,
        ).all()
    }

    # Dates imported from Google Calendar — don't overwrite (calendar is source of truth)
    calendar_sourced_dates = {
        e.exception_date
        for e in OpeningHoursException.query.filter(
            OpeningHoursException.organization_id == org_id,
            OpeningHoursException.exception_date >= start_date,
            OpeningHoursException.exception_date <= end_date,
            OpeningHoursException.source == 'calendar',
        ).all()
    }

    current = start_date
    while current <= end_date:
        try:
            # Skip calendar-imported dates — calendar has higher priority
            if current in calendar_sourced_dates:
                stats['skipped'] += 1
                current += timedelta(days=1)
                continue

            hours = get_opening_hours_for_date(org_id, current)
            sync_record = existing_syncs.get(current)

            if hours:
                # Open day
                st, et = hours['start_time'], hours['end_time']
                start_dt = f"{current.isoformat()}T{st}:00"
                end_dt = f"{current.isoformat()}T{et}:00"
                summary = '開校時間'
                description = f'{st}〜{et}'

                if not sync_record:
                    event_id = create_event(
                        credentials, 'primary', summary, start_dt, end_dt, description
                    )
                    db.session.add(OpeningHoursCalendarSync(
                        organization_id=org_id,
                        sync_date=current,
                        calendar_event_id=event_id,
                        start_time=st,
                        end_time=et,
                    ))
                    stats['created'] += 1
                elif sync_record.start_time != st or sync_record.end_time != et:
                    update_event(
                        credentials, 'primary', sync_record.calendar_event_id,
                        summary, start_dt, end_dt, description
                    )
                    sync_record.start_time = st
                    sync_record.end_time = et
                    sync_record.synced_at = datetime.utcnow()
                    stats['updated'] += 1
                else:
                    stats['skipped'] += 1
            else:
                # Closed day — delete if previously synced
                if sync_record:
                    try:
                        delete_event(credentials, 'primary', sync_record.calendar_event_id)
                    except Exception:
                        pass  # Event may already be deleted on calendar side
                    db.session.delete(sync_record)
                    stats['deleted'] += 1
                else:
                    stats['skipped'] += 1
        except Exception as e:
            current_app.logger.error(f"Sync export error for {current.isoformat()}: {e}")
            stats['errors'].append({'date': current.isoformat(), 'error': '同期エラー'})

        current += timedelta(days=1)

    log = SyncOperationLog(
        organization_id=org_id,
        operation_type='export',
        start_date=start_date,
        end_date=end_date,
        result_summary=stats,
    )
    db.session.add(log)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return stats


def import_opening_hours_from_calendar(org_id, credentials, start_date, end_date):
    """Import '開校時間' events from Google Calendar as opening hour exceptions."""
    stats = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    try:
        events = fetch_events(
            credentials, start_date.isoformat(), end_date.isoformat(),
            calendar_id='primary', query='開校時間'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to fetch events: {e}")
        stats['errors'].append({'error': 'カレンダーイベントの取得に失敗しました'})
        log = SyncOperationLog(
            organization_id=org_id,
            operation_type='import',
            start_date=start_date,
            end_date=end_date,
            result_summary=stats,
        )
        db.session.add(log)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return stats

    # Collect dates that have '開校時間' events
    dates_with_events = set()

    for event in events:
        try:
            # Only exact title match & timed events (not all-day)
            if event.get('summary') != '開校時間':
                continue
            start_str = event.get('start', '')
            end_str = event.get('end', '')
            if 'T' not in start_str or 'T' not in end_str:
                continue  # Skip all-day events

            event_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(JST)
            event_end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00')).astimezone(JST)
            event_date = event_dt.date()
            st = event_dt.strftime('%H:%M')
            et = event_end_dt.strftime('%H:%M')

            dates_with_events.add(event_date)

            existing = OpeningHoursException.query.filter_by(
                organization_id=org_id, exception_date=event_date
            ).first()

            if existing:
                if existing.source == 'calendar':
                    if existing.start_time != st or existing.end_time != et or existing.is_closed:
                        existing.start_time = st
                        existing.end_time = et
                        existing.is_closed = False
                        existing.updated_at = datetime.utcnow()
                        stats['updated'] += 1
                    else:
                        stats['skipped'] += 1
                else:
                    # Manual entry — don't overwrite
                    stats['skipped'] += 1
            else:
                exc = OpeningHoursException(
                    organization_id=org_id,
                    exception_date=event_date,
                    start_time=st,
                    end_time=et,
                    is_closed=False,
                    reason='Googleカレンダーから取込',
                    source='calendar',
                )
                db.session.add(exc)
                stats['imported'] += 1
        except Exception as e:
            current_app.logger.error(f"Sync import error for event {event.get('id', '?')}: {e}")
            stats['errors'].append({'event': event.get('id', '?'), 'error': '取込エラー'})

    # Mark dates without events as closed (calendar is source of truth)
    stats['closed'] = 0
    current = start_date
    while current <= end_date:
        if current not in dates_with_events:
            existing = OpeningHoursException.query.filter_by(
                organization_id=org_id, exception_date=current
            ).first()

            if existing:
                if existing.source == 'calendar':
                    if not existing.is_closed:
                        existing.is_closed = True
                        existing.start_time = None
                        existing.end_time = None
                        existing.updated_at = datetime.utcnow()
                        stats['closed'] += 1
                    else:
                        stats['skipped'] += 1
                else:
                    stats['skipped'] += 1  # Manual entry — don't overwrite
            else:
                exc = OpeningHoursException(
                    organization_id=org_id,
                    exception_date=current,
                    start_time=None,
                    end_time=None,
                    is_closed=True,
                    reason='Googleカレンダーに予定なし',
                    source='calendar',
                )
                db.session.add(exc)
                stats['closed'] += 1
        current += timedelta(days=1)

    log = SyncOperationLog(
        organization_id=org_id,
        operation_type='import',
        start_date=start_date,
        end_date=end_date,
        result_summary=stats,
    )
    db.session.add(log)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return stats
