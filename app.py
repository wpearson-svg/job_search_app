"""WildThing, a job search helper: local web app. Run with run.bat (Windows) or `python app.py`, then open http://127.0.0.1:5050.

What it does: pulls postings from open sources, lets you paste postings from LinkedIn/Indeed, scores each against your
master resume, and turns the gaps into one plan. It never edits your resume and never invents experience.
"""
import json
import os
import secrets
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from flask import Flask, Response, flash, g, redirect, render_template, request, session, url_for

import aiqueue
import career
import db
import exchange
import gaps as gapmod
import gdrive
import home
import matcher
import resume as resumemod
import settings
import shared_db
import shared_details
import sources
import tracking
import usersync
import workfolder
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
    return app.config.get("KEYS_PATH") or os.path.join(home.ROOT or HERE, "keys.local.json")


def load_keys():
    """The keys this app uses. Anything else in the file (such as an old Anthropic key) is ignored and dropped on save."""
    try:
        with open(keys_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    known = {k for k, _ in KEY_FIELDS}
    return {k: v for k, v in data.items() if k in known} if isinstance(data, dict) else {}


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
            "tag_defs": db.TAGS, "tag_label": db.tag_label, "tag_label_map": db.TAG_LABEL,
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
    AI chat. If your assistant already holds them (a project or saved chat), switch that off in Settings."""
    c = cfg()
    if not c.get("send_resume_in_requests", True):
        return message
    return writer.with_context(message, settings.instructions_text(c), resume_text())


def scoring_source():
    """What postings are scored against: the career file when there is a usable one, else the master resume.
    Returns (text, "career" or "resume")."""
    data = settings.load_career()
    if data and not career.validate(data):
        return career.text(data), "career"
    return resume_text(), "resume"


def have_terms(conn):
    return matcher.find_terms(scoring_source()[0], LEX) | usersync.confirmed_skills(conn)


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
    if "state" in request.args and ("code" in request.args or "error" in request.args):
        return google_finish()
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
    ptags = db.job_tags(conn)
    tag_f = request.args.get("tag", "")
    if tag_f:
        jobs = [j for j in jobs if tag_f in ptags.get(j["id"], [])]
    avoid = db.avoided(conn)
    show_avoided = request.args.get("avoided") == "1"
    for j in jobs:
        j["avoided"] = db.norm(j["company"]) in avoid
    hidden = sum(1 for j in jobs if j["avoided"])
    if not show_avoided:
        jobs = [j for j in jobs if not j["avoided"]]
    allowed = cfg().get("locations", [])
    for j in jobs:
        j["location_ok"] = matcher.location_ok(j["location"], j["description"], allowed)
        j["ptags"] = ptags.get(j["id"], [])
    tags_in_use = sorted({t for ts in ptags.values() for t in ts}, key=lambda t: (t not in db.TAG_LABEL, db.tag_label(t).lower()))
    profs = ensure_profiles(conn)
    tags = {}
    for r in conn.execute("SELECT jp.job_id, p.name FROM job_profiles jp JOIN profiles p ON p.id=jp.profile_id ORDER BY p.name"):
        tags.setdefault(r["job_id"], []).append(r["name"])
    purge_counts = {"outside": len(purge_candidates(conn, "outside")), "untouched": len(purge_candidates(conn, "untouched"))}
    sel = request.args.get("sel", "")
    selected = panel_data(conn, int(sel), tags) if sel.isdigit() else None
    keep = {"status": status, "min": min_score, "sort": sort, "profile": profile, "tag": tag_f,
            "avoided": "1" if show_avoided else ""}
    return render_template("index.html", jobs=jobs, status=status, min_score=min_score, sort=sort, purge_counts=purge_counts,
                           profiles=profs, profile=profile, tags=tags, sel=selected, keep=keep, tag_f=tag_f,
                           tags_in_use=tags_in_use, show_avoided=show_avoided, hidden=hidden,
                           dash=None if selected else dashboard_data(conn), event_kinds=EVENT_KINDS,
                           now_local=datetime.now().strftime("%Y-%m-%dT%H:%M"))


def panel_data(conn, job_id, tags):
    """Everything the two side panels show about one posting (and about you, for that posting)."""
    r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        return None
    j = db.row_to_job(r)
    j["tags"] = tags.get(job_id, [])
    j["links"] = [dict(x) for x in conn.execute("SELECT source, url FROM job_links WHERE job_id=?", (job_id,))]
    j["events"] = [event_view(e, j) for e in conn.execute("SELECT * FROM events WHERE job_id=? ORDER BY starts_at", (job_id,))]
    j["outs"] = {o["kind"]: o["created_at"] for o in conn.execute("SELECT kind, created_at FROM outputs WHERE job_id=?", (job_id,))}
    waiting = {q["kind"] for q in conn.execute("SELECT kind FROM queue_items WHERE job_id=? AND status='waiting'", (job_id,))}
    j["waiting"] = {"resume": bool(waiting & {"resume", "resume_cover"}), "cover_letter": "resume_cover" in waiting, "prep": "prep" in waiting}
    j["required"] = [t for t, w in j["gaps"] if w >= 2]
    j["preferred"] = [t for t, w in j["gaps"] if w < 2]
    j["follow_up"] = tracking.needs_follow_up(j["status"], j.get("applied_on"), date.today())
    add_marks(conn, j)
    return j


def add_marks(conn, j):
    """This posting's tags and, when you avoid its company, that record."""
    j["ptags"] = db.job_tags(conn, j["id"]).get(j["id"], [])
    j["avoid"] = db.avoided(conn).get(db.norm(j["company"]))


def dashboard_data(conn):
    """What the right panel shows when no posting is selected."""
    today = date.today()
    follow = []
    for r in conn.execute("SELECT id, title, company, applied_on FROM jobs WHERE status='applied' AND applied_on IS NOT NULL ORDER BY applied_on"):
        days = tracking.days_since(r["applied_on"], today)
        if days is not None and days >= tracking.FOLLOW_UP_DAYS:
            follow.append({"id": r["id"], "title": r["title"], "company": r["company"], "days": days})
    weight = {}
    for r in conn.execute("SELECT gaps_json FROM jobs WHERE status != 'dismissed'"):
        for t, w in json.loads(r["gaps_json"]):
            weight[t] = weight.get(t, 0) + w
    top = sorted(weight.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return {"follow": follow[:5], "follow_total": len(follow), "events": upcoming_events(conn, 14)[:5],
            "waiting": conn.execute("SELECT COUNT(*) FROM queue_items WHERE status='waiting'").fetchone()[0],
            "gaps": top}


def back_to(default):
    """Where to go after a panel form: a local path the form named, else the default. Never an outside address."""
    p = request.form.get("back", "")
    return p if p.startswith("/") and not p.startswith("//") else default


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
    sync_postings(conn)
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
        sync_shared(conn)
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
    sync_shared(conn)
    return redirect(url_for("profiles_page"))


def purge_candidates(conn, scope):
    """Ids of fetched postings you have not touched (status New, not pasted or logged by you, no tags).
    scope 'outside' narrows that to the ones outside your locations. Saved, applied, dismissed ones are never included."""
    allowed = cfg().get("locations", [])
    ids = []
    for r in conn.execute("SELECT id, location, description FROM jobs WHERE pasted=0 AND status='new' "
                          "AND id NOT IN (SELECT job_id FROM job_tags WHERE active=1)"):
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
    add_marks(conn, job_d)
    links = [dict(x) for x in conn.execute("SELECT source, url FROM job_links WHERE job_id=?", (job_id,))]
    events = [event_view(e, job_d) for e in conn.execute("SELECT * FROM events WHERE job_id=? ORDER BY starts_at", (job_id,))]
    prep = outs.get("prep")
    return render_template("job.html", j=job_d, lex=LEX, outs=outs, links=links, events=events,
                           prep=prep, prep_sections=writer.parse_prep(prep["content"]) if prep else [],
                           pkg_prep=with_context(writer.build_prep_message(job_d)), event_kinds=EVENT_KINDS,
                           now_local=datetime.now().strftime("%Y-%m-%dT%H:%M"),
                           pkg_resume=with_context(writer.build_user_message(job_d, False)),
                           pkg_cover=with_context(writer.build_user_message(job_d, True)))


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
    """Takes the reply pasted back from your AI, keeps it with the posting and saves it as files."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
        return "No such posting", 404
    text = request.form.get("reply", "").strip()
    if not text:
        flash("Paste your AI's reply first.")
        return redirect(url_for("job", job_id=job_id) + "#documents")
    note = apply_resume_reply(conn, job_id, text)
    if note:
        flash(note)
    flash("Saved. Files are in the output folder next to the app.")
    return redirect(url_for("job", job_id=job_id) + "#documents")


@app.post("/job/<int:job_id>/prep")
def import_prep(job_id):
    """Keeps the interview-prep reply pasted back from your AI, and saves it as a markdown file."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
        return "No such posting", 404
    text = request.form.get("reply", "").strip()
    if not text:
        flash("Paste your AI's reply first.")
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
        return redirect(back_to(url_for("job", job_id=job_id) + "#calendar"))
    conn.execute("INSERT INTO events(job_id, kind, starts_at, minutes, place, notes) VALUES (?,?,?,?,?,?)",
                 (job_id, kind, start.strftime("%Y-%m-%dT%H:%M"), minutes, request.form.get("place", "").strip(),
                  request.form.get("notes", "").strip()))
    conn.commit()
    flash(f"{kind} added. Use the buttons beside it to put it in Google Calendar.")
    return redirect(back_to(url_for("job", job_id=job_id) + "#calendar"))


@app.post("/event/<int:event_id>/delete")
def delete_event(event_id):
    conn = get_conn()
    r = conn.execute("SELECT job_id FROM events WHERE id=?", (event_id,)).fetchone()
    if not r:
        return "No such event", 404
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    return redirect(back_to(url_for("job", job_id=r["job_id"]) + "#calendar"))


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
    waiting = [j for j in jobs if tracking.needs_follow_up(j["status"], j.get("applied_on"), today)]
    upcoming = upcoming_events(conn, 14)
    summary = tracking.weekly_summary(days, len(applied), len(interviews), len(rejected), len(upcoming), len(waiting))
    rate = tracking.interview_rate(len(applied), len(interviews))
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
                conn.execute("INSERT OR IGNORE INTO job_tags(job_id, tag, active, changed_at) "
                             "SELECT ?, tag, active, changed_at FROM job_tags WHERE job_id=?", (keeper["id"], dup["id"]))
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


@app.post("/job/<int:job_id>/tags")
def set_tags(job_id):
    """Saves the posting's tags: the boxes ticked, plus one you typed."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
        return "No such posting", 404
    want = {t for t in request.form.getlist("tag") if t in db.TAG_LABEL or t.startswith(db.CUSTOM)}
    custom = db.custom_tag(request.form.get("custom", ""))
    if custom:
        same = [t for t in db.TAG_LABEL if db.TAG_LABEL[t].lower() == custom[len(db.CUSTOM):].lower()]
        want.add(same[0] if same else custom)          # typing "Possible scam" ticks the box rather than adding a copy
    have = set(db.job_tags(conn, job_id).get(job_id, []))
    for t in have - want:
        db.set_tag(conn, job_id, t, False)
    for t in want - have:
        db.set_tag(conn, job_id, t, True)
    conn.commit()
    return redirect(back_to(url_for("index", sel=job_id)))


@app.post("/avoid")
def avoid():
    """Avoids a company (on=1) or stops avoiding it (on=0)."""
    conn = get_conn()
    company = request.form.get("company", "")
    on = request.form.get("on") == "1"
    if not db.set_avoided(conn, company, request.form.get("reason", ""), on):
        flash("That posting has no company name to avoid.")
    else:
        conn.commit()
        flash(f"Avoiding {company.strip()}. Its postings are hidden; tick \"Show avoided\" to see them." if on
              else f"No longer avoiding {company.strip()}.")
    return redirect(back_to(url_for("index")))


STAGE_ORDER = ["offer", "interview", "phone_screen", "applied", "no_response", "rejected", "withdrawn"]


@app.route("/applications")
def applications():
    conn = get_conn()
    qs = ",".join("?" * len(db.APPLIED_STAGES))
    rows = [db.row_to_job(r) for r in conn.execute(f"SELECT * FROM jobs WHERE status IN ({qs})", db.APPLIED_STAGES)]
    today = date.today()
    for j in rows:
        j["days"] = tracking.days_since(j.get("applied_on"), today)
        j["follow_up"] = tracking.needs_follow_up(j["status"], j.get("applied_on"), today)
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


# ---- AI work queue: request files out, reply files in (format in aiqueue.py and docs/formats.md) ---------------
QUEUE_KINDS = aiqueue.KINDS
INSTRUCTIONS_SRC = os.path.join(HERE, "docs", "AI_INSTRUCTIONS.md")
_SUFFIX_CHARS = "abcdefghijkmnpqrstuvwxyz23456789"


def drive_on(c=None):
    """True when this computer uses Google Drive directly for the queue and the shared details."""
    return bool((c or cfg()).get("use_drive")) and (app.config.get("DRIVE") is not None or gdrive.linked())


def drive_home():
    """The WildThing folder in Google Drive (one per request, so folder lookups are not repeated)."""
    if "drive_home" not in g:
        keys = load_keys()
        drive = app.config.get("DRIVE") or gdrive.Drive(gdrive.Auth(keys.get("google_client_id", ""),
                                                                    keys.get("google_client_secret", "")))
        g.drive_home = workfolder.DriveDir(drive, "WildThing", permanent=bool(cfg().get("drive_permanent_delete")))
    return g.drive_home


def queue_dir():
    """The work folder: the WildThing folder in Google Drive when it is linked and switched on, else this computer's
    folder setting, else the data folder (home.py)."""
    if app.config.get("QUEUE_ROOT"):
        return workfolder.LocalDir(app.config["QUEUE_ROOT"])
    if drive_on():
        return drive_home()
    return workfolder.LocalDir(cfg().get("queue_folder") or home.ROOT or HERE)


def queue_root():
    """Where the queue is, as words for the page."""
    return queue_dir().label


def write_instructions():
    """Puts AI_INSTRUCTIONS.md in the work folder, and refreshes it when the app's copy has changed."""
    with open(INSTRUCTIONS_SRC, encoding="utf-8") as f:
        text = f.read()
    qd = queue_dir()
    if qd.text(aiqueue.INSTRUCTIONS_FILE) != text:
        qd.write(aiqueue.INSTRUCTIONS_FILE, text.encode("utf-8"))


def _open_batch(conn):
    """New requests join the newest batch until a reply report for it has been seen."""
    place = queue_root()
    r = conn.execute("SELECT batch FROM queue_batches WHERE report_seen=0 AND done=0 AND place IN (?, '') "
                     "ORDER BY created_at DESC, batch DESC LIMIT 1", (place,)).fetchone()
    if r:
        return r["batch"]
    batch = aiqueue.batch_id(datetime.now(), "".join(secrets.choice(_SUFFIX_CHARS) for _ in range(4)))
    conn.execute("INSERT INTO queue_batches(batch, created_at, place) VALUES (?,?,?)", (batch, db.now(), place))
    return batch


def write_batch_todo(conn, batch):
    """requests/TODO_<batch>.md, listing the items still waiting."""
    items = [{"n": r["n"], "kind": r["kind"], "label": r["label"]}
             for r in conn.execute("SELECT * FROM queue_items WHERE batch=? AND status='waiting' ORDER BY n", (batch,))]
    created = conn.execute("SELECT created_at FROM queue_batches WHERE batch=?", (batch,)).fetchone()[0]
    text = aiqueue.render_todo(batch, settings.device_id(), created, items, cfg().get("send_resume_in_requests", True))
    queue_dir().sub("requests").write(aiqueue.todo_name(batch), text.encode("utf-8"))


def queue_add(conn, kind, job_id, scope, label, message):
    """Writes the request file, adds it to the open batch and rewrites that batch's TODO. Returns the file name."""
    batch = _open_batch(conn)
    n = (conn.execute("SELECT MAX(n) FROM queue_items WHERE batch=?", (batch,)).fetchone()[0] or 0) + 1
    name = aiqueue.item_name(batch, n, kind, label)
    conn.execute("INSERT INTO queue_items(kind, job_id, scope, name, status, created_at, batch, n, label) "
                 "VALUES (?,?,?,?, 'waiting', ?,?,?,?)", (kind, job_id, scope, name, db.now(), batch, n, label))
    try:
        queue_dir().sub("requests").write(name, aiqueue.render_request(batch, n, kind, label, with_context(message)).encode("utf-8"))
        queue_dir().sub("replies").ensure()
        write_instructions()
        conn.commit()
        write_batch_todo(conn, batch)
    except OSError:
        conn.rollback()                                  # nothing half-sent stays in the record
        raise
    return name


def _other_places(conn):
    """Batches still waiting in a different work folder (made before the folder or Drive setting changed)."""
    return conn.execute("SELECT place, COUNT(*) AS n FROM queue_batches WHERE done=0 AND place NOT IN (?, '') "
                        "GROUP BY place", (queue_root(),)).fetchall()


def queue_state(conn):
    """For each unfinished batch this copy made in this work folder: its row, its waiting items by number, and the
    plan from the files."""
    qd = queue_dir()
    present = {f["name"] for f in qd.sub("requests").files()}
    rdir = qd.sub("replies")
    replies = rdir.files()
    out = []
    for b in conn.execute("SELECT * FROM queue_batches WHERE done=0 AND place IN (?, '') ORDER BY created_at, batch",
                          (qd.label,)).fetchall():
        items = {r["n"]: r for r in conn.execute(
            "SELECT * FROM queue_items WHERE batch=? AND status='waiting' ORDER BY n", (b["batch"],))}
        report = rdir.text(aiqueue.reply_todo_name(b["batch"]))
        plan = aiqueue.plan_import([{"n": n, "name": r["name"]} for n, r in items.items()], present, replies, report)
        out.append({"batch": b, "items": items, "plan": plan, "replies": replies, "report": report is not None})
    return out


def _finish_batch(conn, batch):
    """Once nothing in a batch is waiting, its two TODO files go too. Otherwise its TODO lists what is left."""
    if conn.execute("SELECT 1 FROM queue_items WHERE batch=? AND status='waiting'", (batch,)).fetchone():
        write_batch_todo(conn, batch)
        return False
    queue_dir().sub("requests").remove(aiqueue.todo_name(batch))
    queue_dir().sub("replies").remove(aiqueue.reply_todo_name(batch))
    conn.execute("UPDATE queue_batches SET done=1 WHERE batch=?", (batch,))
    conn.commit()
    return True


def import_replies(conn):
    """Files every reply that is back, then cleans up in an order that loses nothing if it stops half way: save the
    reply, confirm, delete its reply and request files; when the batch is all done, delete its TODO files.
    Returns (imported, problems): problems are lines to show (skipped, failed, missing, could not import)."""
    got, problems = 0, []
    rdir, reqdir = queue_dir().sub("replies"), queue_dir().sub("requests")
    for st in queue_state(conn):
        batch = st["batch"]["batch"]
        for x in st["plan"]["items"]:
            it = st["items"][x["n"]]
            if x["action"] == "gone":
                conn.execute("UPDATE queue_items SET status='removed' WHERE id=?", (it["id"],))
                continue
            if x["action"] in ("skipped", "failed", "missing"):
                conn.execute("UPDATE queue_items SET note=? WHERE id=?", (f"{x['action']}: {x['reason']}", it["id"]))
                problems.append(f"{QUEUE_KINDS[it['kind']]}, {it['label']}: {x['action']}. {x['reason']}")
                continue
            if x["action"] != "import":
                continue
            reply_name = st["replies"][x["reply"]]["name"]
            text = (rdir.text(reply_name) or "").strip()
            if not text:
                continue
            try:
                if it["kind"] == "gap":
                    apply_gap_reply(conn, it["scope"] or "all postings", text)
                elif not conn.execute("SELECT 1 FROM jobs WHERE id=?", (it["job_id"],)).fetchone():
                    problems.append(f"{QUEUE_KINDS[it['kind']]}, {it['label']}: the posting was removed, so the reply was not kept.")
                elif it["kind"] == "prep":
                    apply_prep_reply(conn, it["job_id"], text)
                else:
                    apply_resume_reply(conn, it["job_id"], text)
            except Exception as e:                       # leave its files in place so nothing is lost
                problems.append(f"Could not import {reply_name}: {e}")
                continue
            conn.execute("UPDATE queue_items SET status='imported', imported_at=?, note='' WHERE id=?", (db.now(), it["id"]))
            conn.commit()                                # saved: now its files can go
            for name in {st["replies"][i]["name"] for i in x["delete"]}:
                rdir.remove(name)
            reqdir.remove(it["name"])
            got += 1
        if st["report"]:
            conn.execute("UPDATE queue_batches SET report_seen=1 WHERE batch=?", (batch,))
        conn.commit()
        _finish_batch(conn, batch)
    return got, problems


@app.route("/queue")
def queue_page():
    """Opening the page imports whatever has come back, then shows each batch as the files say."""
    conn = get_conn()
    try:
        got, problems = import_replies(conn)
        states = queue_state(conn)
    except OSError as e:
        flash(f"Could not reach the work folder: {e}")
        got, problems, states = 0, [], []
    if got:
        flash(f"Imported {got} reply file(s).")
    labels = {"waiting": "Waiting for a reply", "import": "Reply found", "missing": "Reported done, reply file not there yet",
              "skipped": "Skipped", "failed": "Failed"}
    batches = []
    for st in states:
        rows = []
        for x in st["plan"]["items"]:
            it = dict(st["items"][x["n"]])
            job = conn.execute("SELECT title, company FROM jobs WHERE id=?", (it["job_id"],)).fetchone() if it["job_id"] else None
            it["what"] = (job["title"] + (" at " + job["company"] if job["company"] else "")) if job else it["scope"]
            it["state"], it["reason"], it["type"] = labels.get(x["action"], x["action"]), x["reason"], QUEUE_KINDS[it["kind"]]
            rows.append(it)
        if rows:
            batches.append({"id": st["batch"]["batch"], "report": st["report"], "rows": rows})
    done = [dict(r) | {"type": QUEUE_KINDS.get(r["kind"], r["kind"])} for r in
            conn.execute("SELECT * FROM queue_items WHERE status='imported' ORDER BY imported_at DESC LIMIT 15")]
    unused = not conn.execute("SELECT 1 FROM queue_batches LIMIT 1").fetchone()
    return render_template("queue.html", batches=batches, done=done, problems=problems, folder=queue_root(),
                           unused=unused, waiting=sum(len(b["rows"]) for b in batches), elsewhere=_other_places(conn))


@app.route("/queue/help")
def queue_help():
    return render_template("queue_help.html", folder=queue_root())


@app.post("/queue/import")
def queue_import():
    try:
        got, problems = import_replies(get_conn())
    except OSError as e:
        flash(f"Could not reach the work folder: {e}")
        return redirect(url_for("queue_page"))
    flash(f"Imported {got} reply file(s)." if got else "No new replies in the replies folder.")
    for p in problems:
        flash(p)
    return redirect(url_for("queue_page"))


@app.post("/queue/<int:item_id>/delete")
def queue_delete(item_id):
    """Takes one item out of the queue: its request and any reply go; the batch finishes if nothing else waits."""
    conn = get_conn()
    it = conn.execute("SELECT * FROM queue_items WHERE id=?", (item_id,)).fetchone()
    if it:
        try:
            queue_dir().sub("requests").remove(it["name"])
            queue_dir().sub("replies").remove(it["name"])
            conn.execute("UPDATE queue_items SET status='removed' WHERE id=?", (item_id,))
            conn.commit()
            if it["batch"]:
                _finish_batch(conn, it["batch"])
        except OSError as e:
            flash(f"Could not reach the work folder: {e}")
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
    try:
        queue_add(conn, kind, job_id, "", job_d.get("company") or job_d["title"], msg)
        flash(f"{QUEUE_KINDS[kind]} request added to the work folder. Tell your AI: read AI_INSTRUCTIONS.md and process the pending batch.")
    except OSError as e:
        flash(f"Could not add the request to the work folder: {e}")
    return redirect(request.referrer or url_for("job", job_id=job_id))


@app.post("/gaps/queue")
def queue_gaps():
    conn = get_conn()
    jobs, focus, _profile = gap_scope(conn)
    rows, _phases = gapmod.build_plan(jobs, LEX)
    extras = sorted(usersync.confirmed_skills(conn))
    msg = gapmod.build_message(rows, jobs, LEX, focus, extras, _int_arg("hours", 5, 1, 40), _int_arg("weeks", 12, 1, 52),
                               _int_arg("top", 15, 3, 40))
    try:
        queue_add(conn, "gap", None, focus, focus, msg)
    except OSError as e:
        flash(f"Could not add the request to the work folder: {e}")
    flash("Gap plan request added to the work folder. Tell your AI: read AI_INSTRUCTIONS.md and process the pending batch.")
    return redirect(url_for("queue_page"))


@app.route("/gaps")
def gaps_page():
    conn = get_conn()
    profs = ensure_profiles(conn)
    jobs, focus, profile = gap_scope(conn)
    rows, phases = gapmod.build_plan(jobs, LEX)
    hours, weeks, top = _int_arg("hours", 5, 1, 40), _int_arg("weeks", 12, 1, 52), _int_arg("top", 15, 3, 40)
    extras = sorted(usersync.confirmed_skills(conn))
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
        flash("Paste your AI's reply first.")
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
        where = "your career file" if usersync.fold_extras(conn) else "your list"
        rescore_all(conn)
        flash(f'Added "{term}" to {where} as something you have. Postings re-scored. '
              'Add it to your resume only if it is true.')
        sync_shared(conn)
    return redirect(request.referrer or url_for("gaps_page"))


@app.post("/unhave")
def unhave():
    conn = get_conn()
    term = request.form.get("term", "")
    conn.execute("DELETE FROM extras WHERE term=?", (term,))
    conn.commit()
    data = settings.load_career()
    if data:                                    # only a confirmed skill goes; one from your documents stays
        settings.save_career(career.remove_confirmed(data, term, db.now()))
    rescore_all(conn)
    sync_shared(conn)
    return redirect(url_for("resume_page"))


@app.route("/resume")
def resume_page():
    conn = get_conn()
    text = resume_text()
    found = sorted(matcher.find_terms(text, LEX))
    extras = sorted(usersync.confirmed_skills(conn))
    return render_template("resume.html", found=found, extras=extras, source=scoring_source()[1], name=os.path.basename(settings.resume_path(cfg()) or "") or "none yet", chars=len(text))


KEY_FIELDS = (("adzuna_app_id", "Adzuna app id"), ("adzuna_app_key", "Adzuna app key"),
              ("usajobs_key", "USAJOBS key"), ("usajobs_email", "USAJOBS email"),
              ("google_client_id", "Google OAuth client id"), ("google_client_secret", "Google OAuth client secret"))


def _lines(text):
    return [l.strip() for l in (text or "").replace(",", "\n").splitlines() if l.strip()]


# ---- The career file (career.py, docs/formats.md section 9) --------------------------------------------------
CAREER_SOURCE_EXTS = (".docx", ".md", ".txt")


def _career_extra(name):
    """The request being prepared (career_request.md) and a new file waiting for review (career_pending.json)."""
    return os.path.join(settings.DATA_DIR, name)


def _read_text(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def career_pending():
    raw = _read_text(_career_extra("career_pending.json"))
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _drop(name):
    try:
        os.remove(_career_extra(name))
    except OSError:
        pass


@app.route("/career")
def career_page():
    cur = settings.load_career()
    text, source = scoring_source()
    return render_template("career.html", cur=cur, problems=career.validate(cur) if cur else [],
                           found=sorted(matcher.find_terms(text, LEX)) if source == "career" else [],
                           draft=_read_text(_career_extra("career_request.md")), pending=career_pending() is not None,
                           folder=queue_root(), exts=",".join(CAREER_SOURCE_EXTS))


@app.post("/career/request")
def career_request():
    """Makes the build request from the documents you chose (and what you typed). It is kept until a new file is
    accepted, so it can be copied or sent to the work folder."""
    sources = []
    for f in request.files.getlist("sources"):
        if not f or not f.filename:
            continue
        name, ext = os.path.basename(f.filename), os.path.splitext(f.filename)[1].lower()
        data = f.read()
        if ext not in CAREER_SOURCE_EXTS:
            flash(f"{name} was left out: use Word (.docx), Markdown (.md) or text (.txt) files.")
            continue
        if len(data) > 3 * 1024 * 1024:
            flash(f"{name} was left out: it is over 3 MB.")
            continue
        fd, path = tempfile.mkstemp(suffix=ext)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        try:
            body = resumemod.read_resume(path)
        except Exception:
            body = ""
        finally:
            os.remove(path)
        if body.strip():
            sources.append((name, body))
        else:
            flash(f"{name} was left out: no text could be read from it.")
    typed = request.form.get("typed", "").strip()
    if typed:
        sources.append(("typed in WildThing", typed))
    if not sources:
        flash("Add at least one document, or type something about your work.")
        return redirect(url_for("career_page") + "#build")
    with open(INSTRUCTIONS_SRC, encoding="utf-8") as f:
        section = career.instructions_section(f.read())
    current = settings.load_career() if request.form.get("include_current") else None
    with open(settings._data("career_request.md"), "w", encoding="utf-8") as f:
        f.write(career.build_request(section, sources, current))
    flash(f"Request ready, from {len(sources)} source{'' if len(sources) == 1 else 's'}. Copy it into your AI, or send it to the work folder.")
    return redirect(url_for("career_page") + "#request")


@app.post("/career/send")
def career_send():
    draft = _read_text(_career_extra("career_request.md"))
    if not draft:
        flash("Make the request first.")
        return redirect(url_for("career_page") + "#build")
    name = career.request_name(datetime.now())
    try:
        write_instructions()
        queue_dir().sub("requests").write(name, draft.encode("utf-8"))
    except OSError as e:
        flash(f"Could not write to the work folder: {e}")
        return redirect(url_for("career_page") + "#request")
    flash(f"Sent as requests/{name}. Tell your AI: read AI_INSTRUCTIONS.md in the WildThing folder and build the career "
          f"file requested in requests/{name}. Then come back and press Look in the work folder.")
    return redirect(url_for("career_page") + "#reply")


def _career_take(text, reply):
    """Checks a reply; a good file waits for your review, a bad one is refused with the reasons."""
    data, problems = career.read_reply(text)
    if problems:
        more = f" (and {len(problems) - 5} more)" if len(problems) > 5 else ""
        flash("That career file was not used. " + " ".join(problems[:5]) + more)
        return redirect(url_for("career_page") + "#reply")
    with open(settings._data("career_pending.json"), "w", encoding="utf-8") as f:
        json.dump({"file": data, "reply": reply, "at": db.now()}, f, ensure_ascii=False)
    return redirect(url_for("career_review"))


@app.post("/career/reply")
def career_reply():
    return _career_take(request.form.get("reply", ""), None)


@app.post("/career/fetch")
def career_fetch():
    try:
        replies = queue_dir().sub("replies")
        name = career.newest_reply([f["name"] for f in replies.files()])
        text = replies.text(name) if name else None
    except OSError as e:
        flash(f"Could not read the work folder: {e}")
        return redirect(url_for("career_page") + "#reply")
    if not name:
        flash(f"No career file reply in {queue_root()} yet (it would be replies/career_<time>.reply.md).")
        return redirect(url_for("career_page") + "#reply")
    return _career_take(text or "", name)


@app.route("/career/review")
def career_review():
    p = career_pending()
    if not p:
        return redirect(url_for("career_page"))
    cur = settings.load_career()
    new = career.replace(cur, p["file"], p["at"])
    return render_template("career_review.html", new=new, cur=cur, changes=career.changes(cur, new), reply=p.get("reply"),
                           kept=[s["name"] for s in new["skills"] if s.get("source") == "confirmed"
                                 and s["name"].lower() not in {x["name"].lower() for x in p["file"].get("skills", [])}])


@app.post("/career/accept")
def career_accept():
    p = career_pending()
    if not p:
        return redirect(url_for("career_page"))
    data = career.replace(settings.load_career(), p["file"], db.now())
    problems = career.validate(data)
    if problems:
        flash("That career file was not used. " + " ".join(problems[:5]))
        return redirect(url_for("career_review"))
    settings.save_career(data)
    _drop("career_pending.json")
    _drop("career_request.md")
    usersync.fold_extras(get_conn())                    # "I have this" skills from before the file move into it
    rescore_all(get_conn())
    if p.get("reply"):                                  # the work folder's copies are no longer needed
        try:
            qd = queue_dir()
            qd.sub("replies").remove(p["reply"])
            qd.sub("requests").remove(career.request_for(p["reply"]))
        except OSError as e:
            flash(f"Saved, but the reply could not be removed from the work folder: {e}")
    flash("Career file saved. Every posting was re-scored against it.")
    sync_shared(get_conn())
    return redirect(url_for("career_page"))


@app.post("/career/discard")
def career_discard():
    _drop("career_pending.json")
    flash("The new career file was discarded. Your current one is unchanged.")
    return redirect(url_for("career_page"))


@app.route("/settings")
def settings_page():
    c = cfg()
    keys = load_keys()
    rp = settings.resume_path(c)
    google = {"linked": gdrive.linked(), "client": bool(keys.get("google_client_id") and keys.get("google_client_secret")),
              "relink": gdrive.linked() and not gdrive.granted(gdrive.scope(c))}
    return render_template("settings.html", c=c, resume_name=os.path.basename(rp) if rp else "",
                           has_custom=settings.has_custom_instructions(c),
                           instructions=settings.instructions_text(c), google=google,
                           data_folder=home.ROOT or HERE, default_folder=home.DEFAULT, avoided=db.avoided(get_conn()).values(),
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
        "send_resume_in_requests": f.get("ai_has_resume") != "on",
        "jobspy": {"enabled": f.get("jobspy_enabled") == "on", "location": place},
        "linkedin": {"enabled": f.get("linkedin_enabled") == "on", "location": place},
        "adzuna": {"where": place},
        "usajobs": {"location": place},
    }
    for k in ("queue_folder", "shared_folder"):        # this computer only
        if k in f:
            patch[k] = f.get(k, "").strip()
    if "drive_section" in f:                          # this computer only
        patch.update({"use_drive": f.get("use_drive") == "on", "drive_full": f.get("drive_full") == "full",
                      "drive_permanent_delete": f.get("drive_permanent_delete") == "on"})
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
    sync_shared(get_conn())
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
        sync_shared(get_conn())
    return redirect(url_for("settings_page"))


@app.post("/data/move")
def move_data():
    """Moves this computer's data folder (home.py). The database is closed first so Windows lets it move."""
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()
    try:
        flash(home.move_to(request.form.get("folder", "")))
    except (OSError, ValueError) as e:
        flash(f"Not moved: {e}")
    return redirect(url_for("settings_page"))


@app.get("/export")
def export_file():
    """Everything this copy holds as one JSON file (docs/formats.md), for a backup or the Android app."""
    body = json.dumps(exchange.export_data(get_conn()), indent=1, ensure_ascii=False)
    name = f"wildthing-export-{date.today():%Y-%m-%d}.json"
    return Response(body, mimetype="application/json", headers={"Content-Disposition": f"attachment; filename={name}"})


@app.post("/import")
def import_file():
    up = request.files.get("data")
    if not up or not up.filename:
        flash("Choose an export file first.")
        return redirect(url_for("settings_page"))
    try:
        exchange.import_data(get_conn(), json.loads(up.read().decode("utf-8")))
    except (ValueError, KeyError, TypeError) as e:
        flash(f"Could not import that file: {e}")
        return redirect(url_for("settings_page"))
    rescore_all(get_conn())
    flash("Imported. Everything from the file is here now, and every posting was re-scored.")
    return redirect(url_for("settings_page"))


# ---- Shared details: resume, search settings, instructions and skills in step with the phone (usersync.py) -----
_synced_once = False


def shared_dir():
    """WildThing/user in Google Drive when it is linked and switched on, else the Shared details folder, else None."""
    if drive_on():
        return drive_home().sub("user")
    root = usersync.folder(cfg())
    return workfolder.LocalDir(root) if root else None


def sync_shared(conn, resolve=None, quiet=True):
    """Runs the sync when Drive or a shared folder is set. Re-scores after anything arrives. Returns the result or None."""
    usersync.fold_extras(conn)
    res = usersync.sync(conn, resolve, shared_dir())
    if not res:
        return None
    if res["rescore"]:
        rescore_all(conn)
    if res["conflicts"]:
        flash(f"{len(res['conflicts'])} shared file(s) changed both here and on another device. "
              "Choose which to keep on the Sync page.")
    for e in res["errors"]:
        flash("Sync: " + e)
    if not quiet and not res["conflicts"] and not res["errors"]:
        moved = len(res["pushed"]) + len(res["pulled"])
        flash(f"In step with the shared folder ({len(res['pulled'])} received, {len(res['pushed'])} sent)." if moved
              else "Already in step with the shared folder.")
    return res


def sync_postings(conn, quiet=True):
    """The shared postings database (shared_db.py), only with Google linked. Scores what arrived. Returns a result
    or None."""
    if not drive_on():
        return None
    try:
        res = shared_db.sync(conn, shared_dir(), settings.device_id())
    except (OSError, ValueError, sqlite3.DatabaseError) as e:
        conn.rollback()
        flash(f"Postings sync: {e}")
        return None
    if res["arrived"]:
        have = have_terms(conn)
        for jid in res["arrived"]:
            r = conn.execute("SELECT title, description FROM jobs WHERE id=?", (jid,)).fetchone()
            score_into(conn, jid, r["title"], r["description"], have)
        conn.commit()
        flash(f"{len(res['arrived'])} posting(s) arrived from your other device.")
    elif not quiet:
        flash(f"Postings in step with Google Drive ({res['postings']} in the shared file).")
    return res


@app.before_request
def sync_at_start():
    """Once per run of the app: catch up with what the other device changed."""
    global _synced_once
    if _synced_once or request.endpoint in (None, "static") or "code" in request.args:
        return
    _synced_once = True
    sync_shared(get_conn())
    sync_postings(get_conn())


@app.route("/sync", methods=["GET", "POST"])
def sync_page():
    conn = get_conn()
    res = sync_shared(conn, quiet=request.method == "GET")
    if request.method == "POST":
        sync_postings(conn, quiet=False)
        return redirect(url_for("sync_page"))
    labels = {"resume": "Master resume", "search.json": "Search settings and profiles", "instructions.md": "AI instructions",
              "confirmed_skills.json": "\"I have this\" skills", "career.json": "Career file"}
    where = shared_dir()
    return render_template("sync.html", res=res, labels=labels, folder=where.label if where else None, postings=drive_on())


@app.post("/sync/resolve")
def sync_resolve():
    key, keep = request.form.get("key", ""), request.form.get("keep", "")
    if key in shared_details.FILES and keep in ("here", "folder"):
        sync_shared(get_conn(), {key: keep}, quiet=False)
    return redirect(url_for("sync_page"))


# ---- Google sign-in (gdrive.py): the browser goes to Google and comes back to this app's own address -------------
def _google_redirect():
    return url_for("index", _external=True)


@app.post("/google/link")
def google_link():
    keys = load_keys()
    if not (keys.get("google_client_id") and keys.get("google_client_secret")):
        flash("Save the Google OAuth client id and secret (section 6) first.")
        return redirect(url_for("settings_page"))
    verifier, challenge = gdrive.pkce()
    session["google_state"], session["google_verifier"] = secrets.token_urlsafe(24), verifier
    return redirect(gdrive.auth_url(keys["google_client_id"], _google_redirect(), gdrive.scope(cfg()),
                                    session["google_state"], challenge))


def google_finish():
    """Google sent the browser back to the home page with a one-time code (or an error)."""
    state, verifier = session.pop("google_state", None), session.pop("google_verifier", None)
    if not state or request.args.get("state") != state:
        flash("That Google sign-in did not come from this page. Try Link again.")
    elif request.args.get("error"):
        flash("Google sign-in was cancelled." if request.args["error"] == "access_denied"
              else f"Google sign-in failed: {request.args['error']}")
    else:
        keys = load_keys()
        try:
            gdrive.exchange(request.args.get("code", ""), keys.get("google_client_id", ""),
                            keys.get("google_client_secret", ""), verifier, _google_redirect())
            settings.save_user({"use_drive": True})
            flash("Google is linked. The AI queue and shared details now use the WildThing folder in your Drive.")
            if not gdrive.granted(gdrive.scope(cfg())):
                flash("Google did not grant the Drive access chosen in Settings. Link again and allow it.")
            sync_shared(get_conn())
        except gdrive.DriveError as e:
            flash(f"Google sign-in failed: {e}")
    return redirect(url_for("settings_page"))


@app.post("/google/unlink")
def google_unlink():
    gdrive.revoke()
    flash("Google is unlinked from this computer. Files already in your Drive stay there.")
    return redirect(url_for("settings_page"))


@app.post("/google/check")
def google_check():
    """Check Drive access: every file the app can see in the WildThing folder."""
    if not drive_on():
        flash("Link Google and switch on \"Use Google Drive\" first.")
        return redirect(url_for("settings_page"))
    try:
        home = drive_home()
        write_instructions()
        for label, d in (("WildThing", home), ("requests", home.sub("requests")), ("replies", home.sub("replies")),
                         ("user", home.sub("user"))):
            names = [f["name"] for f in d.files()]
            flash(f"{label}: " + (", ".join(names) if names else "(empty)"))
    except OSError as e:
        flash(f"Could not reach Google Drive: {e}")
    return redirect(url_for("settings_page"))


@app.post("/rescore")
def rescore():
    conn = get_conn()
    rescore_all(conn)
    flash("Re-scored every posting against the current resume.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    _root, _moved = home.start()
    print(f"Your data folder: {_root}" + (f" (moved here from the app folder: {', '.join(_moved)})" if _moved else ""), flush=True)
    app.run(host="127.0.0.1", port=5050, debug=False)
