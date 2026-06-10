import re
import json
import spacy
from llm_client import ask_llm

# python -m spacy download en_core_web_trf  (transformer-based, most accurate)
# fallback: en_core_web_sm  (faster, less accurate)
try:
    nlp = spacy.load("en_core_web_trf")
except:
    nlp = spacy.load("en_core_web_sm")

# Patterns that hint at a task being assigned
TASK_VERBS = {"prepare", "complete", "submit", "review", "finalize", "draft",
              "send", "create", "build", "test", "fix", "update", "schedule",
              "coordinate", "follow", "ensure", "verify", "check", "analyze"}

DEADLINE_WORDS = {"by", "before", "until", "due", "on", "at", "next"}


def extract_entities(text: str) -> dict:
    """
    Two-pass extraction:
    1. spaCy for named entities (people, dates, orgs)
    2. Local LLM for structured task/decision extraction
    """
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
    prompt = f"""
You are analyzing a meeting transcript. Extract the following in valid JSON only.
No extra text. No markdown.

Transcript:
{text[:4000]}

Return this exact structure:
{{
  "tasks": [
    {{"task": "...", "owner": "...", "deadline": "..."}}
  ],
  "decisions": ["..."],
  "events": [
    {{"title": "...", "date": "...", "time": "...", "participants": ["..."]}}
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


def generate_summary(text: str, extracted: dict) -> str:
    tasks_str     = "\n".join(f"- {t['task']} ({t.get('owner','?')}) by {t.get('deadline','?')}"
                               for t in extracted.get("tasks", []))
    decisions_str = "\n".join(f"- {d}" for d in extracted.get("decisions", []))

    prompt = f"""
Write professional meeting minutes from the transcript below.
Use plain paragraphs. No bullet spam. Be concise.

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
