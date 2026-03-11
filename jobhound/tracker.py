import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from jobhound.models import Job, Status


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE NOT NULL,
    source       TEXT NOT NULL,
    company      TEXT NOT NULL,
    title        TEXT NOT NULL,
    location     TEXT DEFAULT '',
    remote       BOOLEAN DEFAULT 0,
    salary_min   INTEGER,
    salary_max   INTEGER,
    description  TEXT DEFAULT '',
    score        INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'new',
    applied_at   TEXT,
    method       TEXT,
    cover_letter TEXT,
    cv_used      TEXT,
    notes        TEXT,
    raw_json     TEXT DEFAULT '{}'
);
"""


class Tracker:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        with self._conn() as conn:
            conn.execute(CREATE_SQL)

    def seen(self, url: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
            return row is not None

    def record(self, job: Job):
        d = job.to_dict()
        with self._conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO jobs
                (url, source, company, title, location, remote, salary_min, salary_max,
                 description, score, status, applied_at, method, cover_letter, cv_used, notes, raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                d["url"], d["source"], d["company"], d["title"],
                d["location"], d["remote"], d["salary_min"], d["salary_max"],
                d["description"], d["score"], d["status"],
                d["applied_at"], d["method"], d["cover_letter"],
                d["cv_used"], d["notes"], json.dumps(d.get("raw", {}))
            ))

    def update_status(self, url: str, status: Status,
                      method: Optional[str] = None,
                      cover_letter: Optional[str] = None,
                      cv_used: Optional[str] = None,
                      notes: Optional[str] = None):
        fields = ["status = ?"]
        vals = [status.value]
        if status == Status.APPLIED:
            fields.append("applied_at = ?")
            vals.append(datetime.now(timezone.utc).isoformat())
        if method is not None:
            fields.append("method = ?")
            vals.append(method)
        if cover_letter is not None:
            fields.append("cover_letter = ?")
            vals.append(cover_letter)
        if cv_used is not None:
            fields.append("cv_used = ?")
            vals.append(cv_used)
        if notes is not None:
            fields.append("notes = ?")
            vals.append(notes)
        vals.append(url)
        with self._conn() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE url = ?", vals)

    def list_by_status(self, status: Status) -> list[Job]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY id DESC", (status.value,)
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_all(self, limit: int = 200) -> list[Job]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_by_id(self, job_id: int) -> Optional[Job]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def stats(self) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM jobs GROUP BY status"
            ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            url=row["url"], source=row["source"],
            company=row["company"], title=row["title"],
            location=row["location"] or "",
            remote=bool(row["remote"]),
            salary_min=row["salary_min"], salary_max=row["salary_max"],
            description=row["description"] or "",
            score=row["score"] or 0,
            status=Status(row["status"]),
            applied_at=row["applied_at"], method=row["method"],
            cover_letter=row["cover_letter"], cv_used=row["cv_used"],
            notes=row["notes"],
            raw=json.loads(row["raw_json"] or "{}"),
            db_id=row["id"],
        )
