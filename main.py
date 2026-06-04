
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("atelier_alert_online.db")
API_KEY = "SCHIMBA_PAROLA_ASTEA_123"

app = FastAPI(title="Atelier Alert Online")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'NORMAL',
            worker TEXT, category TEXT, order_no TEXT, client_name TEXT,
            product TEXT, quantity TEXT, location TEXT, due_time TEXT,
            status TEXT NOT NULL DEFAULT 'NECITIT',
            created_at TEXT NOT NULL, seen_at TEXT, answered_at TEXT,
            response TEXT, checklist_ok INTEGER DEFAULT 0,
            checklist_problem INTEGER DEFAULT 0, tablet_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER, event_type TEXT NOT NULL,
            details TEXT, created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def check_key(api_key):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key gresit")

def d(row):
    return dict(row) if row else None

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def home():
    return {"status": "online", "app": "Atelier Alert Online", "docs": "/docs"}

@app.post("/tasks")
def create_task(
    api_key: str = Form(...), title: str = Form(...), message: str = Form(...),
    priority: str = Form("URGENT"), worker: str = Form(""), category: str = Form(""),
    order_no: str = Form(""), client_name: str = Form(""), product: str = Form(""),
    quantity: str = Form(""), location: str = Form(""), due_time: str = Form("")
):
    check_key(api_key)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tasks
        (title,message,priority,worker,category,order_no,client_name,product,quantity,location,due_time,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (title,message,priority,worker,category,order_no,client_name,product,quantity,location,due_time,now()))
    task_id = cur.lastrowid
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at) VALUES(?,?,?,?)",
                 (task_id,"CREAT","Alerta trimisa",now()))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return {"ok": True, "task": d(row)}

@app.get("/tasks/active")
def active_task(api_key: str, tablet_id: str = "tablet-1", zone: str = ""):
    check_key(api_key)
    conn = db()
    if zone and zone.lower() not in ["toate", "all", "tablet-1"]:
        row = conn.execute("""
            SELECT * FROM tasks
            WHERE status IN ('NECITIT','VAZUT','IN_LUCRU')
            AND (worker=? OR worker='Toate' OR worker='' OR worker IS NULL)
            ORDER BY CASE priority WHEN 'URGENT' THEN 1 WHEN 'IMPORTANT' THEN 2 ELSE 3 END, id DESC
            LIMIT 1
        """, (zone,)).fetchone()
    else:
        row = conn.execute("""
            SELECT * FROM tasks
            WHERE status IN ('NECITIT','VAZUT','IN_LUCRU')
            ORDER BY CASE priority WHEN 'URGENT' THEN 1 WHEN 'IMPORTANT' THEN 2 ELSE 3 END, id DESC
            LIMIT 1
        """).fetchone()
    conn.close()
    return {"task": d(row)}

@app.get("/tasks/open")
def open_tasks(api_key: str, zone: str = "", limit: int = 20):
    check_key(api_key)
    conn = db()
    if zone and zone.lower() not in ["toate", "all", "tablet-1"]:
        rows = conn.execute("""
            SELECT * FROM tasks
            WHERE status IN ('NECITIT','VAZUT','IN_LUCRU')
            AND (worker=? OR worker='Toate' OR worker='' OR worker IS NULL)
            ORDER BY CASE priority WHEN 'URGENT' THEN 1 WHEN 'IMPORTANT' THEN 2 ELSE 3 END, id DESC
            LIMIT ?
        """, (zone, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM tasks
            WHERE status IN ('NECITIT','VAZUT','IN_LUCRU')
            ORDER BY CASE priority WHEN 'URGENT' THEN 1 WHEN 'IMPORTANT' THEN 2 ELSE 3 END, id DESC
            LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return {"tasks": [d(r) for r in rows]}

@app.get("/tasks")
def list_tasks(api_key: str, limit: int = 100):
    check_key(api_key)
    conn = db()
    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"tasks": [d(r) for r in rows]}

@app.post("/tasks/{task_id}/seen")
def mark_seen(task_id: int, api_key: str = Form(...), tablet_id: str = Form("tablet-1")):
    check_key(api_key)
    conn = db()
    conn.execute("UPDATE tasks SET status='VAZUT', seen_at=COALESCE(seen_at, ?), tablet_id=? WHERE id=?",
                 (now(), tablet_id, task_id))
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at) VALUES(?,?,?,?)",
                 (task_id,"VAZUT",tablet_id,now()))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return {"ok": True, "task": d(row)}

@app.post("/tasks/{task_id}/start")
def start_task(task_id: int, api_key: str = Form(...), tablet_id: str = Form("tablet-1")):
    check_key(api_key)
    conn = db()
    conn.execute("UPDATE tasks SET status='IN_LUCRU', seen_at=COALESCE(seen_at, ?), tablet_id=? WHERE id=?",
                 (now(), tablet_id, task_id))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return {"ok": True, "task": d(row)}

@app.post("/tasks/{task_id}/answer")
def answer_task(task_id: int, api_key: str = Form(...), response: str = Form(...),
                status: str = Form("FINALIZAT"), checklist_ok: int = Form(0),
                checklist_problem: int = Form(0), tablet_id: str = Form("tablet-1")):
    check_key(api_key)
    conn = db()
    conn.execute("""
        UPDATE tasks SET status=?, answered_at=?, response=?, checklist_ok=?, checklist_problem=?, tablet_id=? WHERE id=?
    """, (status, now(), response, checklist_ok, checklist_problem, tablet_id, task_id))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return {"ok": True, "task": d(row)}

@app.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, api_key: str = Form(...)):
    check_key(api_key)
    conn = db()
    conn.execute("UPDATE tasks SET status='ANULAT', answered_at=? WHERE id=?", (now(), task_id))
    conn.commit()
    conn.close()
    return {"ok": True}
