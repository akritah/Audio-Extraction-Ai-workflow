import os
import time
import json
import logging
import requests
import threading
from datetime import datetime, timedelta
from db.setup import get_connection

logger = logging.getLogger("uvicorn")

MAKE_GMAIL_WEBHOOK_URL = os.environ.get("MAKE_GMAIL_WEBHOOK_URL", "")
MAKE_CALENDAR_WEBHOOK_URL = os.environ.get("MAKE_CALENDAR_WEBHOOK_URL", "")


def log_automation_attempt(meeting_id: int, automation_type: str, payload: dict, status: str, response_code: int = None):
    """
    Log webhook transaction in automation_logs table.
    """
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO automation_logs (meeting_id, automation_type, payload, status, response_code) VALUES (?, ?, ?, ?, ?)",
            (meeting_id, automation_type, json.dumps(payload), status, response_code)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Automation Logs] Failed to write automation log: {e}")


def post_with_retry(url: str, payload: dict, max_retries: int = 3, backoff_factor: int = 2) -> requests.Response:
    """
    Helper function to send POST requests with retry and backoff.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code < 500:  # Success or client-side errors don't trigger retry
                return resp
            logger.warning(f"[Automation] Webhook returned server error {resp.status_code}. Retrying {attempt}/{max_retries}...")
        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                raise e
            logger.warning(f"[Automation] Webhook request failed: {e}. Retrying {attempt}/{max_retries}...")
        time.sleep(backoff_factor * attempt)
    raise RuntimeError("Max retries exceeded")


def send_meeting_summary(meeting_id: int, title: str, summary: str, tasks: list, decisions: list, events: list):
    """
    Construct Gmail/Summary payload and POST to MAKE_GMAIL_WEBHOOK_URL.
    """
    if not MAKE_GMAIL_WEBHOOK_URL:
        logger.warning(f"[Automation] MAKE_GMAIL_WEBHOOK_URL is not set. Skipping summary webhook for meeting {meeting_id}.")
        return

    payload = {
        "type": "summary",
        "meeting_id": meeting_id,
        "title": title or f"Meeting #{meeting_id}",
        "summary": summary,
        "tasks": tasks,
        "decisions": decisions,
        "events": events,
        "generated_at": datetime.now().isoformat()
    }

    try:
        logger.info(f"[Automation] Posting summary webhook for meeting {meeting_id}...")
        resp = post_with_retry(MAKE_GMAIL_WEBHOOK_URL, payload)
        logger.info(f"[Automation] Summary webhook delivered successfully: status {resp.status_code}")
        log_automation_attempt(meeting_id, "gmail", payload, "success", resp.status_code)
    except Exception as e:
        logger.error(f"[Automation] Failed to send meeting summary webhook: {e}")
        log_automation_attempt(meeting_id, "gmail", payload, "failed", None)


def send_calendar_event(meeting_id: int, title: str, date: str, start_time: str, end_time: str, attendees: list):
    """
    Construct Calendar Event payload and POST to MAKE_CALENDAR_WEBHOOK_URL.
    """
    if not MAKE_CALENDAR_WEBHOOK_URL:
        logger.warning(f"[Automation] MAKE_CALENDAR_WEBHOOK_URL is not set. Skipping calendar webhook for meeting {meeting_id}.")
        return

    payload = {
        "type": "event",
        "meeting_id": meeting_id,
        "title": title,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "attendees": attendees
    }

    try:
        logger.info(f"[Automation] Posting calendar webhook for meeting {meeting_id}: {title} on {date}...")
        resp = post_with_retry(MAKE_CALENDAR_WEBHOOK_URL, payload)
        logger.info(f"[Automation] Calendar webhook delivered successfully: status {resp.status_code}")
        log_automation_attempt(meeting_id, "calendar", payload, "success", resp.status_code)
    except Exception as e:
        logger.error(f"[Automation] Failed to send calendar event webhook: {e}")
        log_automation_attempt(meeting_id, "calendar", payload, "failed", None)


def trigger_meeting_summary_automation(meeting_id: int):
    """
    Asynchronously query the database for meeting details and call send_meeting_summary.
    """
    def _run():
        try:
            conn = get_connection()
            m_row = conn.execute(
                "SELECT title, summary FROM meetings WHERE id=?", (meeting_id,)
            ).fetchone()
            if not m_row:
                logger.warning(f"[Automation] Meeting {meeting_id} not found in DB.")
                conn.close()
                return

            tasks = [dict(r) for r in conn.execute(
                "SELECT task, owner, deadline, status FROM tasks WHERE meeting_id=?", (meeting_id,)
            ).fetchall()]
            decisions = [r["decision"] for r in conn.execute(
                "SELECT decision FROM decisions WHERE meeting_id=?", (meeting_id,)
            ).fetchall()]
            events_rows = conn.execute(
                "SELECT title, event_date, event_time, end_time, participants FROM calendar_events WHERE meeting_id=?", (meeting_id,)
            ).fetchall()

            events = []
            for r in events_rows:
                try:
                    parts = json.loads(r["participants"])
                except Exception:
                    parts = []
                events.append({
                    "title": r["title"],
                    "date": r["event_date"],
                    "start_time": r["event_time"],
                    "end_time": r["end_time"],
                    "attendees": parts
                })

            conn.close()

            send_meeting_summary(
                meeting_id=meeting_id,
                title=m_row["title"],
                summary=m_row["summary"],
                tasks=tasks,
                decisions=decisions,
                events=events
            )
        except Exception as e:
            logger.error(f"[Automation] Error fetching meeting summary details: {e}")

    threading.Thread(target=_run, daemon=True).start()


def process_and_trigger_calendar_event(meeting_id: int, event_dict: dict, db_conn=None):
    """
    Deduplicate, normalize, save, generate ICS, and call send_calendar_event for a single event.
    """
    import dateparser
    from services.calendar_gen import make_ics

    # 1. Normalize fields
    title = event_dict.get("title", "Meeting").strip()
    raw_date = event_dict.get("date", "").strip()
    raw_start = event_dict.get("start_time", "").strip()
    raw_end = event_dict.get("end_time", "").strip()
    attendees = event_dict.get("attendees", [])
    if not isinstance(attendees, list):
        attendees = [attendees] if attendees else []

    # Try resolving relative/plain dates
    if not raw_date or raw_date.lower() in ("unassigned", "none", ""):
        logger.warning(f"[Automation] Invalid event date '{raw_date}'. Skipping.")
        return

    # Pre-process next <weekday>
    import re
    date_str_lower = raw_date.lower().strip()
    match = re.match(r"^next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", date_str_lower)
    parsed_date = None
    if match:
        day_name = match.group(1)
        parsed_day = dateparser.parse(day_name, settings={'PREFER_DATES_FROM': 'future'})
        if parsed_day:
            delta = parsed_day - datetime.now()
            if delta.days < 7:
                parsed_day += timedelta(days=7)
            parsed_date = parsed_day

    if not parsed_date:
        # Fall back to standard dateparser
        parsed_date = dateparser.parse(raw_date, settings={'PREFER_DATES_FROM': 'future'})

    if not parsed_date:
        logger.warning(f"[Automation] Could not parse event date '{raw_date}'. Skipping.")
        return
    norm_date = parsed_date.strftime("%Y-%m-%d")

    # Normalize Start Time
    if not raw_start or raw_start.lower() in ("unassigned", "none", ""):
        raw_start = "10:00"
    parsed_start = dateparser.parse(raw_start)
    if not parsed_start:
        norm_start = "10:00"
    else:
        norm_start = parsed_start.strftime("%H:%M")

    # Normalize/Calculate End Time
    if not raw_end or raw_end.lower() in ("unassigned", "none", ""):
        try:
            st = datetime.strptime(norm_start, "%H:%M")
            et = st + timedelta(minutes=60)
            norm_end = et.strftime("%H:%M")
        except Exception:
            norm_end = "11:00"
    else:
        parsed_end = dateparser.parse(raw_end)
        if not parsed_end:
            try:
                st = datetime.strptime(norm_start, "%H:%M")
                et = st + timedelta(minutes=60)
                norm_end = et.strftime("%H:%M")
            except Exception:
                norm_end = "11:00"
        else:
            norm_end = parsed_end.strftime("%H:%M")

    # 2. Database deduplication checks
    local_conn = db_conn is None
    if local_conn:
        db_conn = get_connection()

    try:
        dup = db_conn.execute(
            "SELECT id FROM calendar_events WHERE meeting_id=? AND title=? AND event_date=? AND event_time=?",
            (meeting_id, title, norm_date, norm_start)
        ).fetchone()

        if dup:
            logger.info(f"[Automation] Event '{title}' on {norm_date} at {norm_start} is a duplicate. Skipping.")
            if local_conn:
                db_conn.close()
            return

        # 3. Create ICS File
        duration = 60
        try:
            st = datetime.strptime(norm_start, "%H:%M")
            et = datetime.strptime(norm_end, "%H:%M")
            duration = int((et - st).total_seconds() / 60)
            if duration <= 0:
                duration = 60
        except Exception:
            pass

        ics_path = make_ics(
            title=title,
            date_str=norm_date,
            time_str=norm_start,
            duration_min=duration,
            participants=attendees,
            meeting_id=meeting_id
        )

        # 4. Insert into database
        cursor = db_conn.cursor()
        cursor.execute(
            "INSERT INTO calendar_events (meeting_id, title, event_date, event_time, end_time, duration_min, participants, ics_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (meeting_id, title, norm_date, norm_start, norm_end, duration, json.dumps(attendees), ics_path)
        )
        if local_conn:
            db_conn.commit()

        logger.info(f"[Automation] Saved new event '{title}' on {norm_date} to DB.")

        # 5. Trigger Google Calendar webhook asynchronously
        threading.Thread(
            target=send_calendar_event,
            args=(meeting_id, title, norm_date, norm_start, norm_end, attendees),
            daemon=True
        ).start()

    except Exception as err:
        logger.error(f"[Automation] Error processing calendar event: {err}")
    finally:
        if local_conn:
            db_conn.close()
