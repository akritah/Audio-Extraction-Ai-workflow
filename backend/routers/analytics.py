from fastapi import APIRouter
from db.setup import get_connection

router = APIRouter()


@router.get("/overview")
def overview():
    conn = get_connection()

    total_meetings = conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    total_tasks    = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    pending        = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='Pending'").fetchone()[0]
    done           = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='Done'").fetchone()[0]
    total_events   = conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]

    tasks_per_person = conn.execute(
        "SELECT owner, COUNT(*) as count FROM tasks WHERE owner IS NOT NULL GROUP BY owner ORDER BY count DESC LIMIT 10"
    ).fetchall()

    recent = conn.execute(
        "SELECT id, filename, created_at FROM meetings ORDER BY id DESC LIMIT 5"
    ).fetchall()

    conn.close()

    return {
        "total_meetings":  total_meetings,
        "total_tasks":     total_tasks,
        "pending_tasks":   pending,
        "completed_tasks": done,
        "total_events":    total_events,
        "tasks_per_person": [dict(r) for r in tasks_per_person],
        "recent_meetings":  [dict(r) for r in recent],
    }


@router.get("/daily-report")
def daily_report():
    """
    Generates a daily digest: pending tasks, upcoming meetings, and overdue items.
    """
    from datetime import date
    today = str(date.today())

    conn = get_connection()

    pending = conn.execute(
        "SELECT task, owner, deadline FROM tasks WHERE status='Pending' ORDER BY deadline"
    ).fetchall()

    upcoming = conn.execute(
        "SELECT title, event_date, event_time FROM calendar_events WHERE event_date >= ? ORDER BY event_date LIMIT 10",
        (today,)
    ).fetchall()

    overdue = conn.execute(
        "SELECT task, owner, deadline FROM tasks WHERE status='Pending' AND deadline < ? AND deadline IS NOT NULL",
        (today,)
    ).fetchall()

    conn.close()

    return {
        "date":     today,
        "pending":  [dict(r) for r in pending],
        "upcoming": [dict(r) for r in upcoming],
        "overdue":  [dict(r) for r in overdue],
    }
