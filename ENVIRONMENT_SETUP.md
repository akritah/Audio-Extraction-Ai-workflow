# Environment Setup Guide

This guide describes how to install and initialize the Real-Time Meeting Intelligence platform on a clean machine.

---

## 1. Prerequisites & Required Software

Install the software below in the specified order:

### 1.1 Python 3.12
* **Purpose**: Runs the backend FastAPI server and local AI processing scripts.
* **Verification**: Open a terminal and run `python --version`. It must output `Python 3.12.x`.

### 1.2 Node.js 18 or 20 (LTS)
* **Purpose**: Runs the Next.js React frontend development server.
* **Verification**: Run `node -v` and `npm -v`. It should show `v18.x.x` or `v20.x.x`.

### 1.3 Git
* **Purpose**: Manages code changes and fetches repository files.
* **Verification**: Run `git --version` to verify it is installed.

### 1.4 Ollama
* **Purpose**: Serves local Large Language Models (LLMs) on CPU/GPU.
* **Installation**: Download from [ollama.com](https://ollama.com) and install the application.
* **Verification**: Run `ollama --version` in your terminal.

---

## 2. Local LLM Setup (Ollama)

The backend uses a local LLM to refine emotions, extract action items, and synthesize RAG memory search queries.

1. **Start the Ollama Service**:
   Run `ollama serve` (if not already running in the background as a system tray agent).
2. **Download Model**:
   Download the lightweight 4.3B parameter model by running:
   ```bash
   ollama pull gemma3:4b
   ```
3. **Verify Model is Loaded**:
   Run `ollama list`. The model `gemma3:4b` must show up in the output list.

---

## 3. Backend Setup

The backend handles audio ingestion, database storage, speech pipelines, and automation.

### 3.1 Set Up Virtual Environment
1. Navigate to the `backend` folder:
   ```bash
   cd backend
   ```
2. Create a Python virtual environment:
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   * **Windows (PowerShell)**: `.\venv\Scripts\Activate.ps1`
   * **Windows (CMD)**: `.\venv\Scripts\activate.bat`
   * **Linux/macOS**: `source venv/bin/activate`

### 3.2 Install Python Dependencies
Install dependencies with locked versions:
```bash
pip install -r requirements.txt
```
* **Dependency Purpose & Verification Table**:
  | Dependency | Purpose | Verification Command |
  | :--- | :--- | :--- |
  | `fastapi` | REST & WebSocket API Framework | `python -c "import fastapi; print(fastapi.__version__)"` |
  | `faster-whisper` | Local Speech-to-Text inference | `python -c "import faster_whisper; print('Whisper ready')"` |
  | `pyannote.audio` | Local Speaker Diarization | `python -c "import pyannote.audio; print('Pyannote ready')"` |
  | `transformers` | Runs the Wav2Vec2 emotion model | `python -c "import transformers; print('Transformers ready')"` |
  | `sentence-transformers`| Generates semantic vectors | `python -c "import sentence_transformers; print('Embedder ready')"` |
  | `chromadb` | Vector database for RAG context | `python -c "import chromadb; print(chromadb.__version__)"` |
  | `dateparser` | Resolves relative/natural language dates | `python -c "import dateparser; print(dateparser.__version__)"` |

### 3.3 Install spaCy Pipeline
Download the core English tokenizer/tagger needed for entity extraction:
```bash
python -m spacy download en_core_web_sm
```

### 3.4 Configure Environment Variables
Create a file named `.env` in the root of the workspace ([.env](file:///c:/DRDO%20audio%20workflow/.env)) and add the following lines:

```env
# Hugging Face Access Token (Required to download PyAnnote speaker diarization model)
HF_TOKEN=your_huggingface_token_here

# Whisper model config (small is lightweight and CPU-friendly)
WHISPER_MODEL=small
WHISPER_DEVICE=cpu

# Local Ollama config
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b

# Webhook URLs for Make.com integrations
MAKE_GMAIL_WEBHOOK_URL=https://hook.us1.make.com/your-gmail-hook-id
MAKE_CALENDAR_WEBHOOK_URL=https://hook.us1.make.com/your-calendar-hook-id
BACKEND_BASE_URL=http://localhost:8000
```

### 3.5 Initialize Databases
Create tables and run alterations in SQLite:
```bash
python -c "import sys; sys.path.append('.'); from db.setup import init_db; init_db()"
```
This creates the SQLite database file at `backend/data/meetings.db`.

---

## 4. Frontend Setup

1. Open a new terminal and navigate to the `frontend` folder:
   ```bash
   cd frontend
   ```
2. Install npm packages:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
   *The frontend will run at `http://localhost:3000`.*

---

## 5. Webhook Setup on Make.com

To see automations working in real-time, configure two scenarios on Make.com:

### 5.1 Gmail / Summary Scenario
1. Create a new scenario in Make.com and add a **Webhooks -> Custom Webhook** module.
2. Generate a webhook URL, copy it, and paste it as `MAKE_GMAIL_WEBHOOK_URL` in your `.env` file.
3. Add a **Gmail -> Send an Email** module. Connect your account.
4. Set the **To** address to your email, the **Subject** to `Meeting Summary: {{title}}`, and the **Body** to `{{summary}}`.

### 5.2 Google Calendar Scenario
1. Create a second scenario and add a **Webhooks -> Custom Webhook** module.
2. Copy the URL and paste it as `MAKE_CALENDAR_WEBHOOK_URL` in your `.env` file.
3. Add a **Google Calendar -> Create an Event** module. Connect your Google account.
4. Map the fields:
   * **Event Name**: `{{title}}`
   * **Start Date**: `{{date}} {{start_time}}`
   * **End Date**: `{{date}} {{end_time}}`
   * **Attendees**: `{{attendees}}`

---

## 6. Startup & Validation Checklist

1. [ ] **Ollama**: Ensure `ollama serve` is running and `gemma3:4b` is downloaded.
2. [ ] **Backend**: Run `python main.py` in the `backend` directory. Confirm it prints `INFO: Uvicorn running on http://0.0.0.0:8000`.
3. [ ] **Frontend**: Start `npm run dev` in the `frontend` directory. Confirm it is reachable at `http://localhost:3000`.
4. [ ] **Test Webhooks**: Run the following testing script in the backend virtual environment to check webhook outputs:
   ```bash
   python -c "import requests; print('Gmail:', requests.post('http://localhost:8000/automations/test/gmail').json()); print('Calendar:', requests.post('http://localhost:8000/automations/test/calendar').json())"
   ```
   *Confirm both return `200` success responses.*
