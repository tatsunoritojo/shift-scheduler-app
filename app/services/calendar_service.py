from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def fetch_events(credentials, start_date, end_date, calendar_id='primary', query=None):
    """Fetch Google Calendar events within a date range."""
    service = build('calendar', 'v3', credentials=credentials)

    start_time = datetime.fromisoformat(start_date).isoformat() + 'Z'
    end_time = datetime.fromisoformat(end_date).isoformat() + 'Z'

    params = dict(
        calendarId=calendar_id,
        timeMin=start_time,
        timeMax=end_time,
        singleEvents=True,
        orderBy='startTime',
    )
    if query:
        params['q'] = query

    events_result = service.events().list(**params).execute()

    events = events_result.get('items', [])
    event_list = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        event_list.append({
            'id': event['id'],
            'summary': event.get('summary', 'No Title'),
            'start': start,
            'end': end,
            'location': event.get('location'),
            'description': event.get('description'),
        })

    return event_list


def list_calendars(credentials):
    """List all calendars the user has access to."""
    service = build('calendar', 'v3', credentials=credentials)
    result = service.calendarList().list().execute()
    calendars = []
    for cal in result.get('items', []):
        calendars.append({
            'id': cal['id'],
            'summary': cal.get('summary', ''),
            'description': cal.get('description', ''),
            'backgroundColor': cal.get('backgroundColor', '#4285f4'),
            'foregroundColor': cal.get('foregroundColor', '#ffffff'),
            'primary': cal.get('primary', False),
            'accessRole': cal.get('accessRole', ''),
        })
    return calendars


def create_event(credentials, calendar_id, summary, start_datetime, end_datetime, description=None):
    """Create a Google Calendar event."""
    service = build('calendar', 'v3', credentials=credentials)

    event_body = {
        'summary': summary,
        'start': {'dateTime': start_datetime, 'timeZone': 'Asia/Tokyo'},
        'end': {'dateTime': end_datetime, 'timeZone': 'Asia/Tokyo'},
    }
    if description:
        event_body['description'] = description

    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return created.get('id')


def update_event(credentials, calendar_id, event_id, summary, start_datetime, end_datetime, description=None):
    """Update an existing Google Calendar event."""
    service = build('calendar', 'v3', credentials=credentials)

    event_body = {
        'summary': summary,
        'start': {'dateTime': start_datetime, 'timeZone': 'Asia/Tokyo'},
        'end': {'dateTime': end_datetime, 'timeZone': 'Asia/Tokyo'},
    }
    if description:
        event_body['description'] = description

    updated = service.events().update(
        calendarId=calendar_id, eventId=event_id, body=event_body
    ).execute()
    return updated.get('id')


def delete_event(credentials, calendar_id, event_id):
    """Delete a Google Calendar event."""
    service = build('calendar', 'v3', credentials=credentials)
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
