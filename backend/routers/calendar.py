import os
from fastapi import APIRouter
from fastapi.responses import FileResponse
from db.setup import get_connection

router = APIRouter()


@router.get("/")
def list_events(meeting_id: int = None):
    conn  = get_connection()
    query = "SELECT * FROM calendar_events WHERE 1=1"
    args  = []

    if meeting_id:
        query += " AND meeting_id=?"
        args.append(meeting_id)

    query += " ORDER BY event_date, event_time"
    rows = conn.execute(query, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{event_id}/download")
def download_ics(event_id: int):
    conn = get_connection()
    row  = conn.execute(
        "SELECT ics_path, title FROM calendar_events WHERE id=?", (event_id,)
    ).fetchone()
    conn.close()

    if not row or not row["ics_path"]:
        return {"error": "ICS file not found"}

    return FileResponse(
        path=row["ics_path"],
        filename=f"{row['title'] or 'event'}.ics",
        media_type="text/calendar",
    )
