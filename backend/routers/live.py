import os
import json
import time
import logging
import asyncio
import traceback
import numpy as np
import soundfile as sf
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from db.setup import get_connection
from services.audio import load_and_clean
from services.transcribe import transcribe
from services.diarize import run_diarization, align_transcript_with_speakers
from services.emotion import detect_emotion, detect_context_emotion
from services.extract import (
    extract_incremental_tasks_and_events,
    generate_incremental_summary,
    analyze_meeting_atmosphere,
    answer_meeting_query,
    generate_summary
)
from services.calendar_gen import make_ics
from services.search import index_meeting
from services.graph import build_graph

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "temp_audio")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

class StartMeetingRequest(BaseModel):
    title: str = "Live Meeting"

class QueryRequest(BaseModel):
    query: str

@router.post("/start")
def start_live_meeting(req: StartMeetingRequest):
    """
    Initialize a new live meeting session in the database.
    """
    conn = get_connection()
    c = conn.cursor()
    timestamp = int(time.time())
    filename = f"live_meeting_{timestamp}.wav"
    
    c.execute(
        "INSERT INTO meetings (filename, title, status, transcript, summary) VALUES (?, ?, ?, ?, ?)",
        (filename, req.title, "active", "[]", "")
    )
    meeting_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return {"meeting_id": meeting_id, "filename": filename}

@router.post("/{meeting_id}/query")
def query_live_meeting(meeting_id: int, req: QueryRequest):
    """
    Q&A endpoint: Answer natural language questions about the current meeting.
    """
    conn = get_connection()
    # 1. Fetch transcript segments
    rows = conn.execute(
        "SELECT speaker, text FROM speakers WHERE meeting_id=? ORDER BY start_time",
        (meeting_id,)
    ).fetchall()
    transcript = [dict(r) for r in rows]

    # 2. Fetch tasks
    t_rows = conn.execute(
        "SELECT task, owner, deadline, status FROM tasks WHERE meeting_id=?",
        (meeting_id,)
    ).fetchall()
    tasks = [dict(r) for r in t_rows]
    conn.close()

    if not transcript and not tasks:
        return {"answer": "No details recorded in this meeting yet."}

    answer = answer_meeting_query(transcript, tasks, req.query)
    return {"answer": answer}

logger = logging.getLogger("uvicorn")

def append_to_wav(file_path: str, samples_data: np.ndarray, sample_rate: int):
    """
    Append raw float32 samples to the WAV file.
    If the file doesn't exist, create it. Otherwise open and append.
    """
    if not os.path.exists(file_path):
        with sf.SoundFile(file_path, mode='w', samplerate=sample_rate, channels=1, subtype='PCM_16') as f:
            f.write(samples_data)
    else:
        with sf.SoundFile(file_path, mode='r+') as f:
            f.seek(0, sf.SEEK_END)
            f.write(samples_data)

def insert_placeholder_segment_db(meeting_id, chunk_text, start_time, end_time) -> int:
    db_conn = get_connection()
    c = db_conn.cursor()
    c.execute(
        "INSERT INTO speakers (meeting_id, speaker, start_time, end_time, text, emotion, emotion_confidence, context_emotion, context_explanation, context_emotion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (meeting_id, "Speaker_00", start_time, end_time, chunk_text, "Neutral", 1.0, "Neutral", "Analyzing in background...", 1.0)
    )
    segment_id = c.lastrowid
    db_conn.commit()
    db_conn.close()
    return segment_id

def update_chunk_metadata_db(segment_id, meeting_id, audio_emo, audio_conf, final_emotion, final_conf, explanation, extracted):
    db_conn = get_connection()
    new_tasks = []
    new_events = []
    
    # 1. Fetch existing tasks/events for duplicate checks
    existing_tasks = [dict(r) for r in db_conn.execute("SELECT task FROM tasks WHERE meeting_id=?", (meeting_id,)).fetchall()]
    existing_events = [dict(r) for r in db_conn.execute("SELECT title FROM calendar_events WHERE meeting_id=?", (meeting_id,)).fetchall()]
    
    # Insert tasks
    for t in extracted.get("tasks", []):
        db_conn.execute(
            "INSERT INTO tasks (meeting_id, task, owner, deadline) VALUES (?, ?, ?, ?)",
            (meeting_id, t.get("task"), t.get("owner"), t.get("deadline"))
        )
        new_tasks.append(t)
        
    # Insert decisions
    for d in extracted.get("decisions", []):
        db_conn.execute(
            "INSERT INTO decisions (meeting_id, decision) VALUES (?, ?)",
            (meeting_id, d)
        )
        
    # Insert calendar events
    from services.automation import process_and_trigger_calendar_event
    for ev in extracted.get("events", []):
        if "attendees" not in ev and "participants" in ev:
            ev["attendees"] = ev["participants"]
        if "start_time" not in ev and "time" in ev:
            ev["start_time"] = ev["time"]
        process_and_trigger_calendar_event(meeting_id, ev, db_conn)
        new_events.append(ev)

    # Update speakers table for this segment ID
    db_conn.execute(
        "UPDATE speakers SET emotion=?, emotion_confidence=?, context_emotion=?, context_explanation=?, context_emotion_confidence=? WHERE id=?",
        (audio_emo, audio_conf, final_emotion, explanation, final_conf, segment_id)
    )
    db_conn.commit()
    db_conn.close()
    return new_tasks, new_events

def update_diarization_db(meeting_id, diar_segs):
    db_conn = get_connection()
    rows = db_conn.execute(
        "SELECT id, start_time, end_time, text FROM speakers WHERE meeting_id=? ORDER BY start_time",
        (meeting_id,)
    ).fetchall()
    
    transcript_segs = [
        {"id": r["id"], "start": r["start_time"], "end": r["end_time"], "text": r["text"]}
        for r in rows
    ]
    
    aligned = align_transcript_with_speakers(transcript_segs, diar_segs)
    
    for seg in aligned:
        db_conn.execute(
            "UPDATE speakers SET speaker=? WHERE id=?",
            (seg["speaker"], seg["id"])
        )
    db_conn.commit()
    db_conn.close()
    return aligned

def run_periodic_summary_db(meeting_id, running_summary):
    db_conn = get_connection()
    rows = db_conn.execute(
        "SELECT speaker, text, emotion, emotion_confidence, context_emotion, context_explanation, context_emotion_confidence, start_time as start, end_time as end FROM speakers WHERE meeting_id=? ORDER BY start_time",
        (meeting_id,)
    ).fetchall()
    segments = [dict(r) for r in rows]
    
    full_text = " ".join([s["text"] for s in segments])
    
    atmosphere = analyze_meeting_atmosphere(segments)
    emotion_trend = f"Dominant Emotion: {atmosphere.get('dominant_emotion')}. Overall Sentiment: {atmosphere.get('meeting_sentiment')}. Observations: {', '.join(atmosphere.get('observations', []))}"
    
    new_running_summary = generate_incremental_summary(running_summary, full_text[-1500:], emotion_trend)
    
    db_conn.execute(
        "UPDATE meetings SET summary=?, sentiment=?, dominant_emotion=?, sentiment_confidence=?, sentiment_observations=? WHERE id=?",
        (
            new_running_summary,
            atmosphere.get("meeting_sentiment", "Neutral"),
            atmosphere.get("dominant_emotion", "Neutral"),
            atmosphere.get("confidence", 0.5),
            json.dumps(atmosphere.get("observations", [])),
            meeting_id
        )
    )
    db_conn.commit()
    db_conn.close()
    return new_running_summary, atmosphere

def compile_and_finalize_meeting_db(meeting_id, running_summary):
    db_conn = get_connection()
    rows = db_conn.execute(
        "SELECT speaker, text, emotion, emotion_confidence, context_emotion, context_explanation, context_emotion_confidence, start_time as start, end_time as end FROM speakers WHERE meeting_id=? ORDER BY start_time",
        (meeting_id,)
    ).fetchall()
    segments = [dict(r) for r in rows]
    
    full_text = " ".join([s["text"] for s in segments])
    
    tasks = [dict(r) for r in db_conn.execute("SELECT task, owner, deadline FROM tasks WHERE meeting_id=?", (meeting_id,)).fetchall()]
    decisions = [r["decision"] for r in db_conn.execute("SELECT decision FROM decisions WHERE meeting_id=?", (meeting_id,)).fetchall()]
    events = [dict(r) for r in db_conn.execute("SELECT title, event_date, event_time, participants FROM calendar_events WHERE meeting_id=?", (meeting_id,)).fetchall()]
    
    atmosphere = analyze_meeting_atmosphere(segments)
    emotion_context = f"Sentiment: {atmosphere.get('meeting_sentiment')}. Dominant Emotion: {atmosphere.get('dominant_emotion')}. Observations: {', '.join(atmosphere.get('observations', []))}"
    
    extracted_dict = {"tasks": tasks, "decisions": decisions, "events": events}
    final_summary = generate_summary(full_text, extracted_dict, emotion_context)
    
    graph_data = build_graph(
        meeting_id,
        tasks,
        decisions,
        list({s["speaker"] for s in segments if s["speaker"] != "Unknown"})
    )
    
    db_conn.execute(
        "UPDATE meetings SET status='done', summary=?, transcript=?, graph=? WHERE id=?",
        (final_summary, json.dumps(segments), json.dumps(graph_data), meeting_id)
    )
    db_conn.commit()
    db_conn.close()
    index_meeting(meeting_id, full_text, final_summary, tasks)
    
    # Trigger Gmail Summary Webhook asynchronously
    from services.automation import trigger_meeting_summary_automation
    trigger_meeting_summary_automation(meeting_id)

async def process_chunk_intelligence(meeting_id, segment_id, chunk_path, chunk_text, start_time, end_time, whisper_latency, whisper_conf, websocket):
    try:
        t_intel_start = time.time()
        # 1. Detect Audio Emotion
        emotion_res = await asyncio.to_thread(detect_emotion, chunk_path, chunk_text)
        audio_emo = emotion_res.get("emotion", "Neutral")
        audio_conf = emotion_res.get("confidence", 1.0)
        
        # 2. Context LLM Emotion (only if text is >= 8 words)
        final_emotion = audio_emo
        final_conf = audio_conf
        explanation = "Resolved by acoustic cues."
        if len(chunk_text.strip().split()) >= 8:
            context_emo_res = await asyncio.to_thread(detect_context_emotion, chunk_text, audio_emo, audio_conf)
            final_emotion = context_emo_res.get("emotion", "Neutral")
            final_conf = context_emo_res.get("confidence", audio_conf)
            explanation = context_emo_res.get("explanation", "")
        
        # 3. Extract tasks/events incremental (only if text is >= 8 words)
        extracted = {"tasks": [], "decisions": [], "events": [], "risks": [], "open_questions": []}
        if len(chunk_text.strip().split()) >= 8:
            extracted = await asyncio.to_thread(extract_incremental_tasks_and_events, chunk_text, None, None)
        
        # 4. Save segment details to database (update the placeholder segment)
        new_tasks, new_events = await asyncio.to_thread(
            update_chunk_metadata_db,
            segment_id,
            meeting_id,
            audio_emo,
            audio_conf,
            final_emotion,
            final_conf,
            explanation,
            extracted
        )
        
        intel_latency = time.time() - t_intel_start
        total_chunk_latency = whisper_latency + intel_latency
        
        logger.info(
            f"[Pipeline Metrics] Chunk processed successfully:\n"
            f"  - Transcription Confidence: {whisper_conf:.4f}\n"
            f"  - Acoustic Emotion Confidence: {audio_conf:.4f}\n"
            f"  - Contextual Emotion Confidence: {final_conf:.4f}\n"
            f"  - Transcription Latency: {whisper_latency:.4f} seconds\n"
            f"  - Intelligence Latency: {intel_latency:.4f} seconds\n"
            f"  - Total Processing Latency: {total_chunk_latency:.4f} seconds"
        )
        
        # 5. Broadcast the updated intelligence segment to the WebSocket
        logger.info(f"[WebSocket Pipeline] Broadcasting async intelligence updates for start_time={start_time}...")
        await websocket.send_json({
            "type": "intelligence_update",
            "segment_start": start_time,
            "emotion": final_emotion,
            "explanation": explanation,
            "new_tasks": new_tasks,
            "new_events": new_events
        })
    except Exception as intel_err:
        logger.error(f"[WebSocket Background Intel] Error processing chunk intelligence: {intel_err}")

@router.websocket("/ws/live/{meeting_id}")
async def websocket_live_meeting(websocket: WebSocket, meeting_id: int):
    """
    WebSocket endpoint for real-time audio streaming.
    Receives raw Float32 mono PCM data.
    """
    logger.info(f"[WebSocket] Connection request received for meeting_id={meeting_id}")
    try:
        await websocket.accept()
        logger.info(f"[WebSocket] Connection accepted. Verifying meeting_id={meeting_id} in database...")
        
        # 1. Verify meeting is active
        def verify_meeting(m_id):
            db_conn = get_connection()
            m = db_conn.execute("SELECT * FROM meetings WHERE id=?", (m_id,)).fetchone()
            db_conn.close()
            return dict(m) if m else None

        meeting = await asyncio.to_thread(verify_meeting, meeting_id)
        if not meeting:
            logger.warning(f"[WebSocket] Verification failed: meeting_id={meeting_id} not found. Closing connection.")
            await websocket.close(code=1008)
            return

        master_filename = meeting["filename"]
        master_wav_path = os.path.join(UPLOAD_DIR, master_filename)
        logger.info(f"[WebSocket] Verified successfully. Session WAV will write to: {master_wav_path}")
        # Initialize state variables
        sample_rate = 16000
        chunk_duration = 4  # Process in 4-second audio chunks
        samples_per_chunk = sample_rate * chunk_duration
        overlap_duration = 1.5  # 1.5 seconds rolling overlap
        overlap_samples = int(sample_rate * overlap_duration)
        last_max_end_time = 0.0

        current_chunk_samples = []
        
        total_samples_processed = 0
        last_diarization_samples = 0
        last_summary_samples = 0

        chunk_idx = 0
        packet_idx = 0
        running_summary = ""

        logger.info(
            f"[WebSocket] Initialized states: sample_rate={sample_rate}Hz, chunk_duration={chunk_duration}s, "
            f"overlap_duration={overlap_duration}s, samples_per_chunk={samples_per_chunk}. Entering receive loop..."
        )

        while True:
            # Receive binary packet of Float32 PCM
            data = await websocket.receive_bytes()
            packet_idx += 1
            
            if not data:
                if packet_idx % 50 == 1:
                    logger.info(f"[WebSocket Loop] Packet {packet_idx} received: Empty payload.")
                continue

            # Align length to 4-byte boundaries (Float32 is 4 bytes)
            original_len = len(data)
            if len(data) % 4 != 0:
                data = data[:(len(data) // 4) * 4]
            
            samples = np.frombuffer(data, dtype=np.float32)
            if len(samples) == 0:
                if packet_idx % 50 == 1:
                    logger.info(f"[WebSocket Loop] Packet {packet_idx} decoded: 0 samples.")
                continue

            # Append to buffer
            current_chunk_samples.extend(samples.tolist())
            
            # Log packet metadata and basic sample stats to verify data health
            if packet_idx % 20 == 1:
                s_min = float(samples.min())
                s_max = float(samples.max())
                s_mean = float(samples.mean())
                s_std = float(samples.std())
                logger.info(
                    f"[WebSocket Loop] Packet {packet_idx}: received={original_len} bytes ({len(samples)} samples). "
                    f"Min={s_min:.4f}, Max={s_max:.4f}, Mean={s_mean:.4f}, Std={s_std:.4f}. "
                    f"Buffer={len(current_chunk_samples)}/{samples_per_chunk}"
                )

            # If we have accumulated enough audio for a chunk
            if len(current_chunk_samples) >= samples_per_chunk:
                logger.info(f"[WebSocket Pipeline] Threshold reached: {len(current_chunk_samples)} samples accumulated. Processing chunk {chunk_idx}...")
                try:
                    # 1. Save chunk to temporary wav file
                    chunk_filename = f"live_{meeting_id}_chunk_{chunk_idx}.wav"
                    chunk_path = os.path.join(TEMP_DIR, chunk_filename)
                    chunk_data = np.array(current_chunk_samples[:samples_per_chunk], dtype=np.float32)
                    
                    # Normalize peak to avoid clipping
                    peak = np.abs(chunk_data).max()
                    if peak > 0:
                        chunk_data = chunk_data / peak * 0.95
                    
                    logger.info(f"[WebSocket Pipeline] Writing chunk {chunk_idx} WAV file to: {chunk_path}")
                    await asyncio.to_thread(sf.write, chunk_path, chunk_data, sample_rate)
                    
                    # Write master WAV progress incrementally using thread-safe append helper (excluding overlap)
                    if chunk_idx == 0:
                        master_append_data = chunk_data
                    else:
                        master_append_data = chunk_data[overlap_samples:]
                    logger.info(f"[WebSocket Pipeline] Appending {len(master_append_data)} new samples to master WAV: {master_wav_path}")
                    await asyncio.to_thread(append_to_wav, master_wav_path, master_append_data, sample_rate)
                    
                    # 2. Transcribe using Whisper (run in background thread)
                    logger.info(f"[WebSocket Pipeline] Running Whisper transcription for chunk {chunk_idx} (sample_rate={sample_rate}, duration={chunk_duration}s)...")
                    t0 = time.time()
                    transcribed_segs = await asyncio.to_thread(transcribe, chunk_path, language="en")
                    whisper_latency = time.time() - t0
                    
                    # Deduplicate overlapping segments using absolute timestamps
                    chunk_offset = total_samples_processed / sample_rate
                    new_segs = []
                    for seg in transcribed_segs:
                        abs_start = chunk_offset + seg["start"]
                        abs_end = chunk_offset + seg["end"]
                        
                        # Use a small tolerance threshold of 0.2s to handle minor alignment differences
                        if abs_end > last_max_end_time + 0.2:
                            seg["start"] = abs_start
                            seg["end"] = abs_end
                            new_segs.append(seg)
                            if abs_end > last_max_end_time:
                                last_max_end_time = abs_end
                                
                    chunk_text = " ".join([seg["text"] for seg in new_segs]).strip()
                    avg_conf = 1.0
                    if new_segs:
                        avg_conf = sum([seg.get("confidence", 1.0) for seg in new_segs]) / len(new_segs)
                        
                    logger.info(
                        f"[WebSocket Pipeline] Chunk {chunk_idx} Whisper transcription latency: {whisper_latency:.2f}s. "
                        f"Found {len(new_segs)} new segments out of {len(transcribed_segs)} total. "
                        f"Avg Transcription Confidence={avg_conf:.4f}. Chunk text: \"{chunk_text or '(Silence/No Speech)'}\""
                    )
                    
                    if chunk_text:
                        start_time = round(chunk_offset, 2)
                        end_time = round(chunk_offset + len(chunk_data)/sample_rate, 2)
                        
                        # Save segment details to database immediately as a placeholder
                        segment_id = await asyncio.to_thread(
                            insert_placeholder_segment_db,
                            meeting_id,
                            chunk_text,
                            start_time,
                            end_time
                        )

                        # Broadcast the new chunk segment immediately with default emotion
                        logger.info(f"[WebSocket Pipeline] Broadcasting raw segment text to client immediately...")
                        await websocket.send_json({
                            "type": "chunk_update",
                            "segment": {
                                "speaker": "Speaker_00",
                                "start": start_time,
                                "end": end_time,
                                "text": chunk_text,
                                "emotion": "Neutral",
                                "explanation": "Analyzing tone and tasks in background..."
                            },
                            "new_tasks": [],
                            "new_events": []
                        })
                        
                        # Spawn background task to process context-emotion, tasks, and database updates in parallel
                        asyncio.create_task(
                            process_chunk_intelligence(
                                meeting_id,
                                segment_id,
                                chunk_path,
                                chunk_text,
                                start_time,
                                end_time,
                                whisper_latency,
                                avg_conf,
                                websocket
                            )
                        )

                except WebSocketDisconnect:
                    raise
                except Exception as chunk_err:
                    logger.error(f"[WebSocket Pipeline] Exception during chunk {chunk_idx} processing: {chunk_err}")
                    traceback.print_exc()

                # Slide the buffer: keep the last overlap_samples
                current_chunk_samples = current_chunk_samples[samples_per_chunk - overlap_samples:]
                
                # Update absolute timeline: we processed (samples_per_chunk - overlap_samples) new samples
                total_samples_processed += (samples_per_chunk - overlap_samples)
                chunk_idx += 1

            # 7. Periodically Run PyAnnote Diarization (Every 16 seconds of audio)
            if total_samples_processed - last_diarization_samples >= sample_rate * 16:
                try:
                    logger.info(f"[WebSocket Background] Running periodic speaker diarization on master file...")
                    diar_segs = await asyncio.to_thread(run_diarization, master_wav_path)
                    if diar_segs:
                        aligned = await asyncio.to_thread(update_diarization_db, meeting_id, diar_segs)
                        
                        # Broadcast resolved speakers
                        resolved_list = [
                            {
                                "speaker": seg["speaker"],
                                "start": seg["start"],
                                "end": seg["end"],
                                "text": seg["text"]
                            }
                            for seg in aligned
                        ]
                        logger.info(f"[WebSocket Background] Diarization completed. Broadcasting aligned transcript updates...")
                        await websocket.send_json({
                            "type": "diarization_update",
                            "transcript": resolved_list
                        })
                except Exception as ex:
                    logger.error(f"[WebSocket Background] Diarization process failed: {ex}")
                    traceback.print_exc()
                
                last_diarization_samples = total_samples_processed

            # 8. Periodically Run Summarization and Atmosphere Tracking (Every 30 seconds of audio)
            if total_samples_processed - last_summary_samples >= sample_rate * 30:
                try:
                    logger.info(f"[WebSocket Background] Running periodic incremental summarization...")
                    new_summary, atmosphere = await asyncio.to_thread(run_periodic_summary_db, meeting_id, running_summary)
                    running_summary = new_summary
                    
                    logger.info(f"[WebSocket Background] Summary updated. Broadcasting updates...")
                    await websocket.send_json({
                        "type": "summary_update",
                        "summary": running_summary,
                        "sentiment": atmosphere
                    })
                except Exception as ex:
                    logger.error(f"[WebSocket Background] Summary process failed: {ex}")
                    traceback.print_exc()
                
                last_summary_samples = total_samples_processed

    except WebSocketDisconnect:
        logger.info(f"[WebSocket] Connection disconnected by client for meeting_id={meeting_id}")
        await finalize_meeting(meeting_id, master_wav_path, running_summary)
    except Exception as e:
        if "WebSocket is not connected" in str(e) or "already closed" in str(e):
            logger.info(f"[WebSocket] Connection closed detected via RuntimeError for meeting_id={meeting_id}")
            await finalize_meeting(meeting_id, master_wav_path, running_summary)
        else:
            logger.error(f"[WebSocket] Exception in websocket connection loop: {e}")
            traceback.print_exc()
            
            # Mark as failed in DB
            try:
                def mark_failed(m_id, err_msg):
                    db_conn = get_connection()
                    db_conn.execute("UPDATE meetings SET status='failed', summary=? WHERE id=?", (err_msg, m_id))
                    db_conn.commit()
                    db_conn.close()
                await asyncio.to_thread(mark_failed, meeting_id, f"PROCESSING_FAILED: {str(e)}")
            except:
                pass
                
            try:
                await websocket.close()
            except:
                pass

async def finalize_meeting(meeting_id: int, wav_path: str, running_summary: str):
    """
    Run final diarization, LLM summarization, build graph, and index in ChromaDB.
    """
    if not os.path.exists(wav_path):
        logger.warning(f"[WebSocket Finalization] Audio WAV file does not exist: {wav_path}. Finalizing meeting as empty.")
        try:
            def finalize_empty(m_id):
                db_conn = get_connection()
                db_conn.execute(
                    "UPDATE meetings SET status='done', summary='No audio or segments recorded.' WHERE id=?",
                    (m_id,)
                )
                db_conn.commit()
                db_conn.close()
            await asyncio.to_thread(finalize_empty, meeting_id)
        except Exception as db_err:
            logger.error(f"[WebSocket Finalization] Failed to write empty state to DB: {db_err}")
        return
        
    try:
        await asyncio.to_thread(compile_and_finalize_meeting_db, meeting_id, running_summary)
        logger.info(f"[WebSocket] Meeting {meeting_id} finalized successfully.")
        
    except Exception as ex:
        logger.error(f"[WebSocket] Failed to finalize meeting {meeting_id}: {ex}")
        traceback.print_exc()
        try:
            def finalize_failed(m_id, err_msg):
                db_conn = get_connection()
                db_conn.execute("UPDATE meetings SET status='failed', summary=? WHERE id=?", (err_msg, m_id))
                db_conn.commit()
                db_conn.close()
            await asyncio.to_thread(finalize_failed, meeting_id, f"PROCESSING_FAILED: {str(ex)}")
        except:
            pass
