import re
import json
from fastapi import APIRouter, Query
from db.setup import get_connection
from services.search import search as semantic_search
from llm_client import ask_llm

router = APIRouter()


@router.get("/")
def search(q: str = Query(..., min_length=2), top_k: int = 10):
    """
    Semantic search over all indexed meetings.
    Returns matching chunks with meeting metadata.
    """
    hits = semantic_search(q, top_k=top_k)

    # enrich each hit with meeting title/filename
    conn  = get_connection()
    cache = {}
    for h in hits:
        mid = h.get("meeting_id")
        if mid and mid not in cache:
            row = conn.execute(
                "SELECT filename, title, created_at FROM meetings WHERE id=?", (mid,)
            ).fetchone()
            cache[mid] = dict(row) if row else {}
        h["meeting"] = cache.get(mid, {})

    conn.close()
    return hits


@router.get("/memory")
def query_memory(q: str = Query(..., min_length=2)):
    """
    Translates a natural language question about past meetings/tasks/decisions
    into SQLite queries and ChromaDB vector queries, executing them securely,
    and synthesizing a natural language answer.
    """
    # 1. Ask LLM to generate SQL & semantic search parameters
    prompt = f"""You are translating a natural language query about meeting history/memory into SQLite SELECT queries and semantic search queries.
We have the following database schema:

Table: meetings
- id (INTEGER, PRIMARY KEY)
- title (TEXT)
- filename (TEXT)
- summary (TEXT)
- sentiment (TEXT: 'Positive', 'Negative', 'Neutral')
- dominant_emotion (TEXT)
- created_at (TEXT)

Table: tasks
- id (INTEGER, PRIMARY KEY)
- meeting_id (INTEGER, foreign key)
- task (TEXT)
- owner (TEXT)
- deadline (TEXT)
- status (TEXT: 'Pending', 'Done')

Table: speakers
- id (INTEGER, PRIMARY KEY)
- meeting_id (INTEGER, foreign key)
- speaker (TEXT)
- text (TEXT)
- emotion (TEXT)
- emotion_confidence (REAL)
- context_emotion (TEXT)
- context_explanation (TEXT)
- context_emotion_confidence (REAL)

CRITICAL INSTRUCTIONS:
1. The current year is 2026. If the user refers to dates, write SQL matching the year 2026 (or relative dates).
2. ALWAYS provide a "semantic_query" (never null) if the user is asking about discussions, topics, what someone said, tasks, or decisions.
3. If the user is asking about what was discussed or spoken, write at least one SQL query querying the `speakers` table using `LIKE` on the `text` column, in addition to the semantic query.
4. Keep SQL queries simple, safe, and clean. Use `%keyword%` for text searches.

Return ONLY a valid JSON object. Do not wrap in markdown ```json or include any explanation.

JSON structure:
{{
  "sql_queries": ["SELECT ..."],
  "semantic_query": "..." or null
}}

Few-Shot Examples:

User Query: "who will handle the next meeting?"
Plan:
{{
  "sql_queries": [
    "SELECT task, owner, deadline FROM tasks WHERE task LIKE '%next meeting%' OR task LIKE '%handle%'",
    "SELECT speaker, text FROM speakers WHERE text LIKE '%next meeting%' OR text LIKE '%handle%'"
  ],
  "semantic_query": "who will handle the next meeting"
}}

User Query: "What did we discuss about flexible working plans?"
Plan:
{{
  "sql_queries": [
    "SELECT speaker, text FROM speakers WHERE text LIKE '%flexible working%'"
  ],
  "semantic_query": "flexible working plans"
}}

User Query: "did we discuss any new things on 23rd June?"
Plan:
{{
  "sql_queries": [
    "SELECT m.id, m.title, m.summary FROM meetings m WHERE m.created_at LIKE '%-06-23%'",
    "SELECT s.text FROM speakers s JOIN meetings m ON s.meeting_id = m.id WHERE m.created_at LIKE '%-06-23%'"
  ],
  "semantic_query": "discussions about new things on June 23rd"
}}

User Query: "{q}"
Plan:
"""
    try:
        raw = ask_llm(prompt)
        raw = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        plans = json.loads(raw)
    except Exception as e:
        print(f"[Memory Query] LLM parsing failed: {e}")
        # fallback plan if LLM parsing fails
        plans = {
            "sql_queries": ["SELECT * FROM tasks WHERE status != 'Done' LIMIT 10"],
            "semantic_query": q
        }

    # 2. Execute SQL queries and gather data
    retrieved_data = []
    for sql in plans.get("sql_queries", []):
        try:
            # Safety checks to prevent SQL injections or write operations
            sql_upper = sql.upper().strip()
            if not sql_upper.startswith("SELECT"):
                continue
            forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE", "TRUNCATE"]
            if any(f in sql_upper for f in forbidden):
                continue
            
            conn = get_connection()
            rows = conn.execute(sql).fetchall()
            conn.close()
            retrieved_data.append({"source": "SQL Query: " + sql, "results": [dict(r) for r in rows[:15]]})
        except Exception as sql_err:
            print(f"[Memory Query] SQL failed for query '{sql}': {sql_err}")

    # 3. Execute semantic search
    semantic_q = plans.get("semantic_query")
    if semantic_q:
        try:
            hits = semantic_search(semantic_q, top_k=5)
            # enrich hits with basic filename/title
            conn = get_connection()
            cache = {}
            for h in hits:
                mid = h.get("meeting_id")
                if mid and mid not in cache:
                    row = conn.execute(
                        "SELECT filename, title, created_at FROM meetings WHERE id=?", (mid,)
                    ).fetchone()
                    cache[mid] = dict(row) if row else {}
                h["meeting"] = cache.get(mid, {})
            conn.close()
            retrieved_data.append({"source": "Vector Semantic Search: " + semantic_q, "results": hits})
        except Exception as sem_err:
            print(f"[Memory Query] Semantic search failed: {sem_err}")

    # 4. Synthesize final answer using LLM
    context_str = json.dumps(retrieved_data, default=str)[:5000] # avoid bloating context window
    
    synthesize_prompt = f"""You are a meeting intelligence memory assistant.
Answer the user's natural language query based on the database records retrieved.
Provide dates and specific meeting titles where applicable.
If the records do not contain the answer, explain what was found, or explain that no matching records were found.

User Query:
"{q}"

Retrieved Database Context:
{context_str}

Answer:
"""
    try:
        answer = ask_llm(synthesize_prompt)
    except Exception as e:
        answer = f"Failed to synthesize answer: {str(e)}. Retrieved data: {context_str[:500]}"

    return {"answer": answer, "debug_queries": plans}
