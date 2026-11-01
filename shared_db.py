"""The shared postings database: WildThing/user/wildthing.db in Google Drive, the same file for the desktop and the
phone. Format and rules: docs/formats.md, section 7. The cases in shared_tests/shared_db.json run in both apps.

Each device keeps working on its own jobs.db. A sync downloads the shared file, merges it with this device's
postings record by record, applies the result here and uploads a fresh copy. Nobody edits the shared file in place,
so two devices can never corrupt it; a copy overwritten by the other device's upload is rebuilt on its next sync,
because every upload holds everything that device knows.

Shared: postings (with their full text and links), status, applied date, notes, interviews, saved AI work and gap
plans, tags, the companies you avoid, and what was deleted. Not shared: scores and profile tags (each device works them out from the shared resume
and profiles), the AI queue's own records, keys and settings.
"""
import os
import sqlite3
import tempfile

import db

FILE = "wildthing.db"
FORMAT = "wildthing-shared-db"
VERSION = 2                       # 2 added avoided companies and tags; a version 1 file reads as having none
COMBINE = "\n\n--- Also written on another device ---\n"

SCHEMA = """
CREATE TABLE info(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE postings(uid TEXT PRIMARY KEY, source TEXT NOT NULL, ext_id TEXT NOT NULL, title TEXT NOT NULL,
  company TEXT NOT NULL, location TEXT NOT NULL, url TEXT NOT NULL, description TEXT NOT NULL, posted TEXT NOT NULL,
  pasted INTEGER NOT NULL, added_at TEXT NOT NULL, status TEXT NOT NULL, status_at TEXT NOT NULL,
  applied_on TEXT NOT NULL, notes TEXT NOT NULL);
CREATE TABLE links(posting TEXT NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL, PRIMARY KEY(posting, url));
CREATE TABLE events(uid TEXT PRIMARY KEY, posting TEXT NOT NULL, kind TEXT NOT NULL, starts_at TEXT NOT NULL,
  minutes INTEGER NOT NULL, place TEXT NOT NULL, notes TEXT NOT NULL, time_zone TEXT NOT NULL, changed_at TEXT NOT NULL);
CREATE TABLE outputs(posting TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, warnings_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(posting, kind));
CREATE TABLE gap_plans(uid TEXT PRIMARY KEY, scope TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE tombstones(uid TEXT PRIMARY KEY, kind TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE avoided(key TEXT PRIMARY KEY, company TEXT NOT NULL, reason TEXT NOT NULL, active INTEGER NOT NULL,
  changed_at TEXT NOT NULL);
CREATE TABLE tags(posting TEXT NOT NULL, tag TEXT NOT NULL, active INTEGER NOT NULL, changed_at TEXT NOT NULL,
  PRIMARY KEY(posting, tag));
"""
POSTING_TEXT = ("source", "ext_id", "title", "company", "location", "url", "description", "posted", "added_at",
                "status", "status_at", "applied_on", "notes")
CONTENT = ("title", "company", "location", "url", "description", "posted")
EVENT_TEXT = ("posting", "kind", "starts_at", "place", "notes", "time_zone", "changed_at")


def empty():
    return {"postings": {}, "events": {}, "outputs": {}, "gap_plans": {}, "tombstones": {}, "avoided": {}, "tags": {}}


def _s(v):
    return "" if v is None else str(v)


# ---- the merge rule (pure; shared_tests/shared_db.json) ------------------------------------------------------------
def _match(p, candidates):
    """The local posting (uid) that is the same job as remote posting p, or None: same source and id, else the same
    link, else the same title and company in the same place (db.dup_key / db.same_place)."""
    for uid in sorted(candidates):
        c = candidates[uid]
        if c["source"] == p["source"] and c["ext_id"] == p["ext_id"]:
            return uid
    urls = {u for u in [p["url"]] + [l["url"] for l in p["links"]] if u}
    for uid in sorted(candidates):
        c = candidates[uid]
        if urls & {u for u in [c["url"]] + [l["url"] for l in c["links"]] if u}:
            return uid
    key = db.dup_key(p["title"], p["company"])
    for uid in sorted(candidates):
        c = candidates[uid]
        if key and db.dup_key(c["title"], c["company"]) == key and db.same_place(c["location"], p["location"]):
            return uid
    return None


def _merge_notes(here, there, base):
    if here == there:
        return here
    if base is not None and here == base:
        return there
    if base is not None and there == base:
        return here
    if not here.strip():
        return there
    if not there.strip():
        return here
    return here.rstrip() + COMBINE + there.strip()


def _merge_posting(here, there, base_notes):
    out = dict(here)
    for k in CONTENT + ("source", "ext_id"):
        if not out[k]:
            out[k] = there[k]
    out["pasted"] = max(here["pasted"], there["pasted"])
    out["added_at"] = min(x for x in (here["added_at"], there["added_at"]) if x) if (here["added_at"] or there["added_at"]) else ""
    newer = there if (there["status_at"], there["status"]) > (here["status_at"], here["status"]) else here
    out["status"], out["status_at"], out["applied_on"] = newer["status"], newer["status_at"], newer["applied_on"]
    out["notes"] = _merge_notes(here["notes"], there["notes"], base_notes)
    links = {l["url"]: l for l in there["links"]}
    links.update({l["url"]: l for l in here["links"]})
    out["links"] = [links[u] for u in sorted(links)]
    return out


def _newer(here, there, keys):
    """Of two copies of an avoided company or a tag, the one changed last. A removal is a row with active 0, so it
    travels like any other change; at the same moment, on beats off."""
    return there if tuple(there[k] for k in keys) > tuple(here[k] for k in keys) else here


AVOID_ORDER = ("changed_at", "active", "reason", "company")
TAG_ORDER = ("changed_at", "active")


def merge(here, there, base):
    """Merges this device's snapshot (here) with the shared file's (there). base: {posting uid: notes} as they were
    at this device's last sync. Returns {"merged": snapshot, "rename": {local uid: shared uid}}."""
    candidates = {u: p for u, p in here["postings"].items() if u not in there["postings"]}
    rename = {}
    for uid in sorted(u for u in there["postings"] if u not in here["postings"]):
        found = _match(there["postings"][uid], candidates)
        if found:
            rename[found] = uid
            del candidates[found]
    here = _renamed(here, rename)

    tomb = dict(there["tombstones"])
    for uid, t in here["tombstones"].items():
        if uid not in tomb or t["at"] > tomb[uid]["at"]:
            tomb[uid] = t
    out = empty()
    out["tombstones"] = tomb

    for uid in sorted(set(here["postings"]) | set(there["postings"])):
        if uid in tomb:
            continue
        h, t = here["postings"].get(uid), there["postings"].get(uid)
        out["postings"][uid] = _merge_posting(h, t, base.get(uid)) if h and t else dict(h or t)

    for uid in sorted(set(here["events"]) | set(there["events"])):
        h, t = here["events"].get(uid), there["events"].get(uid)
        e = (t if t["changed_at"] > h["changed_at"] else h) if h and t else (h or t)
        if uid not in tomb and e["posting"] in out["postings"]:
            out["events"][uid] = dict(e)

    for key in sorted(set(here["outputs"]) | set(there["outputs"])):
        h, t = here["outputs"].get(key), there["outputs"].get(key)
        o = (t if t["created_at"] > h["created_at"] else h) if h and t else (h or t)
        if o["posting"] in out["postings"]:
            out["outputs"][key] = dict(o)

    for uid in sorted(set(here["gap_plans"]) | set(there["gap_plans"])):
        if uid not in tomb:
            out["gap_plans"][uid] = dict(here["gap_plans"].get(uid) or there["gap_plans"][uid])

    for key in sorted(set(here["avoided"]) | set(there["avoided"])):
        h, t = here["avoided"].get(key), there["avoided"].get(key)
        out["avoided"][key] = dict(_newer(h, t, AVOID_ORDER) if h and t else (h or t))

    for key in sorted(set(here["tags"]) | set(there["tags"])):
        h, t = here["tags"].get(key), there["tags"].get(key)
        g = _newer(h, t, TAG_ORDER) if h and t else (h or t)
        if g["posting"] in out["postings"]:
            out["tags"][key] = dict(g)
    return {"merged": out, "rename": rename}


def _renamed(snap, rename):
    if not rename:
        return snap
    r = lambda u: rename.get(u, u)
    out = empty()
    out["postings"] = {r(u): p for u, p in snap["postings"].items()}
    out["events"] = {u: dict(e, posting=r(e["posting"])) for u, e in snap["events"].items()}
    out["outputs"] = {f"{r(o['posting'])}|{o['kind']}": dict(o, posting=r(o["posting"])) for o in snap["outputs"].values()}
    out["gap_plans"] = dict(snap["gap_plans"])
    out["tombstones"] = dict(snap["tombstones"])
    out["avoided"] = dict(snap["avoided"])
    out["tags"] = {}
    for g in snap["tags"].values():             # two postings that turn out to be one: the later change to a tag wins
        g = dict(g, posting=r(g["posting"]))
        key = f"{g['posting']}|{g['tag']}"
        out["tags"][key] = _newer(out["tags"][key], g, TAG_ORDER) if key in out["tags"] else g
    return out


# ---- the shared file -----------------------------------------------------------------------------------------------
def read_file(data):
    """The snapshot held in a shared file's bytes."""
    fd, path = tempfile.mkstemp(suffix=".db")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    c = None
    try:
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        try:
            info = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM info")}
        except sqlite3.DatabaseError:
            raise ValueError("The shared wildthing.db is not a WildThing file.") from None
        if info.get("format") != FORMAT:
            raise ValueError("The shared wildthing.db is not a WildThing file.")
        if int(info.get("version", "0")) > VERSION:
            raise ValueError("The shared wildthing.db comes from a newer version of WildThing. Update this copy first.")
        snap = empty()
        links = {}
        for r in c.execute("SELECT * FROM links ORDER BY posting, url"):
            links.setdefault(r["posting"], []).append({"source": r["source"], "url": r["url"]})
        for r in c.execute("SELECT * FROM postings"):
            snap["postings"][r["uid"]] = {k: _s(r[k]) for k in POSTING_TEXT} | {"pasted": int(r["pasted"]),
                                                                                "links": links.get(r["uid"], [])}
        for r in c.execute("SELECT * FROM events"):
            snap["events"][r["uid"]] = {k: _s(r[k]) for k in EVENT_TEXT} | {"minutes": int(r["minutes"])}
        for r in c.execute("SELECT * FROM outputs"):
            snap["outputs"][f"{r['posting']}|{r['kind']}"] = {k: _s(r[k]) for k in ("posting", "kind", "content", "warnings_json", "created_at")}
        for r in c.execute("SELECT * FROM gap_plans"):
            snap["gap_plans"][r["uid"]] = {k: _s(r[k]) for k in ("scope", "content", "created_at")}
        for r in c.execute("SELECT * FROM tombstones"):
            snap["tombstones"][r["uid"]] = {"kind": r["kind"], "at": r["at"]}
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "avoided" in tables:
            for r in c.execute("SELECT * FROM avoided"):
                snap["avoided"][r["key"]] = {k: _s(r[k]) for k in ("company", "reason", "changed_at")} | {"active": int(r["active"])}
        if "tags" in tables:
            for r in c.execute("SELECT * FROM tags"):
                snap["tags"][f"{r['posting']}|{r['tag']}"] = {"posting": r["posting"], "tag": r["tag"],
                                                              "active": int(r["active"]), "changed_at": _s(r["changed_at"])}
        return snap
    finally:
        if c is not None:
            c.close()
        os.remove(path)


def write_file(snap, device):
    """A shared file holding the snapshot, as bytes."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        c = sqlite3.connect(path)
        c.executescript(SCHEMA)
        c.executemany("INSERT INTO info VALUES (?,?)", [("format", FORMAT), ("version", str(VERSION)),
                                                         ("written_at", db.now()), ("device", device)])
        for uid, p in snap["postings"].items():
            c.execute(f"INSERT INTO postings(uid, {', '.join(POSTING_TEXT)}, pasted) VALUES (?{', ?' * len(POSTING_TEXT)}, ?)",
                      (uid, *[p[k] for k in POSTING_TEXT], p["pasted"]))
            c.executemany("INSERT OR IGNORE INTO links VALUES (?,?,?)", [(uid, l["source"], l["url"]) for l in p["links"]])
        for uid, e in snap["events"].items():
            c.execute(f"INSERT INTO events(uid, {', '.join(EVENT_TEXT)}, minutes) VALUES (?{', ?' * len(EVENT_TEXT)}, ?)",
                      (uid, *[e[k] for k in EVENT_TEXT], e["minutes"]))
        for o in snap["outputs"].values():
            c.execute("INSERT INTO outputs VALUES (?,?,?,?,?)", (o["posting"], o["kind"], o["content"], o["warnings_json"], o["created_at"]))
        for uid, gp in snap["gap_plans"].items():
            c.execute("INSERT INTO gap_plans VALUES (?,?,?,?)", (uid, gp["scope"], gp["content"], gp["created_at"]))
        for uid, t in snap["tombstones"].items():
            c.execute("INSERT INTO tombstones VALUES (?,?,?)", (uid, t["kind"], t["at"]))
        for key, a in snap["avoided"].items():
            c.execute("INSERT INTO avoided VALUES (?,?,?,?,?)", (key, a["company"], a["reason"], a["active"], a["changed_at"]))
        for g in snap["tags"].values():
            c.execute("INSERT INTO tags VALUES (?,?,?,?)", (g["posting"], g["tag"], g["active"], g["changed_at"]))
        c.commit()
        c.close()
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---- this computer's jobs.db ---------------------------------------------------------------------------------------
def snapshot(conn):
    """This device's postings record in the shared shape."""
    snap = empty()
    links = {}
    for r in conn.execute("SELECT j.uid, l.source, l.url FROM job_links l JOIN jobs j ON j.id = l.job_id ORDER BY l.url"):
        links.setdefault(r["uid"], []).append({"source": r["source"], "url": r["url"]})
    uids = {}
    for r in conn.execute("SELECT * FROM jobs"):
        uids[r["id"]] = r["uid"]
        p = {k: _s(r[k]) for k in POSTING_TEXT if k not in ("status_at",)}
        p["status_at"] = _s(r["status_updated"])
        p["pasted"] = int(r["pasted"] or 0)
        p["links"] = links.get(r["uid"], [])
        snap["postings"][r["uid"]] = p
    for r in conn.execute("SELECT * FROM events"):
        if r["job_id"] in uids:
            snap["events"][r["uid"]] = {"posting": uids[r["job_id"]], "kind": _s(r["kind"]), "starts_at": _s(r["starts_at"]),
                                        "minutes": int(r["minutes"]), "place": _s(r["place"]), "notes": _s(r["notes"]),
                                        "time_zone": _s(r["time_zone"]), "changed_at": _s(r["changed_at"])}
    for r in conn.execute("SELECT * FROM outputs"):
        if r["job_id"] in uids:
            u = uids[r["job_id"]]
            snap["outputs"][f"{u}|{r['kind']}"] = {"posting": u, "kind": r["kind"], "content": _s(r["content"]),
                                                    "warnings_json": _s(r["warnings_json"]), "created_at": _s(r["created_at"])}
    for r in conn.execute("SELECT * FROM gap_plans"):
        snap["gap_plans"][r["uid"]] = {"scope": _s(r["scope"]), "content": _s(r["content"]), "created_at": _s(r["created_at"])}
    for r in conn.execute("SELECT * FROM tombstones"):
        snap["tombstones"][r["uid"]] = {"kind": r["kind"], "at": r["at"]}
    for r in conn.execute("SELECT * FROM avoided"):
        snap["avoided"][r["key"]] = {"company": _s(r["company"]), "reason": _s(r["reason"]), "active": int(r["active"]),
                                     "changed_at": _s(r["changed_at"])}
    for r in conn.execute("SELECT * FROM job_tags"):
        if r["job_id"] in uids:
            u = uids[r["job_id"]]
            snap["tags"][f"{u}|{r['tag']}"] = {"posting": u, "tag": r["tag"], "active": int(r["active"]),
                                               "changed_at": _s(r["changed_at"])}
    return snap


def base_notes(conn):
    return {r["uid"]: r["notes"] for r in conn.execute("SELECT uid, notes FROM sync_notes")}


def apply(conn, merged, rename):
    """Makes this device's jobs.db hold the merged record. Returns the ids of postings that arrived (to be scored)."""
    for old, new in rename.items():
        conn.execute("UPDATE jobs SET uid=? WHERE uid=?", (new, old))
    tomb = merged["tombstones"]
    for r in conn.execute("SELECT id, uid FROM jobs").fetchall():
        if r["uid"] in tomb:
            for t in ("job_links", "job_profiles", "outputs", "events"):
                conn.execute(f"DELETE FROM {t} WHERE job_id=?", (r["id"],))
            conn.execute("DELETE FROM jobs WHERE id=?", (r["id"],))
    for uid in tomb:
        conn.execute("DELETE FROM events WHERE uid=?", (uid,))
        conn.execute("DELETE FROM gap_plans WHERE uid=?", (uid,))

    ids = {r["uid"]: r["id"] for r in conn.execute("SELECT id, uid FROM jobs")}
    arrived = []
    for uid, p in merged["postings"].items():
        state = (p["status"], p["status_at"] or None, p["applied_on"] or None, p["notes"])
        content = tuple(p[k] for k in CONTENT)
        if uid in ids:
            jid = ids[uid]
            conn.execute(f"UPDATE jobs SET status=?, status_updated=?, applied_on=?, notes=?, "
                         f"{', '.join(k + '=?' for k in CONTENT)}, pasted=? WHERE id=? AND "
                         f"(status IS NOT ? OR status_updated IS NOT ? OR applied_on IS NOT ? OR notes IS NOT ? OR "
                         f"{' OR '.join(k + ' IS NOT ?' for k in CONTENT)} OR pasted IS NOT ?)",
                         (*state, *content, p["pasted"], jid, *state, *content, p["pasted"]))
        else:
            cur = conn.execute(
                "INSERT OR IGNORE INTO jobs(uid, source, ext_id, title, company, location, url, description, posted, pasted, "
                "status, status_updated, applied_on, notes, added_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uid, p["source"], p["ext_id"], *content, p["pasted"], *state, p["added_at"] or db.now()))
            if not cur.rowcount:
                continue
            jid = ids[uid] = cur.lastrowid
            arrived.append(jid)
        for l in p["links"]:
            conn.execute("INSERT OR IGNORE INTO job_links(job_id, source, url) VALUES (?,?,?)", (jid, l["source"], l["url"]))

    have = {r["uid"]: r for r in conn.execute("SELECT * FROM events")}
    for uid, e in merged["events"].items():
        jid = ids.get(e["posting"])
        if jid is None:
            continue
        vals = (jid, e["kind"], e["starts_at"], e["minutes"], e["place"], e["notes"], e["time_zone"], e["changed_at"])
        if uid not in have:
            conn.execute("INSERT INTO events(uid, job_id, kind, starts_at, minutes, place, notes, time_zone, changed_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?)", (uid, *vals))
        elif (have[uid]["changed_at"] or "") != e["changed_at"]:
            conn.execute("UPDATE events SET job_id=?, kind=?, starts_at=?, minutes=?, place=?, notes=?, time_zone=?, changed_at=? "
                         "WHERE uid=?", (*vals, uid))
    for o in merged["outputs"].values():
        jid = ids.get(o["posting"])
        if jid is None:
            continue
        cur = conn.execute("SELECT created_at FROM outputs WHERE job_id=? AND kind=?", (jid, o["kind"])).fetchone()
        if cur is None or (cur["created_at"] or "") < o["created_at"]:
            conn.execute("INSERT OR REPLACE INTO outputs(job_id, kind, content, warnings_json, files_json, created_at) "
                         "VALUES (?,?,?,?,'[]',?)", (jid, o["kind"], o["content"], o["warnings_json"], o["created_at"]))
    plans = {r["uid"] for r in conn.execute("SELECT uid FROM gap_plans")}
    for uid, gp in merged["gap_plans"].items():
        if uid not in plans:
            conn.execute("INSERT INTO gap_plans(uid, scope, content, file, created_at) VALUES (?,?,?,'',?)",
                         (uid, gp["scope"], gp["content"], gp["created_at"]))
    have_avoid = {r["key"]: tuple(r) for r in conn.execute("SELECT key, company, reason, active, changed_at FROM avoided")}
    for key, a in merged["avoided"].items():
        if have_avoid.get(key) != (key, a["company"], a["reason"], a["active"], a["changed_at"]):
            conn.execute("INSERT OR REPLACE INTO avoided(key, company, reason, active, changed_at) VALUES (?,?,?,?,?)",
                         (key, a["company"], a["reason"], a["active"], a["changed_at"]))
    have_tags = {(r["job_id"], r["tag"]): (r["active"], r["changed_at"]) for r in conn.execute("SELECT * FROM job_tags")}
    for g in merged["tags"].values():
        jid = ids.get(g["posting"])
        if jid is not None and have_tags.get((jid, g["tag"])) != (g["active"], g["changed_at"]):
            conn.execute("INSERT OR REPLACE INTO job_tags(job_id, tag, active, changed_at) VALUES (?,?,?,?)",
                         (jid, g["tag"], g["active"], g["changed_at"]))
    conn.execute("DELETE FROM tombstones")
    conn.executemany("INSERT INTO tombstones(uid, kind, at) VALUES (?,?,?)", [(u, t["kind"], t["at"]) for u, t in tomb.items()])
    conn.execute("DELETE FROM sync_notes")
    conn.executemany("INSERT INTO sync_notes(uid, notes) VALUES (?,?)", [(u, p["notes"]) for u, p in merged["postings"].items()])
    conn.commit()
    return arrived


def sync(conn, folder, device):
    """One pass: every copy of wildthing.db in the folder is merged in (Drive can hold two after uploads that crossed),
    then one fresh copy goes back. Returns {"arrived": [job ids], "postings": count}."""
    here = snapshot(conn)
    base = base_notes(conn)
    copies = folder.read_all(FILE)
    rename = {}
    for data in reversed(copies):                       # oldest first, so the newest copy's changes land last
        res = merge(here, read_file(data), base)
        rename.update({k: v for k, v in res["rename"].items()})
        here = res["merged"]
    arrived = apply(conn, here, rename)
    folder.replace(FILE, write_file(here, device))
    return {"arrived": arrived, "postings": len(here["postings"])}
