import os
import uuid
from datetime import datetime, timedelta
from icalendar import Calendar, Event

ICS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "ics")
os.makedirs(ICS_DIR, exist_ok=True)


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
