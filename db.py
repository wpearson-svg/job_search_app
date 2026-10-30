import json
import os
import re
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "jobs.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL, ext_id TEXT NOT NULL,
  title TEXT, company TEXT, location TEXT, url TEXT, description TEXT, posted TEXT,
  pasted INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'new',
  score INTEGER NOT NULL DEFAULT 0,
  matched_json TEXT NOT NULL DEFAULT '[]', gaps_json TEXT NOT NULL DEFAULT '[]', flags_json TEXT NOT NULL DEFAULT '[]',
  title_match INTEGER NOT NULL DEFAULT 0,
  added_at TEXT NOT NULL,
  UNIQUE(source, ext_id));
CREATE TABLE IF NOT EXISTS extras(term TEXT PRIMARY KEY, added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS job_links(job_id INTEGER NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL, PRIMARY KEY(job_id, url));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL, kind TEXT NOT NULL, starts_at TEXT NOT NULL, minutes INTEGER NOT NULL DEFAULT 60, place TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS profiles(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, keywords TEXT NOT NULL DEFAULT '', titles TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS job_profiles(job_id INTEGER NOT NULL, profile_id INTEGER NOT NULL, PRIMARY KEY(job_id, profile_id));
CREATE TABLE IF NOT EXISTS gap_plans(id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, content TEXT NOT NULL, file TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS queue_items(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, job_id INTEGER, scope TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'waiting', created_at TEXT NOT NULL, imported_at TEXT);
CREATE TABLE IF NOT EXISTS outputs(job_id INTEGER NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, warnings_json TEXT NOT NULL DEFAULT '[]', files_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, PRIMARY KEY(job_id, kind));
"""


# Where a posting stands. The first three are before applying; the middle group is the application's progress.
STATUSES = [("new", "New"), ("saved", "Saved"), ("applied", "Applied"), ("phone_screen", "Phone screen"),
            ("interview", "Interview"), ("offer", "Offer"), ("rejected", "Rejected"), ("no_response", "No response"),
            ("withdrawn", "Withdrawn"), ("dismissed", "Dismissed")]
APPLIED_STAGES = ["applied", "phone_screen", "interview", "offer", "rejected", "no_response", "withdrawn"]
STATUS_LABEL = dict(STATUSES)


def _migrate(c):
    """Adds columns that older copies of jobs.db do not have yet."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    for name, ddl in (("applied_on", "TEXT"), ("notes", "TEXT NOT NULL DEFAULT ''"), ("status_updated", "TEXT")):
        if name not in cols:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")
    c.commit()


def connect(path=None):
    c = sqlite3.connect(path or DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    _migrate(c)
    return c


_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company)\b")


def norm(text):
    t = _SUFFIX.sub(" ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()))
    return " ".join(t.split())


def dup_key(title, company):
    """Same title at the same company counts as the same posting. A posting with no company never matches."""
    if not norm(company):
        return ""
    return norm(title) + "|" + norm(company)


def same_place(a, b):
    """Locations agree when either is blank or their first part (the city) matches."""
    ca, cb = norm((a or "").split(",")[0]), norm((b or "").split(",")[0])
    return not ca or not cb or ca == cb or ca in cb or cb in ca


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_job(r):
    d = dict(r)
    d["matched"] = json.loads(d.pop("matched_json"))
    d["gaps"] = json.loads(d.pop("gaps_json"))
    d["flags"] = json.loads(d.pop("flags_json"))
    return d
