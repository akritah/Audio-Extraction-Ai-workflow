import sqlite3
import chromadb
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "meetings.db")
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(CHROMA_PATH, exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT NOT NULL,
            title       TEXT,
            date        TEXT,
            duration    REAL,
            transcript  TEXT,
            summary     TEXT,
            status      TEXT DEFAULT 'active',
            sentiment   TEXT,
            dominant_emotion TEXT,
            sentiment_confidence REAL,
            sentiment_observations TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id  INTEGER REFERENCES meetings(id),
            task        TEXT NOT NULL,
            owner       TEXT,
            deadline    TEXT,
            status      TEXT DEFAULT 'Pending',
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id  INTEGER REFERENCES meetings(id),
            decision    TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS speakers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id  INTEGER REFERENCES meetings(id),
            speaker     TEXT,
            start_time  REAL,
            end_time    REAL,
            text        TEXT,
            emotion     TEXT,
            emotion_confidence REAL,
            context_emotion TEXT,
            context_explanation TEXT,
            context_emotion_confidence REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id   INTEGER REFERENCES meetings(id),
            title        TEXT,
            event_date   TEXT,
            event_time   TEXT,
            end_time     TEXT,
            duration_min INTEGER DEFAULT 60,
            participants TEXT,
            ics_path     TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS automation_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id      INTEGER REFERENCES meetings(id),
            automation_type TEXT NOT NULL,
            payload         TEXT NOT NULL,
            status          TEXT NOT NULL,
            response_code   INTEGER,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # Apply ALTER TABLE migrations for existing databases
    alterations = [
        ("meetings", "status", "TEXT DEFAULT 'active'"),
        ("meetings", "sentiment", "TEXT"),
        ("meetings", "dominant_emotion", "TEXT"),
        ("meetings", "sentiment_confidence", "REAL"),
        ("meetings", "sentiment_observations", "TEXT"),
        ("speakers", "emotion", "TEXT"),
        ("speakers", "emotion_confidence", "REAL"),
        ("speakers", "context_emotion", "TEXT"),
        ("speakers", "context_explanation", "TEXT"),
        ("speakers", "context_emotion_confidence", "REAL"),
        ("calendar_events", "end_time", "TEXT")
    ]

    for table, column, col_type in alterations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            # Column already exists
            pass

    conn.commit()
    conn.close()


_chroma_client = None
_collection = None


def init_chroma():
    global _chroma_client, _collection
    _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    _collection = _chroma_client.get_or_create_collection(
        name="meeting_chunks",
        metadata={"hnsw:space": "cosine"}
    )


def get_collection():
    global _collection
    if _collection is None:
        init_chroma()
    return _collection
