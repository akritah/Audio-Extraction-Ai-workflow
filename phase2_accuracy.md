# Phase 2: Accuracy Improvements

A reference doc for planned upgrades. Each section describes the problem, the
method, and why it works better than the Phase 1 baseline.

---

## 1. Transcription Accuracy

### Problem
Faster-Whisper with `medium` on CPU produces ~5-8% word error rate on clean
audio. Technical jargon, acronyms, and domain-specific terms (e.g. "DRDO",
"RAG", "HAPS") get misrecognized.

### Fixes

**Domain vocabulary injection**
Whisper accepts an `initial_prompt` string that biases the decoder toward
expected vocabulary. Before transcribing, build a prompt from known terms:

```python
domain_prompt = (
    "Meeting notes. DRDO, AI, ML, NLP, HAPS, RAG, YOLOv8, "
    "FastAPI, PyTorch, surveillance, UAV."
)
segments, _ = model.transcribe(audio, initial_prompt=domain_prompt)
```

**VAD tuning**
Silero VAD (used inside Whisper via `vad_filter=True`) removes silence before
feeding audio to the encoder. Tighten thresholds for meeting audio where
pauses are frequent but short:

```python
vad_parameters={
    "threshold": 0.4,           # lower = more sensitive
    "min_speech_duration_ms": 100,
    "min_silence_duration_ms": 300,
}
```

**Large-v3 on GPU**
If a GPU (even a 4GB one) is available, `large-v3` halves the WER vs `medium`
with no code changes. Set `WHISPER_MODEL=large-v3` and `WHISPER_DEVICE=cuda`
in .env.

---

## 2. Speaker Diarization Accuracy

### Problem
pyannote's out-of-the-box model confuses speakers who sound similar, and
over-segments short utterances.

### Fix 1: Speaker count hint
If the number of participants is known (e.g. from a meeting calendar entry),
pass it to the pipeline. Locking `num_speakers` eliminates a major source of
over-segmentation:

```python
diarization = pipeline(audio_path, num_speakers=4)
```

### Fix 2: Minimum segment duration filter
After diarization, merge segments shorter than 1.5 seconds into neighbors.
Short segments are almost always mis-attributed fragments.

```python
def merge_short(segs, min_sec=1.5):
    merged = []
    for seg in segs:
        if merged and seg["end"] - seg["start"] < min_sec:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(seg)
    return merged
```

### Fix 3: Speaker enrollment (out-of-the-box upgrade path)
If short reference audio clips are available for known participants (even 10-20
seconds from a previous meeting), create speaker embeddings using pyannote's
`SpeakerEmbedding` pipeline and compute cosine distance to label clusters.
This turns "SPEAKER_00" into "Rahul" automatically.

```python
from pyannote.audio import Inference

embedding_model = Inference("pyannote/embedding", window="whole")
ref_embedding   = embedding_model("rahul_voice_sample.wav")
# compare against cluster centroids after diarization
```

---

## 3. Information Extraction Accuracy

### Problem
The LLM sometimes misses tasks described indirectly ("we need to look at the
pipeline before Friday") or confuses deadlines (relative dates like "next
Monday" are not resolved to actual calendar dates).

### Fix 1: Relative date normalization
After extraction, pass detected date strings through `dateparser`:

```python
import dateparser
parsed = dateparser.parse("next Monday", settings={"PREFER_DATES_FROM": "future"})
deadline = parsed.strftime("%Y-%m-%d") if parsed else raw_string
```

### Fix 2: Multi-pass extraction
Run extraction twice — once on the full transcript, once on just the last 20%
(closing remarks often contain most of the action items). Merge and deduplicate.

### Fix 3: Confidence scoring
Add a field `confidence: low/medium/high` to each extracted task based on:
- Whether an explicit person name is present → +1
- Whether a concrete deadline was found    → +1
- Whether a clear action verb was used     → +1

Surface low-confidence items separately in the UI so a human can verify them.
This is a lightweight form of human-in-the-loop validation.

---

## 4. Semantic Search Accuracy

### Problem
`all-MiniLM-L6-v2` is a lightweight model (80MB) but struggles with technical
vocabulary and short queries.

### Fix 1: Larger embedding model
Swap to `all-mpnet-base-v2` (420MB) for ~15% better retrieval precision with
modest RAM increase. Change one line in `services/search.py`:

```python
_embedder = SentenceTransformer("all-mpnet-base-v2")
```

### Fix 2: Hybrid search (keyword + semantic)
For queries like "show tasks for Priya" the keyword "Priya" is more useful
than a semantic vector. Add a BM25 keyword pass over SQLite FTS alongside
the ChromaDB vector search, then merge results with reciprocal rank fusion:

```python
# SQLite FTS setup (run once)
conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, meeting_id)")

# at index time
conn.execute("INSERT INTO fts VALUES (?, ?)", (chunk_text, meeting_id))

# at query time
keyword_hits = conn.execute("SELECT * FROM fts WHERE fts MATCH ?", (query,)).fetchall()
# merge with semantic_hits using score = 1/(k + rank)
```

### Fix 3: Chunk overlap increase
Increasing overlap from 50% to 70% means contextually related sentences are
more likely to appear in the same chunk, improving coherence of retrieved
results for multi-sentence queries.

---

## Out-of-the-Box Idea: Speaker Affect Detection

During Phase 1 the system extracts *what* was said. A natural Phase 2 upgrade
is to also capture *how* it was said.

Using `librosa` feature extraction (pitch variance, speech rate, energy) on
per-speaker audio segments, a simple classifier can tag segments as:
- **Assertive** — likely a decision or directive
- **Questioning** — likely an open question
- **Uncertain** — low-confidence claim, worth flagging

This is not sentiment analysis (which is unreliable for meeting audio).
It is prosodic feature-based affect tagging — a technique used in
call centre analytics research and applicable to defence briefing analysis.

Implementation sketch:

```python
import librosa
import numpy as np

def prosodic_features(audio_segment, sr=16000):
    pitch,  _  = librosa.piptrack(y=audio_segment, sr=sr)
    energy     = np.mean(librosa.feature.rms(y=audio_segment))
    tempo, _   = librosa.beat.beat_track(y=audio_segment, sr=sr)
    return {
        "pitch_mean":   float(np.mean(pitch[pitch > 0])),
        "pitch_std":    float(np.std(pitch[pitch > 0])),
        "energy":       float(energy),
        "speech_rate":  float(tempo),
    }
```

These features can be used to weight extraction confidence — a directive
spoken with high energy and steady pitch is more likely to be a real task
assignment than the same sentence spoken hesitatingly.

This is genuinely research-level for a second-year project and maps well
to DRDO's interest in intelligence processing from communications.
