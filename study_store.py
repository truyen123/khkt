"""SQLite store for sessions, events, tasks, assistant messages, system logs."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


def local_timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class StudyStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.active_session_id = None
        self.last_presence_monotonic = None
        self.last_presence_at = None
        # :memory: mo connection rieng moi lan -> giu 1 connection giu DB song
        self._mem_conn = sqlite3.connect(":memory:", timeout=5) if str(path) == ":memory:" else None
        if self._mem_conn is not None:
            self._mem_conn.row_factory = sqlite3.Row
        self._initialize()
        self._recover_open_sessions()

    @contextmanager
    def _connect(self):
        if self._mem_conn is not None:
            try:
                yield self._mem_conn
                self._mem_conn.commit()
            except Exception:
                self._mem_conn.rollback()
                raise
            return
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS study_sessions (
                    id INTEGER PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    last_active_at TEXT NOT NULL,
                    active_seconds REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER,
                    kind TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    details TEXT NOT NULL DEFAULT '',
                    evidence_path TEXT,
                    FOREIGN KEY(session_id) REFERENCES study_sessions(id)
                );
                CREATE INDEX IF NOT EXISTS events_started_at_idx ON events(started_at);
                CREATE INDEX IF NOT EXISTS events_kind_idx ON events(kind);
                CREATE TABLE IF NOT EXISTS posture_alerts (
                    id INTEGER PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    duration_seconds REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS posture_started_at_idx ON posture_alerts(started_at);
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    description TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tasks_created_at_idx ON tasks(created_at);
                CREATE TABLE IF NOT EXISTS assistant_messages (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS assistant_created_at_idx ON assistant_messages(created_at);
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'INFO',
                    source TEXT NOT NULL DEFAULT 'app',
                    message TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS system_logs_created_at_idx ON system_logs(created_at);
                """
            )
            # ---- migration cho DB cu (tao tu ban truoc) ----
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            if "done" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN done INTEGER NOT NULL DEFAULT 0")

    def _recover_open_sessions(self):
        with self._connect() as conn:
            conn.execute("UPDATE study_sessions SET ended_at = last_active_at WHERE ended_at IS NULL")
            conn.execute("UPDATE events SET ended_at = started_at WHERE kind='phone_use' AND ended_at IS NULL")
            conn.execute("UPDATE posture_alerts SET ended_at = started_at WHERE ended_at IS NULL")

    # ---- presence / sessions ----
    def _start_session(self, ts):
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO study_sessions(started_at, last_active_at) VALUES (?, ?)", (ts, ts))
            self.active_session_id = cur.lastrowid
        return self.active_session_id

    def update_presence(self, present, now_monotonic, idle_grace=60):
        with self.lock:
            if present:
                if (self.active_session_id is None or self.last_presence_monotonic is None
                        or now_monotonic - self.last_presence_monotonic > idle_grace):
                    if self.active_session_id is not None:
                        self._close_session(self.last_presence_at)
                    self._start_session(local_timestamp())
                else:
                    elapsed = min(max(now_monotonic - self.last_presence_monotonic, 0), 2)
                    with self._connect() as conn:
                        conn.execute(
                            """UPDATE study_sessions SET active_seconds = active_seconds + ?,
                               last_active_at = ? WHERE id = ? AND ended_at IS NULL""",
                            (elapsed, local_timestamp(), self.active_session_id))
                self.last_presence_monotonic = now_monotonic
                self.last_presence_at = local_timestamp()
            elif (self.active_session_id is not None and self.last_presence_monotonic is not None
                    and now_monotonic - self.last_presence_monotonic > idle_grace):
                self._close_session(self.last_presence_at)

    def _close_session(self, ended_at):
        if self.active_session_id is not None:
            with self._connect() as conn:
                conn.execute("UPDATE study_sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
                             (ended_at or local_timestamp(), self.active_session_id))
        self.active_session_id = None
        self.last_presence_monotonic = None
        self.last_presence_at = None

    def close_active_session(self):
        with self.lock:
            self._close_session(self.last_presence_at)

    # ---- phone events ----
    def start_phone_event(self, started_at, details="Nghi ngờ sử dụng điện thoại"):
        with self.lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO events(session_id, kind, started_at, details) VALUES (?, 'phone_use', ?, ?)",
                (self.active_session_id, started_at, details))
            return cur.lastrowid

    def finish_phone_event(self, event_id, ended_at, evidence_path):
        with self._connect() as conn:
            conn.execute("UPDATE events SET ended_at = ?, evidence_path = ? WHERE id = ? AND kind = 'phone_use'",
                         (ended_at, evidence_path, event_id))

    # ---- posture alerts ----
    def start_posture_alert(self, kind, detail=""):
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO posture_alerts(started_at, kind, detail) VALUES (?, ?, ?)",
                (local_timestamp(), kind, detail))
            return cur.lastrowid

    def finish_posture_alert(self, alert_id, duration_seconds):
        with self._connect() as conn:
            conn.execute("UPDATE posture_alerts SET ended_at = ?, duration_seconds = ? WHERE id = ?",
                         (local_timestamp(), float(duration_seconds), alert_id))

    # ---- tasks ----
    def add_task(self, description):
        created_at = local_timestamp()
        with self._connect() as conn:
            cur = conn.execute("INSERT INTO tasks(created_at, description) VALUES (?, ?)",
                               (created_at, description))
            return {"id": cur.lastrowid, "created_at": created_at,
                    "description": description, "done": 0}

    def toggle_task(self, task_id):
        with self._connect() as conn:
            conn.execute("UPDATE tasks SET done = 1 - done WHERE id = ?", (task_id,))
            row = conn.execute("SELECT id, created_at, description, done FROM tasks WHERE id = ?",
                               (task_id,)).fetchone()
            return dict(row) if row else None

    def delete_task(self, task_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def add_assistant_message(self, user_text, assistant_text):
        with self._connect() as conn:
            conn.execute("INSERT INTO assistant_messages(created_at, user_text, assistant_text) VALUES (?, ?, ?)",
                         (local_timestamp(), user_text, assistant_text))
            conn.execute("DELETE FROM assistant_messages WHERE id NOT IN "
                         "(SELECT id FROM assistant_messages ORDER BY id DESC LIMIT 500)")

    def recent_messages(self, limit=6):
        """Hoi thoai gan day, cu -> moi (hien thi dang chat)."""
        limit = min(max(int(limit or 6), 1), 100)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT created_at, user_text, assistant_text FROM assistant_messages "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---- system logs ----
    def add_log(self, level, source, message):
        with self._connect() as conn:
            conn.execute("INSERT INTO system_logs(created_at, level, source, message) VALUES (?, ?, ?, ?)",
                         (local_timestamp(), level[:10], source[:40], message[:2000]))
            # Retain newest 10k rows to keep long-running deployments bounded.
            cur = conn.execute("SELECT last_insert_rowid()")
            if cur.fetchone()[0] % 100 == 0:
                conn.execute("DELETE FROM system_logs WHERE id NOT IN "
                             "(SELECT id FROM system_logs ORDER BY id DESC LIMIT 10000)")

    def get_logs(self, limit=200):
        limit = min(max(int(limit or 200), 1), 1000)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, level, source, message FROM system_logs "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def clear_logs(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM system_logs")

    def clear_all_data(self):
        """Xoa toan bo du lieu hoc tap + log (giu cau truc bang)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM study_sessions")
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM posture_alerts")
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM assistant_messages")
            conn.execute("DELETE FROM system_logs")
        with self.lock:
            self.active_session_id = None
            self.last_presence_monotonic = None
            self.last_presence_at = None

    def delete_evidence_files(self, evidence_dir):
        import pathlib
        removed, kept = 0, []
        base = pathlib.Path(evidence_dir)
        if base.is_dir():
            for f in base.iterdir():
                if f.is_file() and f.suffix.lower() in (".avi", ".mp4", ".jpg"):
                    try:
                        f.unlink()
                        removed += 1
                    except OSError:
                        kept.append(f.name)
        with self._connect() as conn:
            conn.execute("UPDATE events SET evidence_path = NULL WHERE evidence_path IS NOT NULL")
        return {"removed": removed, "kept": kept}

    def db_size_bytes(self):
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def _fmt_dur(self, seconds):
        s = max(0, int(round(seconds or 0)))
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if h:
            return f"{h} giờ {m:02d} phút {s:02d} giây"
        if m:
            return f"{m} phút {s:02d} giây"
        return f"{s} giây"

    def dashboard(self):
        today = datetime.now().astimezone().date().isoformat()
        with self._connect() as conn:
            sessions = conn.execute(
                "SELECT id, started_at, ended_at, active_seconds FROM study_sessions "
                "WHERE substr(started_at,1,10)=? ORDER BY started_at DESC LIMIT 50", (today,)).fetchall()
            events = conn.execute(
                "SELECT id, kind, started_at, ended_at, details, evidence_path FROM events "
                "WHERE substr(started_at,1,10)=? ORDER BY started_at DESC LIMIT 50", (today,)).fetchall()
            alerts = conn.execute(
                "SELECT id, started_at, ended_at, kind, detail, duration_seconds FROM posture_alerts "
                "WHERE substr(started_at,1,10)=? ORDER BY started_at DESC LIMIT 50", (today,)).fetchall()
            tasks = conn.execute(
                "SELECT id, created_at, description, done FROM tasks "
                "WHERE substr(created_at,1,10)=? ORDER BY created_at DESC LIMIT 30", (today,)).fetchall()
            total = conn.execute(
                "SELECT COALESCE(SUM(active_seconds),0) FROM study_sessions WHERE substr(started_at,1,10)=?",
                (today,)).fetchone()[0]
            week_total = conn.execute(
                "SELECT COALESCE(SUM(active_seconds),0) FROM study_sessions "
                "WHERE substr(started_at,1,10) >= date('now','localtime','-6 days')").fetchone()[0]
        total = int(total or 0)
        sessions = [dict(r) for r in sessions]
        for s in sessions:
            s["duration_text"] = self._fmt_dur(s.get("active_seconds") or 0)
        return {"today": today, "study_seconds": total,
                "study_text": self._fmt_dur(total),
                "week_seconds": int(week_total or 0),
                "week_text": self._fmt_dur(week_total or 0),
                "sessions": sessions,
                "events": [dict(r) for r in events],
                "posture_alerts": [dict(r) for r in alerts],
                "tasks": [dict(r) for r in tasks]}
