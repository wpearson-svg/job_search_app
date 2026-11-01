"""Export and import of everything a user has, as one JSON file. The same format is read and written by the
Android app, so data can move between a PC and a phone. The format is described in docs/formats.md.

API keys are never exported.
"""
import base64
import json
import os

import db
import settings

FORMAT = "wildthing-export"
VERSION = 1
# The settings a person sets for themselves; everything else in config.json stays the app's default.
SETTING_KEYS = ("your_name", "target_titles", "search_keywords", "locations", "greenhouse_boards", "lever_companies",
                "usajobs", "sources", "send_resume_in_requests", "resume_check_phrases")
JOB_COLS = ("id", "source", "ext_id", "title", "company", "location", "url", "description", "posted", "pasted",
            "status", "score", "title_match", "added_at", "applied_on", "notes", "status_updated")


def export_data(conn, app="desktop"):
    cfg = settings.load()
    rp = settings.resume_path(cfg)
    resume = None
    if rp:
        with open(rp, "rb") as f:
            resume = {"filename": "master_resume" + os.path.splitext(rp)[1].lower(),
                      "base64": base64.b64encode(f.read()).decode("ascii")}
    links, tags = {}, {}
    for r in conn.execute("SELECT job_id, source, url FROM job_links ORDER BY job_id, url"):
        links.setdefault(r["job_id"], []).append({"source": r["source"], "url": r["url"]})
    for r in conn.execute("SELECT job_id, profile_id FROM job_profiles ORDER BY job_id, profile_id"):
        tags.setdefault(r["job_id"], []).append(r["profile_id"])
    marks = db.job_tags(conn)
    jobs = []
    for r in conn.execute("SELECT * FROM jobs ORDER BY id"):
        j = {k: r[k] for k in JOB_COLS}
        j["pasted"], j["title_match"] = bool(j["pasted"]), bool(j["title_match"])
        j["matched"], j["gaps"], j["flags"] = (json.loads(r[k]) for k in ("matched_json", "gaps_json", "flags_json"))
        j["profile_ids"] = tags.get(r["id"], [])
        j["links"] = links.get(r["id"], [])
        j["tags"] = marks.get(r["id"], [])
        jobs.append(j)
    return {
        "format": FORMAT, "version": VERSION, "exported_at": db.now(), "app": app,
        "settings": {k: cfg[k] for k in SETTING_KEYS if k in cfg},
        "resume": resume,
        "instructions": settings.instructions_text(cfg) if settings.has_custom_instructions(cfg) else None,
        "extras": [dict(r) for r in conn.execute("SELECT term, added_at FROM extras ORDER BY term")],
        "profiles": [dict(r) for r in conn.execute("SELECT id, name, keywords, titles, location FROM profiles ORDER BY id")],
        "jobs": jobs,
        "events": [dict(r) | {"time_zone": None} for r in
                   conn.execute("SELECT id, job_id, kind, starts_at, minutes, place, notes FROM events ORDER BY id")],
        "outputs": [{"job_id": r["job_id"], "kind": r["kind"], "content": r["content"],
                     "warnings": json.loads(r["warnings_json"]), "created_at": r["created_at"]}
                    for r in conn.execute("SELECT * FROM outputs ORDER BY job_id, kind")],
        "gap_plans": [dict(r) for r in conn.execute("SELECT scope, content, created_at FROM gap_plans ORDER BY id")],
        "avoided": [{"company": a["company"], "reason": a["reason"]} for a in db.avoided(conn).values()],
    }


def check(data):
    """Returns a plain reason the file cannot be imported, or None when it can."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return "That is not a WildThing export file."
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        return "That file comes from a newer version of WildThing. Update this copy first."
    return None


def import_data(conn, data):
    """Replaces everything in this copy with the file's contents. API keys are left as they are. What the file
    replaced is not recorded as deleted, so the shared postings database (shared_db.py) does not delete it elsewhere."""
    problem = check(data)
    if problem:
        raise ValueError(problem)
    for t in ("job_links", "job_profiles", "job_tags", "events", "outputs", "gap_plans", "queue_items", "extras", "jobs",
              "profiles", "avoided"):
        conn.execute(f"DELETE FROM {t}")
    for p in data.get("profiles", []):
        conn.execute("INSERT INTO profiles(id, name, keywords, titles, location) VALUES (?,?,?,?,?)",
                     (p["id"], p["name"], p.get("keywords", ""), p.get("titles", ""), p.get("location", "")))
    for j in data.get("jobs", []):
        conn.execute(
            "INSERT INTO jobs(id, source, ext_id, title, company, location, url, description, posted, pasted, status, score, "
            "matched_json, gaps_json, flags_json, title_match, added_at, applied_on, notes, status_updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (j["id"], j["source"], j["ext_id"], j.get("title", ""), j.get("company", ""), j.get("location", ""),
             j.get("url", ""), j.get("description", ""), j.get("posted", ""), int(bool(j.get("pasted"))),
             j.get("status", "new"), int(j.get("score", 0)), json.dumps(j.get("matched", [])),
             json.dumps(j.get("gaps", [])), json.dumps(j.get("flags", [])), int(bool(j.get("title_match"))),
             j.get("added_at") or db.now(), j.get("applied_on"), j.get("notes", ""), j.get("status_updated")))
        for pid in j.get("profile_ids", []):
            conn.execute("INSERT OR IGNORE INTO job_profiles(job_id, profile_id) VALUES (?,?)", (j["id"], pid))
        for link in j.get("links", []):
            conn.execute("INSERT OR IGNORE INTO job_links(job_id, source, url) VALUES (?,?,?)", (j["id"], link["source"], link["url"]))
        for t in j.get("tags", []):
            db.set_tag(conn, j["id"], t, True)
    for e in data.get("events", []):
        # The desktop keeps local times without a zone; a time zone from the phone is kept only in the phone's copy.
        conn.execute("INSERT INTO events(id, job_id, kind, starts_at, minutes, place, notes) VALUES (?,?,?,?,?,?,?)",
                     (e["id"], e["job_id"], e["kind"], e["starts_at"][:16], e.get("minutes", 60), e.get("place", ""), e.get("notes", "")))
    for o in data.get("outputs", []):
        conn.execute("INSERT OR REPLACE INTO outputs(job_id, kind, content, warnings_json, files_json, created_at) VALUES (?,?,?,?,?,?)",
                     (o["job_id"], o["kind"], o["content"], json.dumps(o.get("warnings", [])), "[]", o.get("created_at") or db.now()))
    for g in data.get("gap_plans", []):
        conn.execute("INSERT INTO gap_plans(scope, content, file, created_at) VALUES (?,?,'',?)",
                     (g["scope"], g["content"], g.get("created_at") or db.now()))
    for a in data.get("avoided", []):
        db.set_avoided(conn, a.get("company", ""), a.get("reason", ""), True)
    for x in data.get("extras", []):
        conn.execute("INSERT OR IGNORE INTO extras(term, added_at) VALUES (?,?)", (x["term"], x.get("added_at") or db.now()))
    conn.execute("DELETE FROM tombstones")              # replaced, not deleted: see the note above
    conn.execute("DELETE FROM sync_notes")
    conn.commit()
    s = {k: v for k, v in (data.get("settings") or {}).items() if k in SETTING_KEYS}
    if s:
        settings.save_user(s)
    settings.save_instructions(data.get("instructions") or "")
    r = data.get("resume")
    if r and r.get("base64"):
        ok, msg = settings.save_resume(r.get("filename", "master_resume.txt"), base64.b64decode(r["base64"]))
        if not ok:
            raise ValueError("The resume in that file could not be used: " + msg)
