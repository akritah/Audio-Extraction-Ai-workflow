import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import uvicorn
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import upload, tasks, search, meetings, calendar, analytics, live, automations
from db.setup import init_db, init_chroma

app = FastAPI(title="Meeting Intelligence System")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()
    init_chroma()

app.include_router(upload.router,    prefix="/upload",    tags=["upload"])
app.include_router(tasks.router,     prefix="/tasks",     tags=["tasks"])
app.include_router(search.router,    prefix="/search",    tags=["search"])
app.include_router(meetings.router,  prefix="/meetings",  tags=["meetings"])
app.include_router(calendar.router,  prefix="/calendar",  tags=["calendar"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(live.router,      prefix="/live",      tags=["live"])
app.include_router(automations.router, prefix="/automations", tags=["automations"])

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
