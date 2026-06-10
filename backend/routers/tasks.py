from fastapi import APIRouter
from pydantic import BaseModel
from db.setup import get_connection

router = APIRouter()


class TaskUpdate(BaseModel):
    status: str


@router.get("/")
def all_tasks(owner: str = None, status: str = None):
    conn  = get_connection()
    query = "SELECT * FROM tasks WHERE 1=1"
    args  = []

    if owner:
        query += " AND LOWER(owner) LIKE ?"
        args.append(f"%{owner.lower()}%")
    if status:
        query += " AND status=?"
        args.append(status)

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.patch("/{task_id}")
def update_task(task_id: int, body: TaskUpdate):
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET status=? WHERE id=?",
        (body.status, task_id)
    )
    conn.commit()
    conn.close()
    return {"updated": task_id, "status": body.status}


@router.get("/summary/by-owner")
def tasks_by_owner():
    conn = get_connection()
    rows = conn.execute(
        """SELECT owner, COUNT(*) as total,
           SUM(CASE WHEN status='Done' THEN 1 ELSE 0 END) as done
           FROM tasks GROUP BY owner ORDER BY total DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
