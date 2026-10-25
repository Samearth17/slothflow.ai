from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SLOTHFLOW_DB", ROOT / "slothflow.db"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

app = FastAPI(title="SlothFlow AI", description="A local-first assistant that turns brain dumps into manageable action plans.")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@contextmanager
def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'medium',
                estimate_minutes INTEGER NOT NULL DEFAULT 25,
                status TEXT NOT NULL DEFAULT 'todo',
                created_at TEXT NOT NULL,
                due_date TEXT
            )
        """)


@app.on_event("startup")
def startup() -> None:
    init_db()


class BrainDump(BaseModel):
    text: str = Field(min_length=3, max_length=12000)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    details: str = Field(default="", max_length=2000)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    estimate_minutes: int = Field(default=25, ge=5, le=480)
    due_date: str | None = None


class TaskUpdate(BaseModel):
    status: str = Field(pattern="^(todo|done)$")


def local_plan(text: str) -> dict[str, Any]:
    """Predictable fallback that works even when Ollama is unavailable."""
    cleaned = re.sub(r"[\r\t]+", " ", text).strip()
    chunks = re.split(r"(?:\n+|(?<=[.!?])\s+|;\s*)", cleaned)
    candidates = []
    for chunk in chunks:
        chunk = re.sub(r"^[\s\-*•\d.)]+", "", chunk).strip()
        if len(chunk) < 4:
            continue
        if len(chunk) > 150:
            chunk = chunk[:147].rstrip() + "..."
        candidates.append(chunk)
    if not candidates:
        candidates = [cleaned[:150]]
    tasks = []
    for i, item in enumerate(candidates[:8]):
        low = item.lower()
        priority = "high" if any(k in low for k in ("urgent", "today", "deadline", "asap", "tomorrow", "due")) else ("medium" if i < 4 else "low")
        tasks.append({
            "title": item[0].upper() + item[1:],
            "details": "Start with the smallest concrete next action. Adjust this task before saving if needed.",
            "priority": priority,
            "estimate_minutes": 25 if len(item) < 70 else 45
        })
    total = sum(t["estimate_minutes"] for t in tasks)
    return {
        "summary": "I split your notes into a first-pass checklist. Review the tasks and edit anything that needs more context.",
        "tasks": tasks,
        "suggested_order": [t["title"] for t in sorted(tasks, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]])],
        "estimated_total_minutes": total,
        "engine": "local-rules"
    }


def ollama_plan(text: str) -> dict[str, Any] | None:
    prompt = f"""Turn the user's brain dump into a practical, non-judgmental task plan.
Return ONLY valid JSON with this schema:
{{"summary":"one short sentence","tasks":[{{"title":"clear task under 100 chars","details":"one concrete next action","priority":"low|medium|high","estimate_minutes":25}}],"suggested_order":["task title"],"estimated_total_minutes":25}}
Rules: make 2-8 tasks when possible; do not invent deadlines; estimates must be integers from 5 to 240; priority high only for clearly urgent/time-sensitive items; do not include markdown.
User brain dump:
{text}
"""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=45,
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
        data = json.loads(raw)
        tasks = data.get("tasks", [])
        valid = []
        for task in tasks[:8]:
            title = str(task.get("title", "")).strip()[:180]
            if not title:
                continue
            priority = task.get("priority", "medium")
            if priority not in ("low", "medium", "high"):
                priority = "medium"
            try:
                estimate = max(5, min(240, int(task.get("estimate_minutes", 25))))
            except (TypeError, ValueError):
                estimate = 25
            valid.append({
                "title": title,
                "details": str(task.get("details", ""))[:2000],
                "priority": priority,
                "estimate_minutes": estimate
            })
        if not valid:
            return None
        return {
            "summary": str(data.get("summary", "Your notes are now a draft plan."))[:500],
            "tasks": valid,
            "suggested_order": [str(x) for x in data.get("suggested_order", [])][:8],
            "estimated_total_minutes": sum(t["estimate_minutes"] for t in valid),
            "engine": "ollama"
        }
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError):
        return None


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    ollama_available = False
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=1.5)
        ollama_available = r.ok
    except requests.RequestException:
        pass
    return {"status": "ok", "ollama_available": ollama_available, "model": OLLAMA_MODEL}


@app.post("/api/plan")
def create_plan(payload: BrainDump):
    result = ollama_plan(payload.text) or local_plan(payload.text)
    return result


@app.get("/api/tasks")
def list_tasks():
    with db() as con:
        rows = con.execute("SELECT * FROM tasks ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id DESC").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/tasks")
def save_task(payload: TaskCreate):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title cannot be blank.")
    due_date = payload.due_date or None
    with db() as con:
        cursor = con.execute(
            "INSERT INTO tasks(title, details, priority, estimate_minutes, status, created_at, due_date) VALUES (?, ?, ?, ?, 'todo', ?, ?)",
            (title, payload.details.strip(), payload.priority, payload.estimate_minutes, datetime.now().isoformat(timespec="seconds"), due_date)
        )
        row = con.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate):
    with db() as con:
        cursor = con.execute("UPDATE tasks SET status = ? WHERE id = ?", (payload.status, task_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found.")
        row = con.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    with db() as con:
        cursor = con.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found.")
    return {"deleted": True, "id": task_id}


@app.get("/api/reset")
def daily_reset():
    with db() as con:
        rows = con.execute("SELECT * FROM tasks WHERE status = 'todo' ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id").fetchall()
    tasks = [dict(row) for row in rows]
    total = sum(t["estimate_minutes"] for t in tasks)
    return {
        "date": date.today().isoformat(),
        "open_count": len(tasks),
        "estimated_minutes": total,
        "message": "Pick one small next step. You do not need to finish everything today.",
        "tasks": tasks
    }
