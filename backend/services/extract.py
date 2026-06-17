import re
import json
from llm_client import ask_llm

# Patterns that hint at a task being assigned
TASK_VERBS = {"prepare", "complete", "submit", "review", "finalize", "draft",
              "send", "create", "build", "test", "fix", "update", "schedule",
              "coordinate", "follow", "ensure", "verify", "check", "analyze"}

DEADLINE_WORDS = {"by", "before", "until", "due", "on", "at", "next"}

_nlp = None

def get_spacy_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_trf")
        except Exception:
            _nlp = spacy.load("en_core_web_sm")
    return _nlp


def extract_entities(text: str) -> dict:
    """
    Two-pass extraction:
    1. spaCy for named entities (people, dates, orgs)
    2. Local LLM for structured task/decision extraction
    """
    nlp = get_spacy_nlp()
    doc = nlp(text)

    people   = list({ent.text for ent in doc.ents if ent.label_ == "PERSON"})
    dates    = list({ent.text for ent in doc.ents if ent.label_ in ("DATE", "TIME")})
    orgs     = list({ent.text for ent in doc.ents if ent.label_ == "ORG"})

    llm_result = _extract_with_llm(text)

    return {
        "people":    people,
        "dates":     dates,
        "orgs":      orgs,
        "tasks":     llm_result.get("tasks", []),
        "decisions": llm_result.get("decisions", []),
        "events":    llm_result.get("events", []),
        "risks":     llm_result.get("risks", []),
        "questions": llm_result.get("open_questions", []),
    }


def _extract_with_llm(text: str) -> dict:
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    day_of_week = datetime.now().strftime("%A")

    prompt = f"""
You are analyzing a meeting transcript. Extract the following in valid JSON only.
No extra text. No markdown.

Today's date is {today_str} ({day_of_week}).
CRITICAL EVENT EXTRACTION INSTRUCTIONS:
1. Actively detect any scheduling phrases such as:
   - "let's meet tomorrow" -> resolve to tomorrow's date
   - "schedule a review" -> create an event
   - "follow-up next week" -> resolve to date +7 days from today
   - "sync on Friday" -> resolve to the date of the upcoming Friday
   - "call at 3 PM" -> resolve start_time to 15:00
2. If the user mentions relative times (like 'tomorrow', 'next week', 'Friday'), calculate the absolute date based on today's date ({today_str}).
3. For each event, you must extract:
   - "title": event name/topic
   - "date": "YYYY-MM-DD"
   - "start_time": "HH:MM" (24h format)
   - "end_time": "HH:MM" (24h format, usually start_time + 1 hour if unspecified)
   - "attendees": list of participant names mentioned or implied

Transcript:
{text[:4000]}

Return this exact structure:
{{
  "tasks": [
    {{"task": "...", "owner": "...", "deadline": "..."}}
  ],
  "decisions": ["..."],
  "events": [
    {{
      "title": "Event title",
      "date": "YYYY-MM-DD",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "attendees": ["Name"]
    }}
  ],
  "risks": ["..."],
  "open_questions": ["..."]
}}
"""
    raw = ask_llm(prompt)

    # strip any accidental markdown fences
    raw = re.sub(r"```[a-z]*", "", raw).strip().strip("`")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # best-effort fallback — return empty rather than crash
        return {}


def generate_summary(text: str, extracted: dict, emotion_context: str = None) -> str:
    tasks_str     = "\n".join(f"- {t['task']} ({t.get('owner','?')}) by {t.get('deadline','?')}"
                               for t in extracted.get("tasks", []))
    decisions_str = "\n".join(f"- {d}" for d in extracted.get("decisions", []))

    emotion_inst = ""
    if emotion_context:
        emotion_inst = f"\nTake into account this emotional context and sentiment profile of the participants to make the summary emotion-aware. Instead of plain facts, note concerns, agreements, frustrations, or excitement when appropriate:\n{emotion_context}\n"

    prompt = f"""
Write professional meeting minutes from the transcript below.
Use plain paragraphs. No bullet spam. Be concise.
{emotion_inst}
Include sections:
1. Summary (2-3 sentences)
2. Key Discussion Points
3. Decisions Taken
4. Action Items
5. Upcoming Meetings
6. Risks and Open Questions

Transcript excerpt:
{text[:5000]}

Known tasks:
{tasks_str or 'None identified'}

Known decisions:
{decisions_str or 'None identified'}
"""
    return ask_llm(prompt)


def extract_incremental_tasks_and_events(text: str, existing_tasks: list = None, existing_events: list = None) -> dict:
    """
    Extract tasks, decisions, events, risks, and open questions from a short transcript segment,
    avoiding duplication of already identified items.
    """
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    day_of_week = datetime.now().strftime("%A")

    existing_tasks_str = ", ".join([t.get("task", "") for t in (existing_tasks or [])])
    existing_events_str = ", ".join([e.get("title", "") for e in (existing_events or [])])
    
    prompt = f"""You are analyzing a new segment of a meeting transcript. Extract new tasks, decisions, calendar events, risks, and open questions.
Do NOT duplicate any tasks or events that have already been identified:
Already Identified Tasks: [{existing_tasks_str}]
Already Identified Events: [{existing_events_str}]

Today's date is {today_str} ({day_of_week}).
CRITICAL EVENT EXTRACTION INSTRUCTIONS:
1. Actively detect any scheduling phrases such as:
   - "let's meet tomorrow" -> resolve to tomorrow's date
   - "schedule a review" -> create an event
   - "follow-up next week" -> resolve to date +7 days from today
   - "sync on Friday" -> resolve to the date of the upcoming Friday
   - "call at 3 PM" -> resolve start_time to 15:00
2. If the user mentions relative times (like 'tomorrow', 'next week', 'Friday'), calculate the absolute date based on today's date ({today_str}).
3. For each event, you must extract:
   - "title": event name/topic
   - "date": "YYYY-MM-DD"
   - "start_time": "HH:MM" (24h format)
   - "end_time": "HH:MM" (24h format, usually start_time + 1 hour if unspecified)
   - "attendees": list of participant names mentioned or implied

Transcript segment:
{text}

Return the extracted details in valid JSON ONLY. No markdown wrapper, no extra text.
Exact JSON structure:
{{
  "tasks": [
    {{"task": "Description of new task", "owner": "Name or Unassigned", "deadline": "Date/Time/Day or Unassigned"}}
  ],
  "decisions": ["New decision statement"],
  "events": [
    {{
      "title": "Event title",
      "date": "YYYY-MM-DD",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "attendees": ["Name"]
    }}
  ],
  "risks": ["New identified risk"],
  "open_questions": ["New open question"]
}}
"""
    raw = ask_llm(prompt)
    raw = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"tasks": [], "decisions": [], "events": [], "risks": [], "open_questions": []}


def generate_incremental_summary(previous_summary: str, new_text: str, emotion_trend: str = None) -> str:
    """
    Update a running meeting summary using the previous summary and the new transcript context.
    """
    if not previous_summary or previous_summary.startswith("PROCESSING_FAILED") or "Summary" not in previous_summary:
        return generate_summary(new_text, {}, emotion_trend)

    emotion_inst = ""
    if emotion_trend:
        emotion_inst = f"\nTake into account this recent emotional trend and sentiment of the participants:\n{emotion_trend}\n"

    prompt = f"""You are updating a live running meeting summary.
You have the existing summary, and a new transcript segment representing the last minute of conversation.{emotion_inst}
Incorporate the new details (new discussions, action items, decisions, or emotional atmosphere shifts) into the existing summary structure.
Preserve the previous context. Do not erase major prior points unless they were modified or corrected in the new transcript.

Previous Summary:
{previous_summary}

New Transcript Segment:
{new_text}

Return the updated meeting minutes in the same structure:
1. Summary (2-3 sentences)
2. Key Discussion Points
3. Decisions Taken
4. Action Items
5. Upcoming Meetings
6. Risks and Open Questions

Provide only the plain text of the updated summary. No extra conversational text.
"""
    return ask_llm(prompt)


def analyze_meeting_atmosphere(segments: list) -> dict:
    """
    Analyze the overall emotional trend and sentiment of the meeting.
    Accepts segments list of dicts: {"speaker": str, "text": str, "emotion": str, "confidence": float}
    """
    if not segments:
        return {
            "meeting_sentiment": "Neutral",
            "dominant_emotion": "Neutral",
            "confidence": 1.0,
            "observations": ["No conversation recorded yet."]
        }

    import numpy as np
    from collections import Counter

    # 1. Programmatically filter recent segments (last 30 seconds of audio)
    last_time = 0.0
    for s in reversed(segments):
        val = s.get("end_time") or s.get("end") or s.get("end_time")
        if val is not None:
            try:
                last_time = float(val)
                break
            except Exception:
                pass
            
    recent_segs = []
    if last_time > 0:
        recent_segs = [s for s in segments if float(s.get("end_time") or s.get("end") or 0) > last_time - 30]
    
    # Fallback to the last 10 segments if recent_segs is too small
    if len(recent_segs) < 3:
        recent_segs = segments[-10:]

    emotions = []
    confidences = []
    for s in recent_segs:
        emo = s.get("context_emotion") or s.get("emotion") or "Neutral"
        conf = s.get("context_emotion_confidence") or s.get("emotion_confidence") or s.get("confidence") or 1.0
        emotions.append(emo)
        confidences.append(conf)

    emotion_counts = Counter(emotions)
    dominant_emotion = emotion_counts.most_common(1)[0][0] if emotions else "Neutral"

    # Map emotions to sentiments: Positive/Neutral/Negative
    sentiment_map = {
        "Excited": "Positive", "Happy": "Positive", "Confident": "Positive",
        "Angry": "Negative", "Frustrated": "Negative", "Worried": "Negative", "Sad": "Negative",
        "Neutral": "Neutral", "Uncertain": "Neutral", "Hesitant": "Neutral"
    }
    sentiments = [sentiment_map.get(e, "Neutral") for e in emotions]
    sentiment_counts = Counter(sentiments)
    meeting_sentiment = sentiment_counts.most_common(1)[0][0] if sentiments else "Neutral"

    avg_confidence = round(float(np.mean(confidences)), 2) if confidences else 1.0

    # 2. Query LLM to generate short text observations based on these calculated metrics
    formatted_segs = []
    for s in recent_segs:
        text = s.get("text", "").strip()
        speaker = s.get("speaker", "Unknown")
        tone = s.get("context_emotion") or s.get("emotion") or "Neutral"
        if text:
            formatted_segs.append(f"{speaker}: \"{text}\" [Tone: {tone}]")
    segs_str = "\n".join(formatted_segs)

    prompt = f"""You are analyzing a meeting's atmosphere.
Recent transcript segments:
{segs_str}

Calculated Metrics:
- Dominant Emotion: {dominant_emotion}
- Overall Sentiment: {meeting_sentiment}
- Average Confidence: {avg_confidence}

Based on this, output 2 short bullet-point observations (1 sentence each) about the discussion tone, participant mood, or sentiment shift.
Return ONLY a valid JSON list of strings. Do not include markdown tags or extra characters.
Example:
[
  "The speaker expressed confidence about the project timelines.",
  "Some hesitation was noted during the task delegation."
]
"""
    observations = []
    try:
        raw = ask_llm(prompt, max_tokens=256)
        raw = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        data = json.loads(raw)
        if isinstance(data, list):
            observations = [str(x) for x in data]
    except Exception as e:
        print(f"[Atmosphere Service] LLM observations failed: {e}")

    if not observations:
        observations = [
            f"Dominant tone detected as {dominant_emotion}.",
            f"Overall sentiment trend is {meeting_sentiment}."
        ]

    return {
        "meeting_sentiment": meeting_sentiment,
        "dominant_emotion": dominant_emotion,
        "confidence": avg_confidence,
        "observations": observations
    }


def answer_meeting_query(transcript: list, tasks: list, query: str) -> str:
    """
    Answer a user's question about the meeting using the transcript and tasks as context.
    """
    formatted_transcript = []
    for t in transcript:
        formatted_transcript.append(f"{t.get('speaker', 'Unknown')}: {t.get('text', '')}")
    
    # Select the most recent segments that fit within our 5000 character limit
    total_len = 0
    selected_segments = []
    for segment in reversed(formatted_transcript):
        if total_len + len(segment) + 1 > 5000:
            break
        selected_segments.append(segment)
        total_len += len(segment) + 1
    
    transcript_str = "\n".join(reversed(selected_segments))
    
    print(f"[Q&A Service] Running query '{query}'. Selected {len(selected_segments)} out of {len(formatted_transcript)} segments. Context size: {len(transcript_str)} chars.")

    tasks_str = "\n".join([f"- Task: {t.get('task')} (Owner: {t.get('owner')}, Deadline: {t.get('deadline')}, Status: {t.get('status')})" for t in tasks])

    prompt = f"""You are a helpful meeting assistant. Answer the user's question based ONLY on the meeting transcript and extracted tasks below.
If the information is not present, say "I cannot find that in this meeting's context."
Keep your answer clear, direct, and concise (at most 2-3 sentences).

Transcript:
{transcript_str}

Extracted Tasks:
{tasks_str or 'None'}

User Question:
"{query}"

Answer:
"""
    return ask_llm(prompt, max_tokens=512)
