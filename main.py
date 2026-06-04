
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
from pathlib import Path
from datetime import datetime
import shutil
import csv
from io import StringIO
from fastapi.responses import StreamingResponse

DB_PATH = Path("atelier_alert_online.db")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
API_KEY = "SCHIMBA_PAROLA_ASTEA_123"

app = FastAPI(title="Atelier Alert Online V3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_key(api_key):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key gresit")

def d(row):
    return dict(row) if row else None

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
            created_at TEXT NOT NULL, seen_at TEXT, started_at TEXT, answered_at TEXT,
            response TEXT, checklist_ok INTEGER DEFAULT 0,
            checklist_problem INTEGER DEFAULT 0, tablet_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            event_type TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL,
            tablet_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tablet_id TEXT
        )
    """)
    # safe migrations
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
    if "started_at" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN started_at TEXT")
    ev_cols = [r["name"] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
    if "tablet_id" not in ev_cols:
        conn.execute("ALTER TABLE events ADD COLUMN tablet_id TEXT")
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def home():
    return {"status": "online", "app": "Atelier Alert Online V3", "docs": "/docs"}

@app.post("/tasks")
def create_task(
    api_key: str = Form(...), title: str = Form(...), message: str = Form(...),
    priority: str = Form("URGENT"), worker: str = Form("Toate"), category: str = Form("Verificare"),
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
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at,tablet_id) VALUES(?,?,?,?,?)",
                 (task_id,"CREAT","Alerta trimisa",now(),"PC"))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return {"ok": True, "task": d(row)}

@app.get("/tasks")
def list_tasks(api_key: str, limit: int = 200):
    check_key(api_key)
    conn = db()
    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"tasks": [d(r) for r in rows]}

@app.get("/tasks/open")
def open_tasks(api_key: str, zone: str = "", limit: int = 50):
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

@app.get("/tasks/{task_id}")
def get_task(task_id: int, api_key: str):
    check_key(api_key)
    conn = db()
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    events = conn.execute("SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
    photos = conn.execute("SELECT * FROM photos WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
    conn.close()
    return {"task": d(task), "events": [d(e) for e in events], "photos": [d(p) for p in photos]}

@app.post("/tasks/{task_id}/seen")
def mark_seen(task_id: int, api_key: str = Form(...), tablet_id: str = Form("tablet-1")):
    check_key(api_key)
    conn = db()
    conn.execute("UPDATE tasks SET status='VAZUT', seen_at=COALESCE(seen_at, ?), tablet_id=? WHERE id=?",
                 (now(), tablet_id, task_id))
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at,tablet_id) VALUES(?,?,?,?,?)",
                 (task_id,"VAZUT","Alerta vazuta",now(),tablet_id))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return {"ok": True, "task": d(row)}

@app.post("/tasks/{task_id}/start")
def start_task(task_id: int, api_key: str = Form(...), tablet_id: str = Form("tablet-1")):
    check_key(api_key)
    conn = db()
    conn.execute("""
        UPDATE tasks SET status='IN_LUCRU',
        seen_at=COALESCE(seen_at, ?),
        started_at=COALESCE(started_at, ?),
        tablet_id=?
        WHERE id=?
    """, (now(), now(), tablet_id, task_id))
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at,tablet_id) VALUES(?,?,?,?,?)",
                 (task_id,"IN_LUCRU","Sarcina inceputa",now(),tablet_id))
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
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at,tablet_id) VALUES(?,?,?,?,?)",
                 (task_id,status,response,now(),tablet_id))
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return {"ok": True, "task": d(row)}

@app.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, api_key: str = Form(...)):
    check_key(api_key)
    conn = db()
    conn.execute("UPDATE tasks SET status='ANULAT', answered_at=? WHERE id=?", (now(), task_id))
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at,tablet_id) VALUES(?,?,?,?,?)",
                 (task_id,"ANULAT","Anulat de pe PC",now(),"PC"))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/tasks/{task_id}/photo")
async def upload_photo(task_id: int, api_key: str = Form(...), tablet_id: str = Form("tablet-1"), photo: UploadFile = File(...)):
    check_key(api_key)
    ext = Path(photo.filename or "photo.jpg").suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        ext = ".jpg"
    filename = f"task_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    dest = UPLOAD_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(photo.file, f)
    url = f"/uploads/{filename}"
    conn = db()
    conn.execute("INSERT INTO photos(task_id,filename,url,created_at,tablet_id) VALUES(?,?,?,?,?)",
                 (task_id, filename, url, now(), tablet_id))
    conn.execute("INSERT INTO events(task_id,event_type,details,created_at,tablet_id) VALUES(?,?,?,?,?)",
                 (task_id,"POZA",url,now(),tablet_id))
    conn.commit()
    conn.close()
    return {"ok": True, "url": url}

@app.get("/dashboard")
def dashboard(api_key: str):
    check_key(api_key)
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
    today = datetime.now().strftime("%Y-%m-%d")
    today_total = conn.execute("SELECT COUNT(*) c FROM tasks WHERE created_at LIKE ?", (today+"%",)).fetchone()["c"]
    by_status = [d(r) for r in conn.execute("SELECT status, COUNT(*) count FROM tasks GROUP BY status").fetchall()]
    by_zone = [d(r) for r in conn.execute("SELECT COALESCE(NULLIF(worker,''),'Fara zona') zone, COUNT(*) count FROM tasks GROUP BY worker").fetchall()]
    open_count = conn.execute("SELECT COUNT(*) c FROM tasks WHERE status IN ('NECITIT','VAZUT','IN_LUCRU')").fetchone()["c"]
    problems = conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='PROBLEMA'").fetchone()["c"]
    conn.close()
    return {"total": total, "today": today_total, "open": open_count, "problems": problems, "by_status": by_status, "by_zone": by_zone}

@app.get("/export.csv")
def export_csv(api_key: str):
    check_key(api_key)
    conn = db()
    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    conn.close()
    out = StringIO()
    writer = csv.writer(out)
    headers = ["id","created_at","title","priority","worker","category","order_no","client_name","product","quantity","status","seen_at","started_at","answered_at","response"]
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r[h] if h in r.keys() else "" for h in headers])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=atelier_alert_export.csv"})
