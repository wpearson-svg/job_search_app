"""Job search helper: local web app. Run with run.bat (Windows) or `python app.py`, then open http://127.0.0.1:5050.

What it does: pulls postings from open sources, lets you paste postings from LinkedIn/Indeed, scores each against your
master resume, and turns the gaps into one plan. It never edits your resume and never invents experience.
"""
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from flask import Flask, Response, flash, g, redirect, render_template, request, url_for

import db
import gaps as gapmod
import matcher
import resume as resumemod
import settings
import sources
import writer

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = "local-only-not-a-secret"


def get_conn():
    """One database connection per request, closed when the request ends."""
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.errorhandler(Exception)
def show_error(exc):
    """Local-only app: show the real error on the page (and in the console) instead of a blank 'Internal Server Error'."""
    import html
    import traceback
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return exc
    tb = traceback.format_exc()
    print(tb, flush=True)
    return ("<h2>Something went wrong</h2><p>Copy everything below and send it over.</p><pre style='white-space:pre-wrap'>"
            + html.escape(tb) + "</pre><p><a href='/'>Back</a></p>"), 500


@app.teardown_appcontext
def close_conn(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def keys_path():
    return app.config.get("KEYS_PATH") or os.path.join(HERE, "keys.local.json")


def load_keys():
    try:
        with open(keys_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_json(name, default):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default


def cfg():
    """config.json defaults with this user's own settings (data/user_settings.json) laid over them."""
    return settings.load()


LEX = matcher.load_lexicon()


@app.context_processor
def inject_statuses():
    c = cfg()
    return {"statuses": db.STATUSES, "status_label": db.STATUS_LABEL, "applied_stages": db.APPLIED_STAGES,
            "setup_missing": [m for m, bad in (("a master resume", not settings.resume_path(c)),
                                               ("the job titles you want", not c.get("target_titles"))) if bad]}


@app.template_filter("safe_url")
def safe_url(u):
    """Only web links are ever put on a button or link; anything else (javascript:, file:) is dropped."""
    u = (u or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


def resume_text():
    p = settings.resume_path(cfg())
    return resumemod.read_resume(p) if p else ""


def with_context(message):
    """When settings say so, puts the instructions and master resume in front of a request, so it works in any
    Claude chat. If your Claude project already holds them, switch that off in Settings."""
    c = cfg()
    if not c.get("send_resume_in_requests", True):
        return message
    r = resume_text().strip()
    return ("<instructions>\n" + settings.instructions_text(c).strip() + "\n</instructions>\n\n"
            + ("<master_resume>\n" + r + "\n</master_resume>\n\n" if r else "") + message)


def have_terms(conn):
    extras = {r["term"] for r in conn.execute("SELECT term FROM extras")}
    return matcher.find_terms(resume_text(), LEX) | extras


def score_into(conn, job_id, title, text, have):
    res = matcher.score_job(title, text, have, LEX, cfg().get("target_titles", []))
    conn.execute("UPDATE jobs SET score=?, matched_json=?, gaps_json=?, flags_json=?, title_match=? WHERE id=?",
                 (res["score"], json.dumps(res["matched"]), json.dumps(res["gaps"]), json.dumps(res["flags"]),
                  int(res["title_match"]), job_id))


def rescore_all(conn):
    have = have_terms(conn)
    for r in conn.execute("SELECT id, title, description FROM jobs").fetchall():
        score_into(conn, r["id"], r["title"], r["description"], have)
    conn.commit()


@app.route("/")
def index():
    conn = get_conn()
    status = request.args.get("status", "active")
    min_score = int(request.args.get("min", cfg().get("min_score_to_show", 0)) or 0)
    sql = "SELECT * FROM jobs WHERE score >= ?"
    args = [min_score]
    if status == "active":
        sql += " AND status != 'dismissed'"
    elif status != "all":
        sql += " AND status = ?"
        args.append(status)
    profile = request.args.get("profile", "")
    if profile.isdigit():
        sql += " AND id IN (SELECT job_id FROM job_profiles WHERE profile_id=?)"
        args.append(int(profile))
    sort = request.args.get("sort", "score")
    order = {"score": "score DESC, id DESC",
             "applied": "applied_on IS NULL, applied_on DESC, id DESC",
             "newest": "id DESC"}.get(sort, "score DESC, id DESC")
    sql += " ORDER BY " + order
    jobs = [db.row_to_job(r) for r in conn.execute(sql, args)]
    allowed = cfg().get("locations", [])
    for j in jobs:
        j["location_ok"] = matcher.location_ok(j["location"], j["description"], allowed)
    profs = ensure_profiles(conn)
    tags = {}
    for r in conn.execute("SELECT jp.job_id, p.name FROM job_profiles jp JOIN profiles p ON p.id=jp.profile_id ORDER BY p.name"):
        tags.setdefault(r["job_id"], []).append(r["name"])
    purge_counts = {"outside": len(purge_candidates(conn, "outside")), "untouched": len(purge_candidates(conn, "untouched"))}
    return render_template("index.html", jobs=jobs, status=status, min_score=min_score, sort=sort, purge_counts=purge_counts,
                           profiles=profs, profile=profile, tags=tags)


def lines(text):
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


def ensure_profiles(conn):
    """First use: one 'General' profile built from the keywords and titles already in config.json."""
    if not conn.execute("SELECT 1 FROM profiles LIMIT 1").fetchone():
        c = cfg()
        conn.execute("INSERT INTO profiles(name, keywords, titles, location) VALUES ('General', ?, ?, '')",
                     ("\n".join(c.get("search_keywords", [])), "\n".join(c.get("target_titles", []))))
        conn.commit()
    return [dict(r) for r in conn.execute("SELECT * FROM profiles ORDER BY id")]


def profile_cfg(pr):
    """config.json with this profile's keywords, titles and place swapped in."""
    c = json.loads(json.dumps(cfg()))
    kws = lines(pr["keywords"])
    if kws:
        c["search_keywords"] = kws
    titles = lines(pr["titles"]) or kws
    if titles:
        c["target_titles"] = titles
    if pr["location"].strip():
        for key, field in (("linkedin", "location"), ("jobspy", "location"), ("adzuna", "where"), ("usajobs", "location")):
            c.setdefault(key, {})[field] = pr["location"].strip()
    return c


def tag(conn, job_id, profile_id):
    conn.execute("INSERT OR IGNORE INTO job_profiles(job_id, profile_id) VALUES (?,?)", (job_id, profile_id))


@app.post("/fetch")
def fetch():
    conn = get_conn()
    keys = load_keys()
    profiles = ensure_profiles(conn)
    want = request.form.get("profile", "all")
    if want != "all":
        profiles = [p for p in profiles if str(p["id"]) == want]
        if not profiles:
            flash("That profile no longer exists.")
            return redirect(url_for("index"))
    have = have_terms(conn)
    allowed = cfg().get("locations", [])
    total = new = skipped = merged = 0
    known = {}                                 # dup key -> [(id, location)] for postings already saved
    for r in conn.execute("SELECT id, title, company, location FROM jobs"):
        k = db.dup_key(r["title"], r["company"])
        if k:
            known.setdefault(k, []).append((r["id"], r["location"]))
    reports = []
    for pr in profiles:
        found, report = sources.fetch_all(profile_cfg(pr), keys)
        total += len(found)
        reports += [(pr["name"] if len(profiles) > 1 else "", n, c, e) for n, c, e in report]
        for j in found:
            if not matcher.location_ok(j["location"], j["description"], allowed):
                skipped += 1                  # outside your areas: never saved
                continue
            k = db.dup_key(j["title"], j["company"])
            twin = next((i for i, loc in known.get(k, []) if db.same_place(loc, j["location"])), None) if k else None
            if twin:                           # already saved (maybe from another source): keep its link, tag it, do not list it twice
                own = conn.execute("SELECT url FROM jobs WHERE id=?", (twin,)).fetchone()["url"]
                if j["url"] and j["url"] != own:
                    conn.execute("INSERT OR IGNORE INTO job_links(job_id, source, url) VALUES (?,?,?)", (twin, j["source"], j["url"]))
                if not conn.execute("SELECT 1 FROM jobs WHERE source=? AND ext_id=?", (j["source"], j["ext_id"])).fetchone():
                    merged += 1
                tag(conn, twin, pr["id"])
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO jobs(source, ext_id, title, company, location, url, description, posted, added_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (j["source"], j["ext_id"], j["title"], j["company"], j["location"], j["url"], j["description"],
                 j["posted"], db.now()))
            if cur.rowcount:
                new += 1
                if k:
                    known.setdefault(k, []).append((cur.lastrowid, j["location"]))
                score_into(conn, cur.lastrowid, j["title"], j["description"], have)
                tag(conn, cur.lastrowid, pr["id"])
            else:                              # saved before: just add this profile's tag
                row = conn.execute("SELECT id FROM jobs WHERE source=? AND ext_id=?", (j["source"], j["ext_id"])).fetchone()
                if row:
                    tag(conn, row["id"], pr["id"])
    conn.commit()
    who = profiles[0]["name"] if len(profiles) == 1 else f"{len(profiles)} profiles"
    flash(f"{who}: fetched {total} postings, {new} new, {skipped} skipped for being outside your areas, {merged} already listed from another source.")
    for prof, name, n, err in reports:
        flash((f"{prof} / " if prof else "") + f"{name}: {n} postings" + (f" ({err})" if err else ""))
    return redirect(url_for("index"))


# ---- Profiles: named searches that decide what Fetch looks for, and tag what it finds ----
@app.route("/profiles")
def profiles_page():
    conn = get_conn()
    profs = ensure_profiles(conn)
    for p in profs:
        p["count"] = conn.execute("SELECT COUNT(*) FROM job_profiles WHERE profile_id=?", (p["id"],)).fetchone()[0]
    return render_template("profiles.html", profiles=profs)


@app.post("/profiles/save")
def save_profile():
    conn = get_conn()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Give the profile a name.")
        return redirect(url_for("profiles_page"))
    vals = (name, request.form.get("keywords", "").strip(), request.form.get("titles", "").strip(),
            request.form.get("location", "").strip())
    pid = request.form.get("id", "").strip()
    try:
        if pid:
            conn.execute("UPDATE profiles SET name=?, keywords=?, titles=?, location=? WHERE id=?", vals + (int(pid),))
        else:
            conn.execute("INSERT INTO profiles(name, keywords, titles, location) VALUES (?,?,?,?)", vals)
        conn.commit()
        flash(f"Saved profile: {name}.")
    except sqlite3.IntegrityError:
        flash("A profile with that name already exists.")
    return redirect(url_for("profiles_page"))


@app.post("/profiles/<int:pid>/delete")
def delete_profile(pid):
    conn = get_conn()
    conn.execute("DELETE FROM job_profiles WHERE profile_id=?", (pid,))   # postings stay; only the tag goes
    conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
    conn.commit()
    flash("Profile removed. Its postings are still in the list.")
    return redirect(url_for("profiles_page"))


def purge_candidates(conn, scope):
    """Ids of fetched postings you have not touched (status New, not pasted or logged by you).
    scope 'outside' narrows that to the ones outside your locations. Saved, applied, dismissed ones are never included."""
    allowed = cfg().get("locations", [])
    ids = []
    for r in conn.execute("SELECT id, location, description FROM jobs WHERE pasted=0 AND status='new'"):
        if scope == "outside" and matcher.location_ok(r["location"], r["description"], allowed):
            continue
        ids.append(r["id"])
    return ids


@app.post("/purge")
def purge():
    scope = request.form.get("scope", "outside")
    if scope not in ("outside", "untouched"):
        return "bad scope", 400
    conn = get_conn()
    ids = purge_candidates(conn, scope)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        conn.execute(f"DELETE FROM outputs WHERE job_id IN ({marks})", chunk)
        conn.execute(f"DELETE FROM job_profiles WHERE job_id IN ({marks})", chunk)
        conn.execute(f"DELETE FROM jobs WHERE id IN ({marks})", chunk)
    conn.commit()
    flash(f"Removed {len(ids)} posting(s).")
    return redirect(url_for("index"))


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        title = request.form.get("title", "").strip()
        if not text:
            flash("Paste the posting text first.")
            return render_template("add.html", form=request.form)
        conn = get_conn()
        n = conn.execute("SELECT COUNT(*) FROM jobs WHERE pasted=1").fetchone()[0] + 1
        cur = conn.execute(
            "INSERT INTO jobs(source, ext_id, title, company, location, url, description, pasted, added_at) "
            "VALUES ('pasted', ?, ?, ?, ?, ?, ?, 1, ?)",
            (f"paste-{n}-{db.now()}", title or "(untitled posting)", request.form.get("company", "").strip(),
             request.form.get("location", "").strip(), request.form.get("url", "").strip(), text, db.now()))
        score_into(conn, cur.lastrowid, title, text, have_terms(conn))
        conn.commit()
        return redirect(url_for("job", job_id=cur.lastrowid))
    return render_template("add.html", form={})


@app.route("/job/<int:job_id>")
def job(job_id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        return "No such posting", 404
    outs = {o["kind"]: {"content": o["content"], "warnings": json.loads(o["warnings_json"]),
                        "files": json.loads(o["files_json"]), "created_at": o["created_at"]}
            for o in conn.execute("SELECT * FROM outputs WHERE job_id=?", (job_id,))}
    job_d = db.row_to_job(r)
    keys = load_keys()
    has_key = bool(keys.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"))
    links = [dict(x) for x in conn.execute("SELECT source, url FROM job_links WHERE job_id=?", (job_id,))]
    events = [event_view(e, job_d) for e in conn.execute("SELECT * FROM events WHERE job_id=? ORDER BY starts_at", (job_id,))]
    prep = outs.get("prep")
    return render_template("job.html", j=job_d, lex=LEX, outs=outs, has_key=has_key, links=links, events=events,
                           prep=prep, prep_sections=writer.parse_prep(prep["content"]) if prep else [],
                           pkg_prep=with_context(writer.build_prep_message(job_d)), event_kinds=EVENT_KINDS,
                           now_local=datetime.now().strftime("%Y-%m-%dT%H:%M"),
                           pkg_resume=with_context(writer.build_user_message(job_d, False)),
                           pkg_cover=with_context(writer.build_user_message(job_d, True)))


@app.post("/job/<int:job_id>/build")
def build(job_id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        return "No such posting", 404
    want_cover = bool(request.form.get("cover_letter"))
    try:
        res = writer.generate(db.row_to_job(r), want_cover, cfg(), load_keys())
    except Exception as e:  # show the reason on the page instead of a crash
        flash(f"Could not build: {e}")
        return redirect(url_for("job", job_id=job_id))
    store_outputs(conn, job_id, res["parts"], res["warnings"], res["files"])
    flash("Built. Files are in the output folder next to the app.")
    return redirect(url_for("job", job_id=job_id) + "#documents")


def store_outputs(conn, job_id, parts, warnings, files):
    conn.execute("DELETE FROM outputs WHERE job_id=? AND kind IN ('resume','cover_letter','review_notes')", (job_id,))
    for kind, text in parts.items():
        if text:
            conn.execute("INSERT INTO outputs(job_id, kind, content, warnings_json, files_json, created_at) VALUES (?,?,?,?,?,?)",
                         (job_id, kind, text, json.dumps(warnings if kind == "resume" else []),
                          json.dumps(files), db.now()))
    conn.commit()


def apply_resume_reply(conn, job_id, text):
    """Keeps a resume / cover letter reply with the posting and saves it as files. Returns a note, or None."""
    r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    parts = writer.parse_blocks(text)
    note = None
    if not parts["resume"]:
        # The project may answer in plain text without the tags: keep the whole reply as the resume.
        parts = {"resume": text, "cover_letter": None, "review_notes": None}
        note = "No <resume> tags found, so the whole reply was kept as the resume."
    warnings = writer.check_resume(parts["resume"], cfg().get("resume_check_phrases"))
    files = writer.save_files(db.row_to_job(r), parts, cfg())
    store_outputs(conn, job_id, parts, warnings, files)
    return note


def apply_prep_reply(conn, job_id, text):
    r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    path = writer.save_prep(db.row_to_job(r), text, cfg())
    conn.execute("INSERT OR REPLACE INTO outputs(job_id, kind, content, warnings_json, files_json, created_at) VALUES (?,?,?,?,?,?)",
                 (job_id, "prep", text, "[]", json.dumps([path]), db.now()))
    conn.commit()


def apply_gap_reply(conn, scope, text):
    path = writer.save_gap_plan(scope, text, gapmod.parse_plan(text), cfg())
    conn.execute("INSERT INTO gap_plans(scope, content, file, created_at) VALUES (?,?,?,?)", (scope, text, path, db.now()))
    conn.commit()


@app.post("/job/<int:job_id>/import")
def import_reply(job_id):
    """Takes the reply pasted back from the Claude project, keeps it with the posting and saves it as files."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
        return "No such posting", 404
    text = request.form.get("reply", "").strip()
    if not text:
        flash("Paste Claude's reply first.")
        return redirect(url_for("job", job_id=job_id) + "#documents")
    note = apply_resume_reply(conn, job_id, text)
    if note:
        flash(note)
    flash("Saved. Files are in the output folder next to the app.")
    return redirect(url_for("job", job_id=job_id) + "#documents")


@app.post("/job/<int:job_id>/prep")
def import_prep(job_id):
    """Keeps the interview-prep reply pasted back from the Claude project, and saves it as a markdown file."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
        return "No such posting", 404
    text = request.form.get("reply", "").strip()
    if not text:
        flash("Paste Claude's reply first.")
        return redirect(url_for("job", job_id=job_id) + "#prep")
    apply_prep_reply(conn, job_id, text)
    flash("Interview prep saved. The file is in the output folder next to the app.")
    return redirect(url_for("job", job_id=job_id) + "#prep")


# ---- Interviews and follow-ups: Google Calendar link and .ics files ----------
EVENT_KINDS = ["Phone screen", "Interview", "Follow-up", "Other"]
ICS_STAMP = "%Y%m%dT%H%M%S"


def _event_times(e):
    start = datetime.fromisoformat(e["starts_at"])
    return start, start + timedelta(minutes=int(e["minutes"] or 60))


def event_view(e, job):
    d = dict(e)
    start, end = _event_times(e)
    d["title"] = f"{e['kind']}: {job['title']}" + (f" at {job['company']}" if job.get("company") else "")
    d["when"] = start.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
    details = [e["notes"] or "", ("Posting: " + job["url"]) if db_url_ok(job.get("url")) else ""]
    d["gcal"] = ("https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + quote(d["title"])
                 + "&dates=" + start.strftime(ICS_STAMP) + "/" + end.strftime(ICS_STAMP)
                 + "&details=" + quote("\n".join(x for x in details if x)) + "&location=" + quote(e["place"] or ""))
    d["past"] = start < datetime.now()
    return d


def db_url_ok(u):
    return (u or "").lower().startswith(("http://", "https://"))


def _ics_escape(t):
    return (t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line):
    out, line = [], line
    while len(line) > 72:
        out.append(line[:72])
        line = " " + line[72:]
    out.append(line)
    return "\r\n".join(out)


def ics_for(rows):
    """rows: list of (event row, job dict). Times are written as local time (no zone), so the calendar uses its own."""
    stamp = datetime.now(timezone.utc).strftime(ICS_STAMP) + "Z"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//job-search-app//EN", "CALSCALE:GREGORIAN"]
    for e, job in rows:
        v = event_view(e, job)
        start, end = _event_times(e)
        desc = "\n".join(x for x in [e["notes"] or "", ("Posting: " + job["url"]) if db_url_ok(job.get("url")) else ""] if x)
        lines += ["BEGIN:VEVENT", f"UID:event-{e['id']}@job-search-app", f"DTSTAMP:{stamp}",
                  f"DTSTART:{start.strftime(ICS_STAMP)}", f"DTEND:{end.strftime(ICS_STAMP)}",
                  "SUMMARY:" + _ics_escape(v["title"]), "LOCATION:" + _ics_escape(e["place"]),
                  "DESCRIPTION:" + _ics_escape(desc), "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


@app.post("/job/<int:job_id>/event")
def add_event(job_id):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
        return "No such posting", 404
    kind = request.form.get("kind", "Interview")
    if kind not in EVENT_KINDS:
        kind = "Other"
    try:
        start = datetime.fromisoformat(request.form.get("starts_at", ""))
        minutes = max(5, min(int(request.form.get("minutes") or 60), 600))
    except ValueError:
        flash("Pick a date and time for the event.")
        return redirect(url_for("job", job_id=job_id) + "#calendar")
    conn.execute("INSERT INTO events(job_id, kind, starts_at, minutes, place, notes) VALUES (?,?,?,?,?,?)",
                 (job_id, kind, start.strftime("%Y-%m-%dT%H:%M"), minutes, request.form.get("place", "").strip(),
                  request.form.get("notes", "").strip()))
    conn.commit()
    flash(f"{kind} added. Use the buttons beside it to put it in Google Calendar.")
    return redirect(url_for("job", job_id=job_id) + "#calendar")


@app.post("/event/<int:event_id>/delete")
def delete_event(event_id):
    conn = get_conn()
    r = conn.execute("SELECT job_id FROM events WHERE id=?", (event_id,)).fetchone()
    if not r:
        return "No such event", 404
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    return redirect(url_for("job", job_id=r["job_id"]) + "#calendar")


@app.get("/event/<int:event_id>.ics")
def event_ics(event_id):
    conn = get_conn()
    e = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not e:
        return "No such event", 404
    job = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (e["job_id"],)).fetchone())
    return Response(ics_for([(e, job)]), mimetype="text/calendar",
                    headers={"Content-Disposition": f"attachment; filename=event-{event_id}.ics"})


@app.get("/calendar.ics")
def calendar_ics():
    """Every event not yet past, in one file you can import into Google Calendar (Settings > Import & export)."""
    conn = get_conn()
    rows = []
    for e in conn.execute("SELECT * FROM events ORDER BY starts_at"):
        job = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (e["job_id"],)).fetchone())
        rows.append((e, job))
    return Response(ics_for(rows), mimetype="text/calendar", headers={"Content-Disposition": "attachment; filename=job-search.ics"})


def upcoming_events(conn, days=30):
    out = []
    horizon = datetime.now() + timedelta(days=days)
    for e in conn.execute("SELECT * FROM events ORDER BY starts_at"):
        start = datetime.fromisoformat(e["starts_at"])
        if datetime.now() - timedelta(hours=2) <= start <= horizon:
            job = db.row_to_job(conn.execute("SELECT * FROM jobs WHERE id=?", (e["job_id"],)).fetchone())
            v = event_view(e, job)
            v["job_id"] = job["id"]
            out.append(v)
    return out


# ---- Weekly summary --------------------------------------------------------------
@app.route("/weekly")
def weekly():
    conn = get_conn()
    try:
        days = max(1, min(int(request.args.get("days", 7)), 90))
    except ValueError:
        days = 7
    since = (date.today() - timedelta(days=days)).isoformat()
    jobs = [db.row_to_job(r) for r in conn.execute("SELECT * FROM jobs")]
    applied = [j for j in jobs if j.get("applied_on") and j["applied_on"] >= since]
    moved = [j for j in jobs if (j.get("status_updated") or "")[:10] >= since
             and j["status"] in ("phone_screen", "interview", "offer", "rejected")]
    interviews = [j for j in moved if j["status"] in ("phone_screen", "interview", "offer")]
    rejected = [j for j in moved if j["status"] == "rejected"]
    today = date.today()
    waiting = [j for j in jobs if j["status"] == "applied" and j.get("applied_on")
               and (today - date.fromisoformat(j["applied_on"])).days >= 14]
    upcoming = upcoming_events(conn, 14)
    lines = [f"Job search, last {days} days:", f"- {len(applied)} application(s) sent"]
    if interviews:
        lines.append(f"- {len(interviews)} moved to a phone screen or interview")
    if rejected:
        lines.append(f"- {len(rejected)} closed out")
    if upcoming:
        lines.append(f"- {len(upcoming)} interview or follow-up coming up in the next 2 weeks")
    if waiting:
        lines.append(f"- {len(waiting)} application(s) waiting 14+ days with no word, due for a follow-up")
    summary = "\n".join(lines)
    rate = f"{round(100 * len(interviews) / len(applied))}%" if applied else "n/a"
    return render_template("weekly.html", days=days, applied=applied, interviews=interviews, rejected=rejected,
                           waiting=waiting, upcoming=upcoming, summary=summary, rate=rate)


# ---- Merge duplicates already in the list -----------------------------------------
def merge_duplicates(conn):
    """Folds duplicate postings together. Only untouched, fetched copies are removed; their links go to the one kept."""
    groups = {}
    for r in conn.execute("SELECT id, title, company, location, url, source, status, pasted, score FROM jobs"):
        k = db.dup_key(r["title"], r["company"])
        if k:
            groups.setdefault(k, []).append(dict(r))
    removed = 0
    for rows in groups.values():
        pool = list(rows)
        while pool:
            base = pool.pop(0)
            same = [base] + [b for b in pool if db.same_place(base["location"], b["location"])]
            pool = [b for b in pool if b not in same]
            if len(same) < 2:
                continue
            keeper = sorted(same, key=lambda x: (x["status"] == "new" and not x["pasted"], -x["score"], x["id"]))[0]
            for dup in same:
                if dup is keeper or dup["status"] != "new" or dup["pasted"]:
                    continue
                if dup["url"]:
                    conn.execute("INSERT OR IGNORE INTO job_links(job_id, source, url) VALUES (?,?,?)",
                                 (keeper["id"], dup["source"], dup["url"]))
                conn.execute("UPDATE job_links SET job_id=? WHERE job_id=?", (keeper["id"], dup["id"]))
                conn.execute("INSERT OR IGNORE INTO job_profiles(job_id, profile_id) SELECT ?, profile_id FROM job_profiles WHERE job_id=?",
                             (keeper["id"], dup["id"]))
                conn.execute("DELETE FROM job_profiles WHERE job_id=?", (dup["id"],))
                conn.execute("DELETE FROM outputs WHERE job_id=?", (dup["id"],))
                conn.execute("DELETE FROM jobs WHERE id=?", (dup["id"],))
                removed += 1
    conn.commit()
    return removed


@app.post("/dedupe")
def dedupe():
    n = merge_duplicates(get_conn())
    flash(f"Merged {n} duplicate posting(s)." if n else "No duplicates found.")
    return redirect(url_for("index"))


@app.post("/job/<int:job_id>/status")
def set_status(job_id):
    status = request.form.get("status", "new")
    if status not in db.STATUS_LABEL:
        return "bad status", 400
    conn = get_conn()
    conn.execute("UPDATE jobs SET status=?, status_updated=? WHERE id=?", (status, db.now(), job_id))
    if status in db.APPLIED_STAGES:  # the first time a posting becomes an application, note today as the date
        conn.execute("UPDATE jobs SET applied_on=? WHERE id=? AND applied_on IS NULL", (date.today().isoformat(), job_id))
    conn.commit()
    return redirect(request.referrer or url_for("index"))


@app.post("/job/<int:job_id>/apply")
def apply_to(job_id):
    """The Apply button: marks the posting Applied (never moves a later stage back) and notes today's date."""
    conn = get_conn()
    r = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        return "No such posting", 404
    if r["status"] not in db.APPLIED_STAGES:
        conn.execute("UPDATE jobs SET status='applied', status_updated=? WHERE id=?", (db.now(), job_id))
    conn.execute("UPDATE jobs SET applied_on=? WHERE id=? AND applied_on IS NULL", (date.today().isoformat(), job_id))
    conn.commit()
    return "", 204


@app.post("/job/<int:job_id>/application")
def set_application(job_id):
    applied_on = request.form.get("applied_on", "").strip() or None
    if applied_on:
        try:
            datetime.strptime(applied_on, "%Y-%m-%d")
        except ValueError:
            flash("Use the date picker for the applied date.")
            return redirect(request.referrer or url_for("applications"))
    conn = get_conn()
    conn.execute("UPDATE jobs SET applied_on=?, notes=?, status_updated=? WHERE id=?",
                 (applied_on, request.form.get("notes", "").strip(), db.now(), job_id))
    conn.commit()
    return redirect(request.referrer or url_for("applications"))


STAGE_ORDER = ["offer", "interview", "phone_screen", "applied", "no_response", "rejected", "withdrawn"]


@app.route("/applications")
def applications():
    conn = get_conn()
    qs = ",".join("?" * len(db.APPLIED_STAGES))
    rows = [db.row_to_job(r) for r in conn.execute(f"SELECT * FROM jobs WHERE status IN ({qs})", db.APPLIED_STAGES)]
    today = date.today()
    for j in rows:
        j["days"] = None
        if j.get("applied_on"):
            try:
                j["days"] = (today - date.fromisoformat(j["applied_on"])).days
            except ValueError:
                pass
        j["follow_up"] = j["status"] == "applied" and j["days"] is not None and j["days"] >= 14
    rows.sort(key=lambda j: (STAGE_ORDER.index(j["status"]), -(j["days"] or 0) if j["status"] == "applied" else (j["days"] or 0)))
    counts = {k: sum(1 for j in rows if j["status"] == k) for k in db.APPLIED_STAGES}
    return render_template("applications.html", jobs=rows, counts=counts, today=today.isoformat(),
                           upcoming=upcoming_events(conn, 30))


@app.post("/applications/log")
def log_application():
    """Records an application made somewhere else, for a job that is not in the app."""
    title = request.form.get("title", "").strip()
    if not title:
        flash("Give the job a title.")
        return redirect(url_for("applications"))
    status = request.form.get("status", "applied")
    if status not in db.APPLIED_STAGES:
        status = "applied"
    applied_on = request.form.get("applied_on", "").strip() or date.today().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO jobs(source, ext_id, title, company, location, url, description, pasted, status, applied_on, "
        "status_updated, added_at) VALUES ('logged', ?, ?, ?, ?, ?, '', 1, ?, ?, ?, ?)",
        (f"logged-{db.now()}", title, request.form.get("company", "").strip(), request.form.get("location", "").strip(),
         request.form.get("url", "").strip(), status, applied_on, db.now(), db.now()))
    conn.commit()
    flash(f"Logged: {title}.")
    return redirect(url_for("applications"))


def _int_arg(name, default, lo, hi):
    try:
        return max(lo, min(int(request.values.get(name, default)), hi))
    except ValueError:
        return default


def gap_scope(conn):
    """Postings the gap plan covers, from the page's filters: profile, minimum score."""
    profile = request.values.get("profile", "")
    sql, args = "SELECT * FROM jobs WHERE status != 'dismissed' AND score >= ?", [_int_arg("min", 0, 0, 100)]
    focus = "all postings"
    if profile.isdigit():
        sql += " AND id IN (SELECT job_id FROM job_profiles WHERE profile_id=?)"
        args.append(int(profile))
        row = conn.execute("SELECT name FROM profiles WHERE id=?", (int(profile),)).fetchone()
        focus = f'the "{row["name"]}" profile' if row else focus
    jobs = [db.row_to_job(r) for r in conn.execute(sql, args)]
    return jobs, focus, profile


# ---- Folder queue: request files out, reply files in ---------------------------------------------------------
QUEUE_KINDS = {"resume": "Resume", "resume_cover": "Resume and cover letter", "prep": "Interview prep", "gap": "Gap plan"}


def queue_root():
    return app.config.get("QUEUE_ROOT", HERE)


def _queue_path(folder, name=""):
    d = os.path.join(queue_root(), folder)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name) if name else d


def write_todo(conn):
    waiting = conn.execute("SELECT * FROM queue_items WHERE status='waiting' ORDER BY id").fetchall()
    c = cfg()
    lines = ["# Work to do", "",
             "Each request below is a file in `requests/`. Open it, follow it, and write your answer to the matching file in "
             "`replies/` (same file name). Skip any request whose reply file already exists.", ""]
    if c.get("send_resume_in_requests", True):
        lines += ["Each request file already contains my instructions and my master resume. Use only facts from my master "
                  "resume. Do not invent experience.", ""]
    else:
        lines += ["Use the instructions and master resume you already hold for me. Use only facts from my master resume. "
                  "Do not invent experience.", ""]
    if not waiting:
        lines.append("Nothing waiting.")
    for it in waiting:
        lines.append(f"- [ ] `requests/{it['name']}`  ->  `replies/{it['name']}`   ({QUEUE_KINDS.get(it['kind'], it['kind'])})")
    with open(os.path.join(queue_root(), "TODO.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def queue_add(conn, kind, job_id, scope, label, message):
    """Writes the request file and adds it to the queue. Returns the file name."""
    cur = conn.execute("INSERT INTO queue_items(kind, job_id, scope, created_at) VALUES (?,?,?,?)", (kind, job_id, scope, db.now()))
    name = f"{cur.lastrowid:03d}_{kind}_{writer.slug(label)}.md"
    conn.execute("UPDATE queue_items SET name=? WHERE id=?", (name, cur.lastrowid))
    c = cfg()
    if c.get("send_resume_in_requests", True):
        context = "My instructions and my master resume are included below. Use only facts from them."
    else:
        context = "Use the instructions and master resume you already hold for me, and only facts from the master resume."
    body = (f"# Request: {QUEUE_KINDS[kind]}, {label}\n\n"
            f"Write your answer to `replies/{name}` in this folder. {context} Follow the reply format described below. "
            "The reply file should contain the tagged parts and nothing else.\n\n---\n\n" + with_context(message) + "\n")
    with open(_queue_path("requests", name), "w", encoding="utf-8") as f:
        f.write(body)
    _queue_path("replies")
    conn.commit()
    write_todo(conn)
    return name


def import_replies(conn):
    """Reads every waiting item whose reply file exists and files it where a pasted reply would go."""
    got = skipped = 0
    for it in conn.execute("SELECT * FROM queue_items WHERE status='waiting' ORDER BY id").fetchall():
        path = _queue_path("replies", it["name"])
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
        if not text:
            continue
        try:
            if it["kind"] == "gap":
                apply_gap_reply(conn, it["scope"] or "all postings", text)
            elif not conn.execute("SELECT 1 FROM jobs WHERE id=?", (it["job_id"],)).fetchone():
                conn.execute("UPDATE queue_items SET status='skipped' WHERE id=?", (it["id"],))
                skipped += 1
                continue
            elif it["kind"] == "prep":
                apply_prep_reply(conn, it["job_id"], text)
            else:
                apply_resume_reply(conn, it["job_id"], text)
        except Exception as e:                       # leave it waiting so nothing is lost
            flash(f"Could not import {it['name']}: {e}")
            continue
        conn.execute("UPDATE queue_items SET status='imported', imported_at=? WHERE id=?", (db.now(), it["id"]))
        got += 1
    conn.commit()
    write_todo(conn)
    return got, skipped


@app.route("/queue")
def queue_page():
    conn = get_conn()
    items = []
    for r in conn.execute("SELECT q.*, j.title, j.company FROM queue_items q LEFT JOIN jobs j ON j.id=q.job_id ORDER BY q.id DESC"):
        d = dict(r)
        d["label"] = QUEUE_KINDS.get(d["kind"], d["kind"])
        d["what"] = (d["title"] + (" at " + d["company"] if d["company"] else "")) if d["title"] else d["scope"]
        d["reply_ready"] = os.path.exists(_queue_path("replies", d["name"])) if d["status"] == "waiting" else False
        items.append(d)
    return render_template("queue.html", items=items, folder=queue_root(), waiting=sum(1 for i in items if i["status"] == "waiting"))


@app.post("/queue/import")
def queue_import():
    got, skipped = import_replies(get_conn())
    flash(f"Imported {got} reply file(s)." if got else "No new reply files found in the replies folder.")
    if skipped:
        flash(f"{skipped} skipped because the posting was removed.")
    return redirect(url_for("queue_page"))


@app.post("/queue/<int:item_id>/delete")
def queue_delete(item_id):
    conn = get_conn()
    conn.execute("DELETE FROM queue_items WHERE id=?", (item_id,))
    conn.commit()
    write_todo(conn)
    return redirect(url_for("queue_page"))


@app.post("/job/<int:job_id>/queue")
def queue_job(job_id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        return "No such posting", 404
    kind = request.form.get("kind", "resume")
    if kind not in ("resume", "resume_cover", "prep"):
        return "bad kind", 400
    job_d = db.row_to_job(r)
    msg = writer.build_prep_message(job_d) if kind == "prep" else writer.build_user_message(job_d, kind == "resume_cover")
    queue_add(conn, kind, job_id, "", job_d.get("company") or job_d["title"], msg)
    flash(f"{QUEUE_KINDS[kind]} request written to the requests folder and added to TODO.md.")
    return redirect(request.referrer or url_for("job", job_id=job_id))


@app.post("/gaps/queue")
def queue_gaps():
    conn = get_conn()
    jobs, focus, _profile = gap_scope(conn)
    rows, _phases = gapmod.build_plan(jobs, LEX)
    extras = [r["term"] for r in conn.execute("SELECT term FROM extras")]
    msg = gapmod.build_message(rows, jobs, LEX, focus, extras, _int_arg("hours", 5, 1, 40), _int_arg("weeks", 12, 1, 52),
                               _int_arg("top", 15, 3, 40))
    queue_add(conn, "gap", None, focus, focus, msg)
    flash("Gap plan request written to the requests folder and added to TODO.md.")
    return redirect(url_for("queue_page"))


@app.route("/gaps")
def gaps_page():
    conn = get_conn()
    profs = ensure_profiles(conn)
    jobs, focus, profile = gap_scope(conn)
    rows, phases = gapmod.build_plan(jobs, LEX)
    hours, weeks, top = _int_arg("hours", 5, 1, 40), _int_arg("weeks", 12, 1, 52), _int_arg("top", 15, 3, 40)
    extras = [r["term"] for r in conn.execute("SELECT term FROM extras")]
    message = with_context(gapmod.build_message(rows, jobs, LEX, focus, extras, hours, weeks, top))
    plans = []
    for r in conn.execute("SELECT * FROM gap_plans ORDER BY id DESC"):
        d = dict(r)
        d["sections"] = gapmod.parse_plan(d["content"])
        plans.append(d)
    return render_template("gaps.html", rows=rows, phases=phases, count=len(jobs), message=message, focus=focus,
                           profiles=profs, profile=profile, min_score=_int_arg("min", 0, 0, 100),
                           hours=hours, weeks=weeks, top=top, plans=plans)


@app.post("/gaps/plan")
def save_gap_plan():
    text = request.form.get("reply", "").strip()
    scope = request.form.get("scope", "").strip() or "all postings"
    back = request.form.get("back", "")
    if not text:
        flash("Paste Claude's reply first.")
        return redirect(url_for("gaps_page") + back)
    apply_gap_reply(get_conn(), scope, text)
    flash("Plan saved. The file is in the output folder next to the app.")
    return redirect(url_for("gaps_page") + back + "#saved")


@app.post("/gaps/plan/<int:plan_id>/delete")
def delete_gap_plan(plan_id):
    conn = get_conn()
    conn.execute("DELETE FROM gap_plans WHERE id=?", (plan_id,))
    conn.commit()
    return redirect(url_for("gaps_page") + "#saved")


@app.post("/have")
def have():
    term = request.form.get("term", "")
    conn = get_conn()
    if term in LEX:
        conn.execute("INSERT OR IGNORE INTO extras(term, added_at) VALUES (?,?)", (term, db.now()))
        conn.commit()
        rescore_all(conn)
        flash(f'Marked "{term}" as something you have. Postings re-scored. Add it to your resume only if it is true.')
    return redirect(request.referrer or url_for("gaps_page"))


@app.post("/unhave")
def unhave():
    conn = get_conn()
    conn.execute("DELETE FROM extras WHERE term=?", (request.form.get("term", ""),))
    conn.commit()
    rescore_all(conn)
    return redirect(url_for("resume_page"))


@app.route("/resume")
def resume_page():
    conn = get_conn()
    text = resume_text()
    found = sorted(matcher.find_terms(text, LEX))
    extras = sorted(r["term"] for r in conn.execute("SELECT term FROM extras"))
    return render_template("resume.html", found=found, extras=extras, name=os.path.basename(settings.resume_path(cfg()) or "") or "none yet", chars=len(text))


KEY_FIELDS = (("anthropic_api_key", "Anthropic API key (only for writing resumes straight from the app; not needed for the copy-and-paste way)"),
              ("adzuna_app_id", "Adzuna app id"), ("adzuna_app_key", "Adzuna app key"),
              ("usajobs_key", "USAJOBS key"), ("usajobs_email", "USAJOBS email"))


def _lines(text):
    return [l.strip() for l in (text or "").replace(",", "\n").splitlines() if l.strip()]


@app.route("/settings")
def settings_page():
    c = cfg()
    keys = load_keys()
    rp = settings.resume_path(c)
    return render_template("settings.html", c=c, resume_name=os.path.basename(rp) if rp else "",
                           has_custom=settings.has_custom_instructions(c),
                           instructions=settings.instructions_text(c),
                           key_fields=KEY_FIELDS, key_set={k for k, _ in KEY_FIELDS if keys.get(k)})


@app.post("/settings")
def settings_save():
    f = request.form
    place = f.get("place", "").strip()
    patch = {
        "your_name": f.get("your_name", "").strip(),
        "target_titles": [t.lower() for t in _lines(f.get("target_titles"))],
        "search_keywords": [t.lower() for t in _lines(f.get("search_keywords"))],
        "locations": [t.lower() for t in _lines(f.get("locations"))],
        "send_resume_in_requests": f.get("claude_has_resume") != "on",
        "jobspy": {"enabled": f.get("jobspy_enabled") == "on", "location": place},
        "linkedin": {"enabled": f.get("linkedin_enabled") == "on", "location": place},
        "adzuna": {"where": place},
        "usajobs": {"location": place},
    }
    settings.save_user(patch)
    settings.save_instructions("" if f.get("reset_instructions") == "on" else f.get("instructions", ""))
    keys = load_keys()
    changed = False
    for k, _ in KEY_FIELDS:
        v = f.get(k, "").strip()
        if v:
            keys[k] = v
            changed = True
    if f.get("clear_keys") == "on":
        keys, changed = {}, True
    if changed:
        with open(keys_path(), "w", encoding="utf-8") as fh:
            json.dump(keys, fh, indent=2)
    flash("Settings saved.")
    return redirect(url_for("settings_page"))


@app.post("/settings/resume")
def settings_resume():
    up = request.files.get("resume")
    if not up or not up.filename:
        flash("Choose a resume file first.")
        return redirect(url_for("settings_page"))
    ok, msg = settings.save_resume(up.filename, up.read())
    flash(msg)
    if ok:
        rescore_all(get_conn())
    return redirect(url_for("settings_page"))


@app.post("/rescore")
def rescore():
    conn = get_conn()
    rescore_all(conn)
    flash("Re-scored every posting against the current resume.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
