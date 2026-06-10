import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse

from services.audio       import load_and_clean
from services.transcribe  import transcribe, segments_to_text
from services.diarize     import run_diarization, align_transcript_with_speakers
from services.extract     import extract_entities, generate_summary
from services.search      import index_meeting
from services.calendar_gen import make_ics
from services.graph       import build_graph
from db.setup             import get_connection

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/audio")
async def upload_audio(
    file: UploadFile = File(...),
    num_speakers: int = Form(default=None),
    language: str    = Form(default="en"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    # save uploaded file
    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # insert a placeholder row and return the meeting_id immediately
    conn = get_connection()
    c    = conn.cursor()
    c.execute("INSERT INTO meetings (filename) VALUES (?)", (file.filename,))
    meeting_id = c.lastrowid
    conn.commit()
    conn.close()

    # run the heavy pipeline in the background
    background_tasks.add_task(
        run_pipeline, save_path, meeting_id, num_speakers, language
    )

    return {"meeting_id": meeting_id, "status": "processing"}


def run_pipeline(audio_path: str, meeting_id: int, num_speakers, language: str):
    try:
        # Stage 1: clean audio
        clean_path = load_and_clean(audio_path)

        # Stage 2: transcription
        transcript_segs = transcribe(clean_path, language=language)
        full_text       = segments_to_text(transcript_segs)

        # Stage 3: diarization
        diarization_segs   = run_diarization(clean_path, num_speakers=num_speakers)
        aligned            = align_transcript_with_speakers(transcript_segs, diarization_segs)

        # Stage 4: extraction
        extracted = extract_entities(full_text)

        # Stage 5: summary / meeting minutes
        summary = generate_summary(full_text, extracted)

        # persist to SQLite
        conn = get_connection()
        c    = conn.cursor()

        import json
        c.execute(
            "UPDATE meetings SET transcript=?, summary=? WHERE id=?",
            (json.dumps(aligned), summary, meeting_id)
        )

        for t in extracted.get("tasks", []):
            c.execute(
                "INSERT INTO tasks (meeting_id, task, owner, deadline) VALUES (?,?,?,?)",
                (meeting_id, t.get("task"), t.get("owner"), t.get("deadline"))
            )

        for d in extracted.get("decisions", []):
            c.execute(
                "INSERT INTO decisions (meeting_id, decision) VALUES (?,?)",
                (meeting_id, d)
            )

        for sp in aligned:
            c.execute(
                "INSERT INTO speakers (meeting_id, speaker, start_time, end_time, text) VALUES (?,?,?,?,?)",
                (meeting_id, sp["speaker"], sp["start"], sp["end"], sp["text"])
            )

        # Stage 7: calendar events
        for ev in extracted.get("events", []):
            ics_path = make_ics(
                title        =ev.get("title", "Meeting"),
                date_str     =ev.get("date", ""),
                time_str     =ev.get("time", "10:00"),
                duration_min =60,
                participants =ev.get("participants", []),
                meeting_id   =meeting_id,
            )
            c.execute(
                """INSERT INTO calendar_events
                   (meeting_id, title, event_date, event_time, participants, ics_path)
                   VALUES (?,?,?,?,?,?)""",
                (meeting_id,
                 ev.get("title"),
                 ev.get("date"),
                 ev.get("time"),
                 json.dumps(ev.get("participants", [])),
                 ics_path)
            )

        conn.commit()
        conn.close()

        # Stage 8: index in ChromaDB
        index_meeting(meeting_id, full_text, summary, extracted.get("tasks", []))

        # knowledge graph (stored as JSON in meetings table)
        graph = build_graph(
            meeting_id,
            extracted.get("tasks", []),
            extracted.get("decisions", []),
            extracted.get("people", []),
        )
        import json as _json
        conn2 = get_connection()
        conn2.execute(
            "ALTER TABLE meetings ADD COLUMN graph TEXT",
            # ignore if column already exists
        ) if False else None
        # safe update
        try:
            conn2.execute("ALTER TABLE meetings ADD COLUMN graph TEXT")
        except Exception:
            pass
        conn2.execute(
            "UPDATE meetings SET graph=? WHERE id=?",
            (_json.dumps(graph), meeting_id)
        )
        conn2.commit()
        conn2.close()

    except Exception as e:
        # mark as failed so the frontend can show an error state
        conn = get_connection()
        conn.execute(
            "UPDATE meetings SET summary=? WHERE id=?",
            (f"PROCESSING_FAILED: {str(e)}", meeting_id)
        )
        conn.commit()
        conn.close()
        raise
