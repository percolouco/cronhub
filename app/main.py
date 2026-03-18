import asyncio
import os
import subprocess
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", "/data/cronhub.db")
scheduler = AsyncIOScheduler(timezone="Europe/Paris")


# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            schedule    TEXT NOT NULL,
            command     TEXT NOT NULL,
            description TEXT DEFAULT '',
            category    TEXT DEFAULT '',
            enabled     INTEGER DEFAULT 1,
            last_run    TEXT,
            last_status TEXT DEFAULT 'never',
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id     TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            started_at TEXT NOT NULL,
            ended_at   TEXT,
            status     TEXT NOT NULL DEFAULT 'running',
            exit_code  INTEGER,
            stdout     TEXT DEFAULT '',
            stderr     TEXT DEFAULT ''
        );
    """)
    conn.commit()
    
    # Migration: ajouter la colonne category si elle n'existe pas
    try:
        conn = get_db()
        conn.execute("ALTER TABLE jobs ADD COLUMN category TEXT DEFAULT ''")
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        # La colonne existe déjà
        pass


def row_to_dict(row) -> dict:
    return dict(row) if row else None


def get_all_jobs() -> list:
    conn = get_db()
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job(job_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


def get_job_logs(job_id: str, limit: int = 50) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM logs WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
        (job_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────
# Job execution
# ──────────────────────────────────────────────
def run_job_sync(job_id: str):
    """Called by APScheduler (sync) or direct trigger."""
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        conn.close()
        return
    if not job["enabled"]:
        conn.close()
        return

    started_at = datetime.now().isoformat()
    log_id = conn.execute(
        "INSERT INTO logs (job_id, started_at, status) VALUES (?, ?, 'running')",
        (job_id, started_at)
    ).lastrowid
    conn.execute("UPDATE jobs SET last_run = ?, last_status = 'running' WHERE id = ?",
                 (started_at, job_id))
    conn.commit()
    conn.close()

    try:
        result = subprocess.run(
            job["command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        status = "success" if result.returncode == 0 else "failed"
        stdout = result.stdout[-10000:] if result.stdout else ""
        stderr = result.stderr[-10000:] if result.stderr else ""
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        status = "failed"
        stdout = ""
        stderr = "Timeout (3600s)"
        exit_code = -1
    except Exception as e:
        status = "failed"
        stdout = ""
        stderr = str(e)
        exit_code = -1

    ended_at = datetime.now().isoformat()
    conn2 = get_db()
    conn2.execute(
        "UPDATE logs SET ended_at=?, status=?, exit_code=?, stdout=?, stderr=? WHERE id=?",
        (ended_at, status, exit_code, stdout, stderr, log_id)
    )
    conn2.execute(
        "UPDATE jobs SET last_run=?, last_status=? WHERE id=?",
        (started_at, status, job_id)
    )
    conn2.commit()
    conn2.close()


# ──────────────────────────────────────────────
# Scheduler helpers
# ──────────────────────────────────────────────
def _parse_cron(schedule: str) -> CronTrigger:
    parts = schedule.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron: {schedule}")
    minute, hour, day, month, dow = parts
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=dow,
        timezone="Europe/Paris"
    )


def schedule_job(job: dict):
    job_id = job["id"]
    if not job.get("enabled"):
        return
    try:
        trigger = _parse_cron(job["schedule"])
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        scheduler.add_job(run_job_sync, trigger, id=job_id, args=[job_id],
                          replace_existing=True, misfire_grace_time=60)
    except Exception as e:
        print(f"[CronHub] Failed to schedule {job_id}: {e}")


def unschedule_job(job_id: str):
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def reschedule_all():
    for job in get_all_jobs():
        if job["enabled"]:
            schedule_job(job)
        else:
            unschedule_job(job["id"])


# ──────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    reschedule_all()
    yield
    scheduler.shutdown(wait=False)


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────
app = FastAPI(title="CronHub", version="1.0.0",
              description="API REST de gestion de cron jobs", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


# ──────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────
class JobCreate(BaseModel):
    name: str
    schedule: str
    command: str
    description: Optional[str] = ""
    category: Optional[str] = ""
    enabled: Optional[bool] = True


class JobUpdate(BaseModel):
    name: Optional[str] = None
    schedule: Optional[str] = None
    command: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    enabled: Optional[bool] = None


# ──────────────────────────────────────────────
# API Routes
# ──────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/jobs")
def api_list_jobs():
    return get_all_jobs()


@app.post("/api/jobs", status_code=201)
def api_create_job(payload: JobCreate):
    try:
        _parse_cron(payload.schedule)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    job_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO jobs (id,name,schedule,command,description,category,enabled,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (job_id, payload.name, payload.schedule, payload.command,
         payload.description or "", payload.category or "", int(payload.enabled), now)
    )
    conn.commit()
    conn.close()

    job = get_job(job_id)
    if job["enabled"]:
        schedule_job(job)
    return job


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.put("/api/jobs/{job_id}")
def api_update_job(job_id: str, payload: JobUpdate):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.schedule is not None:
        try:
            _parse_cron(payload.schedule)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        updates["schedule"] = payload.schedule
    if payload.command is not None:
        updates["command"] = payload.command
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.category is not None:
        updates["category"] = payload.category
    if payload.enabled is not None:
        updates["enabled"] = int(payload.enabled)

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [job_id]
        conn = get_db()
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id=?", vals)
        conn.commit()
        conn.close()

    job = get_job(job_id)
    unschedule_job(job_id)
    if job["enabled"]:
        schedule_job(job)
    return job


@app.delete("/api/jobs/{job_id}", status_code=204)
def api_delete_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    unschedule_job(job_id)
    conn = get_db()
    conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    conn.commit()
    conn.close()


@app.post("/api/jobs/{job_id}/toggle")
def api_toggle_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    new_state = 0 if job["enabled"] else 1
    conn = get_db()
    conn.execute("UPDATE jobs SET enabled=? WHERE id=?", (new_state, job_id))
    conn.commit()
    conn.close()
    job = get_job(job_id)
    if job["enabled"]:
        schedule_job(job)
    else:
        unschedule_job(job_id)
    return job


@app.post("/api/jobs/{job_id}/run")
def api_run_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Run in background thread via scheduler one-shot
    scheduler.add_job(run_job_sync, args=[job_id], id=f"manual_{job_id}_{uuid.uuid4().hex[:6]}",
                      replace_existing=False, misfire_grace_time=60)
    return {"status": "triggered", "job_id": job_id}


@app.get("/api/jobs/{job_id}/logs")
def api_get_logs(job_id: str, limit: int = 50):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return get_job_logs(job_id, limit)


# ──────────────────────────────────────────────
# UI Routes
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def ui_index(request: Request):
    jobs = get_all_jobs()
    total = len(jobs)
    active = sum(1 for j in jobs if j["enabled"])
    failed = sum(1 for j in jobs if j["last_status"] == "failed")
    success = sum(1 for j in jobs if j["last_status"] == "success")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "jobs": jobs,
        "page": "dashboard",
        "stats": {"total": total, "active": active, "failed": failed, "success": success},
    })


@app.get("/jobs/new", response_class=HTMLResponse)
def ui_new_job(request: Request):
    return templates.TemplateResponse("job_form.html", {
        "request": request,
        "page": "jobs",
        "job": None,
        "action": "/jobs",
        "method": "POST",
    })


@app.post("/jobs", response_class=HTMLResponse)
def ui_create_job(
    request: Request,
    name: str = Form(...),
    schedule: str = Form(...),
    command: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    enabled: str = Form("on"),
):
    try:
        _parse_cron(schedule)
    except ValueError as e:
        return templates.TemplateResponse("job_form.html", {
            "request": request,
            "page": "jobs",
            "job": None,
            "action": "/jobs",
            "method": "POST",
            "error": str(e),
            "form": {"name": name, "schedule": schedule, "command": command, "description": description},
        })

    job_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    is_enabled = 1 if enabled == "on" else 0
    conn = get_db()
    conn.execute(
        "INSERT INTO jobs (id,name,schedule,command,description,category,enabled,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (job_id, name, schedule, command, description, category, is_enabled, now)
    )
    conn.commit()
    conn.close()
    job = get_job(job_id)
    if job["enabled"]:
        schedule_job(job)
    return RedirectResponse("/", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def ui_job_detail(request: Request, job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    logs = get_job_logs(job_id, 20)
    return templates.TemplateResponse("job_detail.html", {
        "request": request,
        "job": job,
        "logs": logs,
        "page": "jobs",
    })


@app.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
def ui_edit_job(request: Request, job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("job_form.html", {
        "request": request,
        "page": "jobs",
        "job": job,
        "action": f"/jobs/{job_id}/edit",
        "method": "POST",
    })


@app.post("/jobs/{job_id}/edit", response_class=HTMLResponse)
def ui_update_job(
    request: Request,
    job_id: str,
    name: str = Form(...),
    schedule: str = Form(...),
    command: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    enabled: str = Form("off"),
):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    try:
        _parse_cron(schedule)
    except ValueError as e:
        return templates.TemplateResponse("job_form.html", {
            "request": request,
            "page": "jobs",
            "job": job,
            "action": f"/jobs/{job_id}/edit",
            "method": "POST",
            "error": str(e),
        })

    is_enabled = 1 if enabled == "on" else 0
    conn = get_db()
    conn.execute(
        "UPDATE jobs SET name=?,schedule=?,command=?,description=?,category=?,enabled=? WHERE id=?",
        (name, schedule, command, description, category, is_enabled, job_id)
    )
    conn.commit()
    conn.close()
    job = get_job(job_id)
    unschedule_job(job_id)
    if job["enabled"]:
        schedule_job(job)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/delete")
def ui_delete_job(job_id: str):
    unschedule_job(job_id)
    conn = get_db()
    conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.post("/jobs/{job_id}/toggle")
def ui_toggle_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    new_state = 0 if job["enabled"] else 1
    conn = get_db()
    conn.execute("UPDATE jobs SET enabled=? WHERE id=?", (new_state, job_id))
    conn.commit()
    conn.close()
    job = get_job(job_id)
    if job["enabled"]:
        schedule_job(job)
    else:
        unschedule_job(job_id)
    return RedirectResponse("/", status_code=303)


@app.post("/jobs/{job_id}/run-now")
def ui_run_now(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404)
    scheduler.add_job(run_job_sync, args=[job_id],
                      id=f"manual_{job_id}_{uuid.uuid4().hex[:6]}",
                      replace_existing=False, misfire_grace_time=60)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)
