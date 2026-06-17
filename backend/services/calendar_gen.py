import os
import uuid
import logging
import requests
from datetime import datetime, timedelta
from icalendar import Calendar, Event
from db.setup import get_connection

ICS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "ics")
os.makedirs(ICS_DIR, exist_ok=True)

logger = logging.getLogger("uvicorn")


def make_ics(title: str, date_str: str, time_str: str,
             duration_min: int, participants: list, meeting_id: int) -> str:
    """
    Create an ICS file for a calendar event.
    Returns the path to the generated file.
    """
    cal = Calendar()
    cal.add("prodid", "-//Meeting Intelligence//local//EN")
    cal.add("version", "2.0")

    event = Event()
    event.add("summary", title)
    event.add("uid", str(uuid.uuid4()))

    # parse date + time
    try:
        dt_str = f"{date_str} {time_str}"
        start  = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except ValueError:
        start = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

    end = start + timedelta(minutes=duration_min)

    event.add("dtstart", start)
    event.add("dtend",   end)
    event.add("dtstamp", datetime.now())

    for person in participants:
        event.add("attendee", f"mailto:{person.lower().replace(' ', '.')}@meeting.local")

    cal.add_component(event)

    filename = f"meeting_{meeting_id}_{uuid.uuid4().hex[:6]}.ics"
    path     = os.path.join(ICS_DIR, filename)

    with open(path, "wb") as f:
        f.write(cal.to_ical())

    return path


def trigger_calendar_event_webhook(event_id: int):
    """
    Fetch the event from DB and send it to Make.com webhook if configured.
    Executed in a background thread to prevent blocking.
    """
    webhook_url = os.environ.get("MAKE_WEBHOOK_URL")
    if not webhook_url:
        logger.info("[Integration] MAKE_WEBHOOK_URL is not set. Skipping webhook trigger.")
        return

    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT id, meeting_id, title, event_date, event_time, participants FROM calendar_events WHERE id=?",
            (event_id,)
        ).fetchone()
        conn.close()

        if not row:
            logger.warning(f"[Integration] Event {event_id} not found in database.")
            return

        import json
        try:
            participants = json.loads(row["participants"])
        except Exception:
            participants = []

        base_url = os.environ.get("BACKEND_BASE_URL", "http://localhost:8000")
        ics_download_url = f"{base_url.rstrip('/')}/calendar/{row['id']}/download"

        payload = {
            "event": "meeting_scheduled",
            "event_id": row["id"],
            "meeting_id": row["meeting_id"],
            "title": row["title"],
            "date": row["event_date"],
            "time": row["event_time"],
            "participants": participants,
            "ics_download_url": ics_download_url
        }

        logger.info(f"[Integration] Sending calendar event {event_id} to Make.com webhook...")
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"[Integration] Webhook delivered successfully: {resp.status_code}")
    except Exception as e:
        logger.error(f"[Integration] Failed to trigger Make.com webhook: {e}")

