import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from db.setup import get_connection

router = APIRouter()


@router.get("/")
def list_meetings():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, filename, title, date, duration, summary, created_at FROM meetings ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{meeting_id}")
def get_meeting(meeting_id: int):
    conn = get_connection()

    meeting = conn.execute(
        "SELECT * FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()

    if not meeting:
        return JSONResponse(status_code=404, content={"error": "Not found"})

    tasks = conn.execute(
        "SELECT * FROM tasks WHERE meeting_id=?", (meeting_id,)
    ).fetchall()

    decisions = conn.execute(
        "SELECT decision FROM decisions WHERE meeting_id=?", (meeting_id,)
    ).fetchall()

    speakers = conn.execute(
        "SELECT speaker, start_time, end_time, text FROM speakers WHERE meeting_id=? ORDER BY start_time",
        (meeting_id,)
    ).fetchall()

    events = conn.execute(
        "SELECT * FROM calendar_events WHERE meeting_id=?", (meeting_id,)
    ).fetchall()

    conn.close()

    m = dict(meeting)
    # transcript is stored as JSON string
    try:
        m["transcript"] = json.loads(m.get("transcript") or "[]")
    except Exception:
        m["transcript"] = []

    try:
        m["graph"] = json.loads(m.get("graph") or "{}")
    except Exception:
        m["graph"] = {}

    m["tasks"]     = [dict(t) for t in tasks]
    m["decisions"] = [d["decision"] for d in decisions]
    m["speakers"]  = [dict(s) for s in speakers]
    m["events"]    = [dict(e) for e in events]

    return m


@router.get("/{meeting_id}/status")
def get_status(meeting_id: int):
    conn = get_connection()
    row  = conn.execute(
        "SELECT summary FROM meetings WHERE id=?", (meeting_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {"status": "not_found"}

    summary = row["summary"] or ""
    if summary.startswith("PROCESSING_FAILED"):
        return {"status": "failed", "error": summary}
    elif summary:
        return {"status": "done"}
    else:
        return {"status": "processing"}


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM tasks       WHERE meeting_id=?", (meeting_id,))
    conn.execute("DELETE FROM decisions   WHERE meeting_id=?", (meeting_id,))
    conn.execute("DELETE FROM speakers    WHERE meeting_id=?", (meeting_id,))
    conn.execute("DELETE FROM calendar_events WHERE meeting_id=?", (meeting_id,))
    conn.execute("DELETE FROM meetings    WHERE id=?",          (meeting_id,))
    conn.commit()
    conn.close()
    return {"deleted": meeting_id}
