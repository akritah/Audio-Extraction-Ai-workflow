# Troubleshooting Guide

This guide describes how to identify, verify, and resolve common issues encountered when running the platform.

---

## 1. Web Service & Connection Issues

### 1.1 Backend Startup Port Conflict (`[Errno 10048]`)
* **Symptom**: The backend fails to start and outputs: `ERROR: [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)`.
* **Likely Cause**: A stale Uvicorn or Python process is still running and holding port 8000.
* **How to Verify**: Run the following command in PowerShell to locate the PID listening on port 8000:
  ```powershell
  netstat -aon | findstr :8000
  ```
* **How to Fix**: Kill the process using the PID found in the command above:
  ```powershell
  Stop-Process -Id <PID> -Force
  ```

### 1.2 WebSocket Disconnects Prematurely
* **Symptom**: The live transcription interface disconnects immediately upon starting a meeting, showing a closed socket error in the browser console.
* **Likely Cause**: The frontend requested a live session for a `meeting_id` that is not present in SQLite, or there is a database path mismatch.
* **How to Verify**: Inspect the backend logs for `[WebSocket] Verification failed: meeting_id=XX not found. Closing connection.`
* **How to Fix**: Ensure that the meeting is started through the UI (which triggers a POST request to `/live/start` to insert the meeting row) before initiating the WebSocket stream at `/ws/live/{meeting_id}`.

### 1.3 frontend Startup Failure (`next-dev` loop or build errors)
* **Symptom**: Running `npm run dev` in the `frontend` folder exits immediately or hangs with TypeScript errors.
* **Likely Cause**: Missing node packages or version mismatch in the lockfile.
* **How to Verify**: Check the terminal output for compiler warnings or missing import paths (e.g. `d3` or `react-force-graph`).
* **How to Fix**: Clear `node_modules` and force install packages:
  ```bash
  cd frontend
  rm -rf node_modules .next
  npm install
  npm run dev
  ```

---

## 2. Audio & Transcription Issues

### 2.1 Audio Streams Not Transcribing (Silence loops)
* **Symptom**: The browser connects to the WebSocket, but the transcript shows nothing, and the backend logs packet sizes of `0 samples` or `Empty payload`.
* **Likely Cause**: The browser does not have microphone permissions, or the audio device is sending empty buffers.
* **How to Verify**: Open the browser developer console (F12) and inspect if the audio worklet is capturing and streaming float array buffers.
* **How to Fix**: Grant microphone permission to the application in the browser settings and reload the page.

### 2.2 Whisper VAD Filtering Out Real Speech
* **Symptom**: Speech is spoken clearly, but Whisper transcribes nothing or omits large sections.
* **Likely Cause**: The Voice Activity Detection (VAD) filter is configured too aggressively, treating quiet speaking as silence.
* **How to Verify**: Check the parameters set in [transcribe.py](file:///c:/DRDO%20audio%20workflow/backend/services/transcribe.py) inside the `model.transcribe` call:
  ```python
  vad_parameters={"min_silence_duration_ms": 500}
  ```
* **How to Fix**: Increase the silence duration threshold or adjust the VAD activation threshold by tweaking `vad_parameters` inside [transcribe.py](file:///c:/DRDO%20audio%20workflow/backend/services/transcribe.py):
  ```python
  vad_parameters={"threshold": 0.3, "min_silence_duration_ms": 1000}
  ```

---

## 3. Local LLM & Ollama Failures

### 3.1 Ollama Read Timeouts (120s Timeout)
* **Symptom**: Backend logs show `LLM call failed: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120)`.
* **Likely Cause**: Ollama is congested by too many parallel prompts running on CPU, or the model takes too long to generate tokens.
* **How to Verify**: Run `ollama ps` to see if a model is currently running and occupying 100% CPU.
* **How to Fix**:
  * Kill any stale Ollama loops on your machine.
  * The backend has built-in throttling: it bypasses LLM contextual emotion calls on segments with $< 8$ words. Ensure this filter is active in [live.py](file:///c:/DRDO%20audio%20workflow/backend/routers/live.py).
  * Truncate the size of retrieved documents passed to LLM prompts. In [search.py](file:///c:/DRDO%20audio%20workflow/backend/routers/search.py), the retrieval context is capped at `5000` characters to prevent long pre-fill evaluations.

### 3.2 Ollama Connection Errors
* **Symptom**: The backend raises `RuntimeError: Ollama is not running. Start it with: ollama serve`.
* **Likely Cause**: The Ollama service is stopped or port 11434 is blocked.
* **How to Verify**: Open your browser and navigate to `http://localhost:11434`. It should output `Ollama is running`.
* **How to Fix**: Start the Ollama background daemon or run `ollama serve` in a new terminal window.

---

## 4. Machine Learning & Database Failures

### 4.1 PyTorch & NumPy Conflicts (NotImplementedError)
* **Symptom**: The backend crashes during meeting finalization (ChromaDB indexing) with `NotImplementedError: Cannot copy out of meta tensor; no data!`.
* **Likely Cause**: PyTorch 2.3.0 has binary incompatibilities with NumPy 2.x.
* **How to Verify**: Run this command to check the installed NumPy version in the virtual environment:
  ```powershell
  venv\Scripts\pip.exe show numpy
  ```
* **How to Fix**: Downgrade NumPy to a version under 2.0.0 (version `1.26.4` is verified compatible):
  ```powershell
  venv\Scripts\pip.exe install "numpy==1.26.4"
  ```

### 4.2 SQLite Database Locking (`database is locked`)
* **Symptom**: Parallel read/write operations fail with `sqlite3.OperationalError: database is locked`.
* **Likely Cause**: SQLite is attempting concurrent writes while in default rollback journal mode.
* **How to Verify**: Query the database journal mode:
  ```powershell
  venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('backend/data/meetings.db'); print(conn.execute('PRAGMA journal_mode;').fetchone())"
  ```
* **How to Fix**: Ensure that Write-Ahead Logging (WAL) is enabled. In [setup.py](file:///c:/DRDO%20audio%20workflow/backend/db/setup.py), verify that:
  ```python
  conn = sqlite3.connect(DB_PATH, timeout=10.0)
  conn.execute("PRAGMA journal_mode=WAL;")
  ```
  Is executed on every connection.

### 4.3 ChromaDB Initialization Warnings
* **Symptom**: Startup displays warnings about deprecated parameters or DB lock errors.
* **Likely Cause**: Stale/corrupt persistent files in `backend/data/chroma`.
* **How to Verify**: Check the files inside `backend/data/chroma`.
* **How to Fix**: Delete the chroma directory to force a clean re-initialization (meeting vectors will automatically re-index from SQLite segments on finalization):
  ```powershell
  Remove-Item -Recurse -Force backend/data/chroma
  ```

---

## 5. Webhook & Automation Failures

### 5.1 Webhooks Fails silently
* **Symptom**: Meetings complete, but no email is sent, and no calendar event is created, and there are no backend errors.
* **Likely Cause**: `MAKE_GMAIL_WEBHOOK_URL` or `MAKE_CALENDAR_WEBHOOK_URL` environment variables are empty or missing in `.env`.
* **How to Verify**: Check the SQLite `automation_logs` table. If it is empty, no webhook was triggered.
* **How to Fix**: Make sure your `.env` contains valid Make.com URLs (not httpbin mock links) and restart the server.

### 5.2 Calendar Webhook Skipping Events
* **Symptom**: The backend logs `[Automation] Event 'XXX' is a duplicate. Skipping.`
* **Likely Cause**: The event was already extracted from a previous audio chunk in the same meeting.
* **How to Verify**: Check the `calendar_events` table for rows matching the event title, date, and time:
  ```powershell
  venv\Scripts\python.exe -c "import sqlite3; conn=sqlite3.connect('backend/data/meetings.db'); print(conn.execute('SELECT title FROM calendar_events').fetchall())"
  ```
* **How to Fix**: This is the intended deduplication behavior. If you want to force re-extraction, delete the row from the `calendar_events` table using its ID.
