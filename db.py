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
CREATE TABLE IF NOT EXISTS queue_batches(batch TEXT PRIMARY KEY, created_at TEXT NOT NULL, report_seen INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS outputs(job_id INTEGER NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, warnings_json TEXT NOT NULL DEFAULT '[]', files_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, PRIMARY KEY(job_id, kind));
CREATE TABLE IF NOT EXISTS job_tags(job_id INTEGER NOT NULL, tag TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, changed_at TEXT NOT NULL, PRIMARY KEY(job_id, tag));
CREATE TABLE IF NOT EXISTS avoided(key TEXT PRIMARY KEY, company TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, changed_at TEXT NOT NULL);
"""


NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%S+00:00','now')"          # the same text as now()
SYNC = f"""
CREATE UNIQUE INDEX IF NOT EXISTS jobs_uid ON jobs(uid);
CREATE TABLE IF NOT EXISTS tombstones(uid TEXT PRIMARY KEY, kind TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_notes(uid TEXT PRIMARY KEY, notes TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS jobs_new_uid AFTER INSERT ON jobs WHEN new.uid IS NULL
  BEGIN UPDATE jobs SET uid=lower(hex(randomblob(16))) WHERE id=new.id; END;
CREATE TRIGGER IF NOT EXISTS gap_plans_new_uid AFTER INSERT ON gap_plans WHEN new.uid IS NULL
  BEGIN UPDATE gap_plans SET uid=lower(hex(randomblob(16))) WHERE id=new.id; END;
CREATE TRIGGER IF NOT EXISTS events_new_uid AFTER INSERT ON events WHEN new.uid IS NULL
  BEGIN UPDATE events SET uid=lower(hex(randomblob(16))), changed_at=COALESCE(new.changed_at, {NOW_SQL}) WHERE id=new.id; END;
CREATE TRIGGER IF NOT EXISTS events_changed AFTER UPDATE OF kind, starts_at, minutes, place, notes, time_zone ON events
  WHEN new.changed_at IS old.changed_at BEGIN UPDATE events SET changed_at={NOW_SQL} WHERE id=new.id; END;
CREATE TRIGGER IF NOT EXISTS jobs_gone AFTER DELETE ON jobs WHEN old.uid IS NOT NULL
  BEGIN INSERT OR REPLACE INTO tombstones(uid, kind, at) VALUES (old.uid, 'posting', {NOW_SQL}); END;
CREATE TRIGGER IF NOT EXISTS events_gone AFTER DELETE ON events WHEN old.uid IS NOT NULL
  BEGIN INSERT OR REPLACE INTO tombstones(uid, kind, at) VALUES (old.uid, 'event', {NOW_SQL}); END;
CREATE TRIGGER IF NOT EXISTS gap_plans_gone AFTER DELETE ON gap_plans WHEN old.uid IS NOT NULL
  BEGIN INSERT OR REPLACE INTO tombstones(uid, kind, at) VALUES (old.uid, 'gap_plan', {NOW_SQL}); END;
CREATE TRIGGER IF NOT EXISTS jobs_gone_tags AFTER DELETE ON jobs BEGIN DELETE FROM job_tags WHERE job_id=old.id; END;
"""


# Where a posting stands. The first three are before applying; the middle group is the application's progress.
STATUSES = [("new", "New"), ("saved", "Saved"), ("applied", "Applied"), ("phone_screen", "Phone screen"),
            ("interview", "Interview"), ("offer", "Offer"), ("rejected", "Rejected"), ("no_response", "No response"),
            ("withdrawn", "Withdrawn"), ("dismissed", "Dismissed")]
APPLIED_STAGES = ["applied", "phone_screen", "interview", "offer", "rejected", "no_response", "withdrawn"]
STATUS_LABEL = dict(STATUSES)

# Tags say something about a posting that its status does not. These keys are fixed so that, one day, the same tag
# from many people can be counted together; a tag you type yourself is kept as "c:" + your words.
TAGS = [("ai_interview", "AI interview", "Uses AI to screen or interview applicants"),
        ("scam", "Possible scam", "Signs of a fake job or a scam"),
        ("ghost", "Ghost posting", "Reposted again and again, never seems to be filled"),
        ("no_pay", "No pay listed", "The posting gives no pay or pay range"),
        ("agency", "Agency or recruiter", "Posted by a staffing agency or outside recruiter"),
        ("unpaid_test", "Unpaid test task", "Asks for unpaid work as part of applying")]
TAG_LABEL = {k: label for k, label, _ in TAGS}
CUSTOM = "c:"


def tag_label(tag):
    return TAG_LABEL.get(tag) or (tag[len(CUSTOM):] if tag.startswith(CUSTOM) else tag)


def custom_tag(text):
    """The key for a tag you type yourself, or "" when there is nothing to keep."""
    t = " ".join((text or "").split())[:40]
    return CUSTOM + t if t else ""


def _migrate(c):
    """Adds columns that older copies of jobs.db do not have yet."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    for name, ddl in (("applied_on", "TEXT"), ("notes", "TEXT NOT NULL DEFAULT ''"), ("status_updated", "TEXT")):
        if name not in cols:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")
    qcols = {r[1] for r in c.execute("PRAGMA table_info(queue_items)")}
    for name, ddl in (("batch", "TEXT"), ("n", "INTEGER"), ("label", "TEXT NOT NULL DEFAULT ''"), ("note", "TEXT NOT NULL DEFAULT ''")):
        if name not in qcols:
            c.execute(f"ALTER TABLE queue_items ADD COLUMN {name} {ddl}")
    if "place" not in {r[1] for r in c.execute("PRAGMA table_info(queue_batches)")}:   # which work folder it is in
        c.execute("ALTER TABLE queue_batches ADD COLUMN place TEXT NOT NULL DEFAULT ''")
    # The shared postings database (shared_db.py): an id that is the same on every device, a time on each interview
    # change, and a record of what was deleted, kept up to date by the triggers in SYNC.
    for table, cols in (("jobs", (("uid", "TEXT"),)), ("gap_plans", (("uid", "TEXT"),)),
                        ("events", (("uid", "TEXT"), ("changed_at", "TEXT"), ("time_zone", "TEXT NOT NULL DEFAULT ''")))):
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        for name, ddl in cols:
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        c.execute(f"UPDATE {table} SET uid=lower(hex(randomblob(16))) WHERE uid IS NULL")
    c.execute(f"UPDATE events SET changed_at={NOW_SQL} WHERE changed_at IS NULL")
    c.executescript(SYNC)
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


# A removed tag or avoided company keeps its row with active=0, so the removal reaches the other device too.
def set_tag(conn, job_id, tag, on):
    conn.execute("INSERT INTO job_tags(job_id, tag, active, changed_at) VALUES (?,?,?,?) ON CONFLICT(job_id, tag) "
                 "DO UPDATE SET active=excluded.active, changed_at=excluded.changed_at", (job_id, tag, int(on), now()))


def set_avoided(conn, company, reason, on):
    """Avoids (or stops avoiding) a company, matched by its name without Inc, LLC and the like. False when the name
    is blank."""
    key = norm(company)
    if not key:
        return False
    conn.execute("INSERT INTO avoided(key, company, reason, active, changed_at) VALUES (?,?,?,?,?) ON CONFLICT(key) "
                 "DO UPDATE SET company=excluded.company, reason=excluded.reason, active=excluded.active, "
                 "changed_at=excluded.changed_at", (key, company.strip(), (reason or "").strip(), int(on), now()))
    return True


def avoided(conn):
    """{key: row} for the companies you avoid."""
    return {r["key"]: dict(r) for r in conn.execute("SELECT * FROM avoided WHERE active=1 ORDER BY company")}


def job_tags(conn, job_id=None):
    """{job id: [tag, ...]} for the tags in use (one posting's when job_id is given)."""
    sql, args = "SELECT job_id, tag FROM job_tags WHERE active=1", ()
    if job_id is not None:
        sql, args = sql + " AND job_id=?", (job_id,)
    out = {}
    for r in conn.execute(sql + " ORDER BY tag", args):
        out.setdefault(r["job_id"], []).append(r["tag"])
    return out


def row_to_job(r):
    d = dict(r)
    d["matched"] = json.loads(d.pop("matched_json"))
    d["gaps"] = json.loads(d.pop("gaps_json"))
    d["flags"] = json.loads(d.pop("flags_json"))
    return d
