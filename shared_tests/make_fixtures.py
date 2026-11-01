"""Writes the shared behavior fixtures (shared_tests/*.json) from the desktop code.

The desktop tests (tests.py) and the Android tests (android/core) both run every case in these files and must get the
same answers. Run this only when you mean to change behavior:

    py -3 shared_tests/make_fixtures.py

then read the diff of the .json files (it shows exactly what changed), and make the Android code pass again.
Inputs are written here; the "expect" values come from running the desktop code on them.
"""
import json
import os
import sys
import zipfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import aiqueue  # noqa: E402
import db  # noqa: E402
import gaps  # noqa: E402
import matcher  # noqa: E402
import resume as resumemod  # noqa: E402
import shared_details  # noqa: E402
import sources  # noqa: E402
import tracking  # noqa: E402
import writer  # noqa: E402

LEX = matcher.load_lexicon()
RESUME = open(os.path.join(HERE, "sample_resume.md"), encoding="utf-8").read()
HAVE = sorted(matcher.find_terms(RESUME, LEX))
USER = json.load(open(os.path.join(HERE, "sample_user.json"), encoding="utf-8"))
TITLES = USER["target_titles"]

GOOD = ("Implementation Specialist. We roll out our scheduling software to customers.\n"
        "Requirements: 2+ years of software implementation or IT support experience. Strong troubleshooting, end user "
        "training,\nSQL and Excel skills. Experience with vendor management and stakeholder communication. "
        "Preferred: ITIL, Salesforce.")
SENIOR = "Senior Director of Engineering. Requirements: 10+ years of experience. Kubernetes, AWS, Terraform, Go, Java."
LONG = ("About the role\nYou will join a busy service desk supporting 2,000 users across three offices. "
        "Day to day you will troubleshoot hardware and software issues, manage tickets in ServiceNow, and keep the "
        "knowledge base current.\n\nWhat you'll need\n- 5+ years of help desk or desktop support experience\n"
        "- Active Directory and Microsoft 365 administration\n- Strong customer service and clear written communication\n"
        "- Comfort with Windows 10/11 imaging and Intune\n\nNice to have\n- CompTIA A+ or Network+\n- ITIL Foundation\n"
        "- Some PowerShell scripting\n\nWe offer a hybrid schedule and a learning budget. "
        "You will excel in a fast-moving team and grow with us.")


def write(name, data):
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def scoring():
    find = [{"text": t, "expect": sorted(matcher.find_terms(t, LEX))} for t in (
        RESUME,
        "You will excel in a fast team and love to excel at support.",
        "Advanced Excel and pivot tables",
        "Experience with C#, .NET and SQL Server; Python a plus.",
        "Tier II support, break/fix, and O365 admin.",
        "",
    )]
    cases = [
        ("good fit", "Implementation Specialist", GOOD, HAVE, TITLES),
        ("required weighs double", "x", GOOD, [], []),
        ("senior and years", "Senior Director of Engineering", SENIOR, HAVE, TITLES),
        ("no terms", "Barista", "Make coffee. Smile.", HAVE, TITLES),
        ("long posting with zones", "Service Desk Analyst II", LONG, HAVE, TITLES),
        ("no title match", "Warehouse Associate", LONG, HAVE, TITLES),
        ("empty", "", "", [], TITLES),
        ("blank have, title match", "IT Support Specialist", LONG, [], TITLES),
    ]
    score = []
    for name, title, text, have, titles in cases:
        r = matcher.score_job(title, text, set(have), LEX, titles)
        score.append({"name": name, "title": title, "text": text, "have": have, "target_titles": titles,
                      "expect": {"score": r["score"], "matched": r["matched"], "gaps": [list(g) for g in r["gaps"]],
                                 "flags": r["flags"], "title_match": r["title_match"]}})
    loc = []
    allowed = USER["locations"]
    for location in ("Springfield, IL", "Remote", "Remote - Worldwide", "Anywhere", "", "  ", "Tulsa, OK",
                     "USA, Canada, USA timezones", "Global (remote)", "Riverton"):
        loc.append({"location": location, "allowed": allowed, "expect": matcher.location_ok(location, "", allowed)})
    write("scoring.json", {"lexicon": "skills.json at the repo root", "resume_file": "sample_resume.md",
                           "find_terms": find, "score_job": score, "location_ok": loc})


def dedupe():
    norm = [{"text": t, "expect": db.norm(t)} for t in ("Acme Inc.", "Beta LLC", "  Help-Desk   Technician ", "", None,
                                                        "The Company Co", "Café Ltd")]
    keys = [{"title": t, "company": c, "expect": db.dup_key(t, c)} for t, c in (
        ("Help Desk Technician", "Acme Inc."), ("IT Support", ""), ("Analyst", "Beta LLC"), ("", "Zed"))]
    place = [{"a": a, "b": b, "expect": db.same_place(a, b)} for a, b in (
        ("Springfield, IL", "Springfield"), ("Springfield", "Tulsa"), ("", "Tulsa"), ("Kansas City, MO", "Kansas City, KS"),
        ("New York", "New York City, NY"), (None, None))]
    write("dedupe.json", {"norm": norm, "dup_key": keys, "same_place": place})


def gap_plans():
    plans = []
    for jobs in ([{"gaps": [["itil", 2], ["salesforce", 1]]}, {"gaps": [["itil", 1]]}, {"gaps": [["docker", 1]]}],
                 [{"gaps": [[t, 1 + (i % 2)] for i, t in enumerate(("sql", "python", "itil", "aws", "tableau", "jira",
                                                                      "power bi", "salesforce", "docker", "kubernetes",
                                                                      "terraform", "linux"))]}],
                 []):
        rows, phases = gaps.build_plan(jobs, LEX)
        plans.append({"jobs": jobs, "expect": {"rows": rows, "phases": phases}})
    msg_jobs = [
        {"title": "Systems Analyst", "company": "Beta", "matched": ["sql"],
         "description": "Requirements:\nStrong SQL skills and Power BI dashboards.\nITIL certification required.",
         "gaps": [["power bi", 2], ["itil", 2]]},
        {"title": "Service Desk Analyst", "company": "", "matched": ["help desk", "troubleshooting"],
         "description": LONG, "gaps": [[t, w] for t, w in matcher.score_job("x", LONG, set(HAVE), LEX, [])["gaps"]]},
    ]
    rows, _ = gaps.build_plan(msg_jobs, LEX)
    messages = [{"jobs": msg_jobs, "focus": f, "extras": e, "hours": h, "weeks": w, "top": t,
                 "expect": gaps.build_message(rows, msg_jobs, LEX, f, e, h, w, t)}
                for f, e, h, w, t in (("all postings", [], 5, 12, 15), ('the "PM" profile', ["jira", "aws"], 6, 8, 3))]
    replies = ["<priorities>Start with ITIL</priorities><plan>Week 1: read the guide</plan><skip>Tableau</skip>",
               "No tags at all.", "<plan>\n\n</plan><questions> Do you have AWS? </questions>"]
    parse = [{"text": r, "expect": [list(x) for x in gaps.parse_plan(r)]} for r in replies]
    write("gaps.json", {"build_plan": plans, "build_message": messages, "parse_plan": parse,
                        "actions": gaps.ACTIONS, "sections": [list(x) for x in gaps.PLAN_SECTIONS]})


FAKE_REPLY = """Built it.
<resume>
**Jane Doe**
Springfield, IL

### SUMMARY
Led a software rollout in 6 weeks against a 6-month plan.
</resume>

<cover_letter>
Dear Hiring Team, ...
</cover_letter>

<review_notes>
Hard gaps: none
</review_notes>"""


def replies():
    blocks = [{"text": t, "expect": writer.parse_blocks(t)} for t in (FAKE_REPLY, "<resume>x</resume>", "plain text reply", "")]
    rules = USER["resume_check_phrases"]
    long_resume = " ".join(["word"] * 650)
    checks = [{"text": t, "rules": r, "expect": writer.check_resume(t, r)} for t, r in (
        ("I managed a team of 5 and have 2.5 years. [FILL IN]", rules),
        ("Led a rollout. Trained users.", []),
        (None, []),
        ("I managed a team of 5.", []),
        (long_resume, []),
        ("**Bold** # heading [x] and [y]", rules),
    )]
    job = {"title": "Analyst", "company": "Acme", "location": "KC", "description": "Do SQL", "gaps": [["itil", 2], ["aws", 1]]}
    bare = {"title": "Coordinator", "description": "Plan things"}
    msgs = [{"job": j, "want_cover": c, "expect": writer.build_user_message(j, c)} for j, c in ((job, True), (job, False), (bare, False))]
    prep_msgs = [{"job": j, "expect": writer.build_prep_message(j)} for j in (job, bare)]
    prep_reply = ("<likely_questions>Tell me about a rollout.</likely_questions>\n<questions_to_ask>What does success "
                  "look like?</questions_to_ask><gap_prep> </gap_prep><research>Read the annual report.</research>")
    prep = [{"text": t, "expect": [list(x) for x in writer.parse_prep(t)]} for t in (prep_reply, "nothing tagged")]
    ctx = [{"message": "Build a resume for this listing.", "instructions": "  # Rules\nBe honest.\n", "resume": r,
            "expect": writer.with_context("Build a resume for this listing.", "  # Rules\nBe honest.\n", r)}
           for r in (RESUME, "", "   ")]
    slugs = [{"text": t, "expect": writer.slug(t)} for t in ("Acme Co", "", None, "A very long company name that goes past forty characters", "Ünïcode & Co!")]
    write("replies.json", {"parse_blocks": blocks, "check_resume": checks, "build_user_message": msgs,
                           "build_prep_message": prep_msgs, "parse_prep": prep, "with_context": ctx, "slug": slugs,
                           "prep_sections": [list(x) for x in writer.PREP_SECTIONS]})


def parsers():
    cases = {
        "strip_html": [{"html": h, "expect": sources.strip_html(h)} for h in (
            "<p>Help &amp; fix</p>", "&lt;p&gt;Use Excel&lt;/p&gt;", "Line one<br>Line two<br/>Line three",
            "<ul><li>SQL</li><li>Excel</li></ul>\n\n\n<p>Done</p>", "a\t\t b &nbsp; c &rsquo; &#39; &#x2014;", "", None)],
        "remoteok": [{"data": d, "expect": sources.parse_remoteok(d)} for d in (
            [{"legal": "notice"}, {"id": 5, "position": "IT Support", "company": "Acme", "location": "", "url": "https://r/5",
                                   "description": "<p>Help &amp; fix</p>", "date": "d"}],)],
        "remotive": [{"data": d, "expect": sources.parse_remotive(d)} for d in (
            {"jobs": [{"id": 1, "title": "Analyst", "company_name": "C", "url": "u", "candidate_required_location": "USA",
                       "description": "<b>SQL</b>", "publication_date": "2026-10-01"},
                      {"id": 2, "title": "Coordinator", "company_name": "D", "url": "v", "candidate_required_location": "",
                       "description": ""}]},)],
        "greenhouse": [{"data": d, "board": "acme", "expect": sources.parse_greenhouse(d, "acme")} for d in (
            {"jobs": [{"id": 9, "title": "Coordinator", "location": {"name": "KC"}, "absolute_url": "u",
                       "content": "&lt;p&gt;Use Excel&lt;/p&gt;", "updated_at": "2026-10-02"},
                      {"id": 10, "title": "Analyst", "location": None, "absolute_url": "w", "content": ""}]},)],
        "lever": [{"data": d, "company": "co", "expect": sources.parse_lever(d, "co")} for d in (
            [{"id": "a", "text": "Support", "categories": {"location": "Remote"}, "hostedUrl": "u", "descriptionPlain": "Desc",
              "createdAt": 1730000000000, "lists": [{"text": "Requirements", "content": "<li>SQL</li>"}]}],)],
        "adzuna": [{"data": d, "expect": sources.parse_adzuna(d)} for d in (
            {"results": [{"id": 3, "title": "T", "company": {"display_name": "X"}, "location": {"display_name": "KC"},
                          "redirect_url": "u", "description": "d", "created": "2026-10-03"}]},)],
        "usajobs": [{"data": d, "expect": sources.parse_usajobs(d)} for d in (
            {"SearchResult": {"SearchResultItems": [{"MatchedObjectId": "7", "MatchedObjectDescriptor": {
                "PositionTitle": "IT Specialist", "OrganizationName": "Agency", "PositionLocationDisplay": "KC",
                "PositionURI": "u", "UserArea": {"Details": {"JobSummary": "Support users"}}, "QualificationSummary": "SQL",
                "PublicationStartDate": "2026-10-04"}}]}},)],
        "title_wanted": [{"title": t, "targets": TITLES, "expect": sources.title_wanted(t, TITLES)}
                         for t in ("IT Support Specialist", "Barista", "", "Senior Business Analyst")],
    }
    write("sources.json", cases)


def tracking_rules():
    today = date(2026, 10, 31)
    follow = [{"status": s, "applied_on": a, "today": today.isoformat(), "expect": tracking.needs_follow_up(s, a, today)}
              for s, a in (("applied", "2026-10-17"), ("applied", "2026-10-18"), ("applied", None), ("applied", "bad"),
                           ("interview", "2026-01-01"), ("applied", "2026-11-05"))]
    days = [{"applied_on": a, "today": today.isoformat(), "expect": tracking.days_since(a, today)}
            for a in ("2026-10-17", "2026-10-31", "", None, "31/10/2026")]
    weekly = [{"args": list(a), "expect": tracking.weekly_summary(*a)} for a in ((7, 0, 0, 0, 0, 0), (14, 5, 2, 1, 3, 4))]
    rate = [{"applied": a, "interviews": i, "expect": tracking.interview_rate(a, i)} for a, i in ((0, 0), (8, 3), (3, 1), (8, 1))]
    write("tracking.json", {"statuses": [list(x) for x in db.STATUSES], "applied_stages": db.APPLIED_STAGES,
                            "follow_up_days": tracking.FOLLOW_UP_DAYS, "needs_follow_up": follow, "days_since": days,
                            "weekly_summary": weekly, "interview_rate": rate})


def docx():
    """A tiny Word file, to check both versions read .docx the same way."""
    path = os.path.join(HERE, "sample_resume.docx")
    paras = ["Jane Doe", "Springfield, IL", "", "Skills: SQL &amp; Excel", "Tier 1-3 support"]
    body = "".join(f'<w:p><w:pPr/><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in paras)
    body += '<w:p><w:r><w:t>Split </w:t></w:r><w:r><w:t>run</w:t></w:r></w:p>'
    fixed = lambda name: zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))   # same bytes every run
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(fixed("[Content_Types].xml"), '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr(fixed("word/document.xml"), '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
                   'wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>')
    write("resume.json", {"docx_file": "sample_resume.docx", "expect": resumemod.read_resume(path)})


def queue():
    from datetime import datetime
    batch = aiqueue.batch_id(datetime(2026, 10, 31, 18, 10), "k3f9")
    items = [{"n": 1, "kind": "resume", "label": "Acme Co"}, {"n": 2, "kind": "prep", "label": "Beta"},
             {"n": 3, "kind": "resume_cover", "label": "Gamma Health"}, {"n": 4, "kind": "gap", "label": "all postings"}]
    names = [aiqueue.item_name(batch, it["n"], it["kind"], it["label"]) for it in items]
    todo = {"batch": batch, "origin": "android-7x2q", "created": "2026-10-31T18:10:00+00:00", "items": items,
            "carries_context": True}
    todo["expect"] = aiqueue.render_todo(batch, todo["origin"], todo["created"], items, True)
    todo_bare = dict(todo, carries_context=False, expect=aiqueue.render_todo(batch, todo["origin"], todo["created"], items, False))
    request = {"batch": batch, "n": 2, "kind": "prep", "label": "Beta", "body": "Prepare me for an interview.",
               "expect": aiqueue.render_request(batch, 2, "prep", "Beta", "Prepare me for an interview.")}
    reply_texts = [
        aiqueue.render_reply_todo(batch, [(1, "done", names[0], ""), (2, "skipped", "", "The posting text was empty."),
                                          (3, "failed", "", "Could not read the request file.")]),
        "Replies:\n- 01: done " + names[0] + "\n- 2 skipped - not a real posting\n* 03) FAILED: timed out\n",
        "| item | status | reply | reason |\n|---|---|---|---|\n| 01 | Done | `" + names[0] + "` | |\n| 01 | skipped | | changed my mind |\n",
        "", None,
    ]
    parse = [{"text": t, "expect": {str(k): v for k, v in aiqueue.parse_reply_todo(t).items()}} for t in reply_texts]
    names_cases = [{"name": n, "expect": list(aiqueue.parse_item_name(n) or []) or None} for n in names + [
        "TODO_" + batch + ".md", "003_prep_acme.md", batch + "_01_cooking_x.md", ""]]
    todo_names = [{"name": n, "todo": aiqueue.batch_of_todo(n), "reply_todo": aiqueue.batch_of_reply_todo(n)}
                  for n in (aiqueue.todo_name(batch), aiqueue.reply_todo_name(batch), names[0], "TODO.md")]
    recs = [{"n": it["n"], "name": nm} for it, nm in zip(items, names)]
    plans = []
    for label, present, replies, report in (
        ("nothing back yet", names, [], None),
        ("all done with report", names, [{"name": nm, "modified": "2026-10-31T19:00:00Z"} for nm in names],
         aiqueue.render_reply_todo(batch, [(i + 1, "done", nm, "") for i, nm in enumerate(names)])),
        ("report missing, match by name", names, [{"name": names[1], "modified": "2026-10-31T19:00:00Z"}], None),
        ("skipped, failed and missing", names, [{"name": names[0], "modified": "2026-10-31T19:00:00Z"}],
         aiqueue.render_reply_todo(batch, [(1, "done", names[0], ""), (2, "skipped", "", "The posting text was empty."),
                                           (3, "done", names[2], ""), (4, "failed", "", "Could not read the request file.")])),
        ("duplicates: newest wins", names, [{"name": names[0], "modified": "2026-10-31T19:00:00Z"},
                                             {"name": names[0], "modified": "2026-10-31T19:05:00Z"},
                                             {"name": "unrelated.md", "modified": "2026-10-31T19:06:00Z"}], None),
        ("some already imported", names[2:], [{"name": names[2], "modified": "x"}, {"name": names[3], "modified": "y"}], None),
        ("reply under another name", names, [{"name": "resume-acme.md", "modified": "2026-10-31T19:00:00Z"}],
         "| 01 | done | resume-acme.md | |"),
    ):
        plans.append({"name": label, "items": recs, "requests_present": present, "replies": replies, "reply_todo": report,
                      "expect": aiqueue.plan_import(recs, set(present), replies, report)})
    write("queue.json", {"kinds": aiqueue.KINDS, "reply_tags": aiqueue.REPLY_TAGS, "batch_id": batch, "item_names": names,
                         "render_todo": [todo, todo_bare], "render_request": [request], "parse_item_name": names_cases,
                         "todo_names": todo_names, "parse_reply_todo": parse, "plan_import": plans})


def shared():
    cfg = {"target_titles": ["help desk", "analyst"], "search_keywords": ["help desk"], "locations": ["springfield", "remote"],
           "your_name": "not shared"}
    profiles = [{"id": 3, "name": "PM", "keywords": "project coordinator", "titles": "", "location": "Springfield, IL"},
                {"id": 1, "name": "General", "keywords": "help desk", "titles": "help desk\nanalyst", "location": ""}]
    search = shared_details.search_doc(cfg, profiles).decode("utf-8")
    skills = shared_details.skills_doc(["sql", "itil", "itil"]).decode("utf-8")
    a, b, c = "a" * 64, "b" * 64, "c" * 64
    cases = []
    for label, local, remote, base in (
        ("neither side has it", None, None, None), ("only here", a, None, None), ("only in the folder", None, b, None),
        ("first sync, same", a, a, None), ("first sync, different", a, b, None),
        ("nothing changed", a, b, {"local": a, "remote": b}), ("changed here", c, b, {"local": a, "remote": b}),
        ("changed in the folder", a, c, {"local": a, "remote": b}), ("changed on both", c, c + "x", {"local": a, "remote": b}),
        ("both changed to the same", c, c, {"local": a, "remote": b}),
        ("deleted from the folder", a, None, {"local": a, "remote": b}),
    ):
        rm = None if remote is None else shared_details.meta("search.json", 3, "2026-10-31T18:00:00+00:00", "desktop-ab12", remote)
        cases.append({"name": label, "local": local, "remote": rm, "base": base, "expect": shared_details.decide(local, rm, base)})
    versions = [{"remote": r, "base": bs, "expect": shared_details.next_version(r, bs)}
                for r, bs in ((None, None), ({"version": 4}, None), ({"version": 2}, {"version": 5}))]
    write("shared_details.json", {"files": list(shared_details.FILES), "meta_names": {k: shared_details.meta_name(k) for k in shared_details.FILES},
                                  "search_doc": {"settings": cfg, "profiles": profiles, "expect": search,
                                                 "sha256": shared_details.sha256(search.encode("utf-8"))},
                                  "skills_doc": {"terms": ["sql", "itil", "itil"], "expect": skills},
                                  "decide": cases, "next_version": versions})


def shared_postings():
    """The merge rule for the shared postings database (shared_db.py, docs/formats.md section 7)."""
    import shared_db

    def posting(source="remoteok", ext_id="1", title="Help Desk Analyst", company="Acme", location="Springfield, IL",
                url="https://example.com/1", status="new", status_at="", applied_on="", notes="", links=(), **kw):
        p = {"source": source, "ext_id": ext_id, "title": title, "company": company, "location": location, "url": url,
             "description": "Help desk, SQL.", "posted": "", "added_at": "2026-10-01T10:00:00+00:00", "status": status,
             "status_at": status_at, "applied_on": applied_on, "notes": notes, "pasted": 0,
             "links": [{"source": s_, "url": u} for s_, u in links]}
        p.update(kw)
        return p

    def snap(postings=None, events=None, outputs=None, gap_plans=None, tombstones=None, avoided=None, tags=None):
        s_ = shared_db.empty()
        s_["postings"] = postings or {}
        s_["events"] = events or {}
        s_["outputs"] = {f"{o['posting']}|{o['kind']}": o for o in (outputs or [])}
        s_["gap_plans"] = gap_plans or {}
        s_["tombstones"] = tombstones or {}
        s_["avoided"] = avoided or {}
        s_["tags"] = {f"{g['posting']}|{g['tag']}": g for g in (tags or [])}
        return s_

    def avoid(company, at, active=1, reason=""):
        return {"company": company, "reason": reason, "active": active, "changed_at": at}

    def tag(posting, name, at, active=1):
        return {"posting": posting, "tag": name, "active": active, "changed_at": at}

    def event(posting, when="2026-11-05T10:00", changed="2026-10-30T10:00:00+00:00", place=""):
        return {"posting": posting, "kind": "Interview", "starts_at": when, "minutes": 60, "place": place, "notes": "",
                "time_zone": "", "changed_at": changed}

    def output(posting, created, content):
        return {"posting": posting, "kind": "resume", "content": content, "warnings_json": "[]", "created_at": created}

    t1, t2, t3 = "2026-10-20T09:00:00+00:00", "2026-10-25T09:00:00+00:00", "2026-10-28T09:00:00+00:00"
    cases = [
        ("only here, only there", snap({"a": posting()}), snap({"b": posting(source="greenhouse", ext_id="9", url="https://example.com/9", title="Analyst", company="Beta")}), {}),
        ("same posting, matched by source and id", snap({"a": posting(status="saved", status_at=t1)}), snap({"b": posting(url="")}), {}),
        ("same posting, matched by link", snap({"a": posting(source="pasted", ext_id="p1")}),
         snap({"b": posting(source="greenhouse", ext_id="g7", links=[("remotive", "https://example.com/1")])}), {}),
        ("same posting, matched by title and company in the same place", snap({"a": posting(source="pasted", ext_id="p1", url="")}),
         snap({"b": posting(source="lever", ext_id="l2", url="", location="Springfield")}), {}),
        ("same title and company in another place is another posting", snap({"a": posting(source="pasted", ext_id="p1", url="")}),
         snap({"b": posting(source="lever", ext_id="l2", url="", location="Denver, CO")}), {}),
        ("newer status wins, with its applied date", snap({"a": posting(status="applied", status_at=t2, applied_on="2026-10-25")}),
         snap({"a": posting(status="interview", status_at=t3, applied_on="2026-10-24")}), {}),
        ("older status there loses", snap({"a": posting(status="offer", status_at=t3)}), snap({"a": posting(status="saved", status_at=t1)}), {}),
        ("notes changed only there", snap({"a": posting(notes="old")}), snap({"a": posting(notes="called them")}), {"a": "old"}),
        ("notes changed only here", snap({"a": posting(notes="sent thank-you")}), snap({"a": posting(notes="old")}), {"a": "old"}),
        ("notes changed on both are kept together", snap({"a": posting(notes="phone: Tuesday")}), snap({"a": posting(notes="recruiter is Sam")}), {"a": "old"}),
        ("first sync, notes on one side only", snap({"a": posting(notes="")}), snap({"a": posting(notes="from the phone")}), {}),
        ("notes cleared here on purpose", snap({"a": posting(notes="")}), snap({"a": posting(notes="old")}), {"a": "old"}),
        ("deleted here: gone there, with its interviews and AI work",
         snap(tombstones={"a": {"kind": "posting", "at": t3}}),
         snap({"a": posting()}, {"e1": event("a")}, [output("a", t1, "R")]), {}),
        ("interviews: the newer change wins; one deleted", snap({"a": posting()}, {"e1": event("a", place="Zoom", changed=t3), "e2": event("a")}, tombstones={"e3": {"kind": "event", "at": t3}}),
         snap({"a": posting()}, {"e1": event("a", place="Office", changed=t2), "e3": event("a")}), {}),
        ("saved AI work: the newer one wins", snap({"a": posting()}, outputs=[output("a", t1, "older resume")]),
         snap({"a": posting()}, outputs=[output("a", t2, "newer resume")]), {}),
        ("links from both are kept", snap({"a": posting(links=[("remoteok", "https://example.com/1")])}),
         snap({"a": posting(links=[("adzuna", "https://example.com/a")])}), {}),
        ("gap plans from both, less the deleted", snap(gap_plans={"g1": {"scope": "all postings", "content": "A", "created_at": t1}},
                                                    tombstones={"g2": {"kind": "gap_plan", "at": t3}}),
         snap(gap_plans={"g2": {"scope": "PM", "content": "B", "created_at": t2}, "g3": {"scope": "PM", "content": "C", "created_at": t3}}), {}),
        ("avoided companies from both are kept", snap(avoided={"acme": avoid("Acme Inc", t1, reason="lowball offer")}),
         snap(avoided={"beta": avoid("Beta", t2)}), {}),
        ("stopped avoiding here, later: stays stopped", snap(avoided={"acme": avoid("Acme", t3, active=0)}),
         snap(avoided={"acme": avoid("Acme", t2, reason="rude")}), {}),
        ("avoided again there, later: avoided", snap(avoided={"acme": avoid("Acme", t2, active=0)}),
         snap(avoided={"acme": avoid("Acme", t3, reason="still rude")}), {}),
        ("avoided and stopped at the same moment: avoided", snap(avoided={"acme": avoid("Acme", t2, active=0)}),
         snap(avoided={"acme": avoid("Acme", t2)}), {}),
        ("tags from both are kept", snap({"a": posting()}, tags=[tag("a", "scam", t1)]),
         snap({"a": posting()}, tags=[tag("a", "c:Slow to reply", t2)]), {}),
        ("tag removed there, later: removed", snap({"a": posting()}, tags=[tag("a", "ghost", t1)]),
         snap({"a": posting()}, tags=[tag("a", "ghost", t2, active=0)]), {}),
        ("tag added again here, later: on", snap({"a": posting()}, tags=[tag("a", "ghost", t3)]),
         snap({"a": posting()}, tags=[tag("a", "ghost", t2, active=0)]), {}),
        ("tags follow a posting matched to the other device's", snap({"a": posting(url="")}, tags=[tag("a", "ai_interview", t1)]),
         snap({"b": posting()}, tags=[tag("b", "no_pay", t2)]), {}),
        ("tags on a deleted posting go with it", snap(tombstones={"a": {"kind": "posting", "at": t3}}),
         snap({"a": posting()}, tags=[tag("a", "scam", t1)]), {}),
    ]
    out = []
    for name, here, there, base in cases:
        res = shared_db.merge(here, there, base)
        out.append({"name": name, "here": here, "there": there, "base": base, "expect": res})
    write("shared_db.json", {"file": shared_db.FILE, "format": shared_db.FORMAT, "version": shared_db.VERSION,
                             "combine": shared_db.COMBINE, "merge": out})


def career_file():
    """The career file (career.py, docs/formats.md section 9): what counts as a usable file, reading one from an AI's
    reply, the app's own edits, and the privacy and wording check."""
    import copy
    import career
    with open(os.path.join(HERE, "career_sample.json"), encoding="utf-8") as f:
        sample = json.load(f)

    def bad(name, change):
        d = copy.deepcopy(sample)
        change(d)
        return {"name": name, "data": d, "problems": career.validate(d)}

    def set_(path, value):
        def go(d):
            *head, last = path
            for k in head:
                d = d[k]
            d[last] = value
        return go

    invalid = [
        {"name": "not an object", "data": [1, 2], "problems": career.validate([1, 2])},
        {"name": "another format", "data": {"format": "other"}, "problems": career.validate({"format": "other"})},
        bad("from a newer version", set_(["version"], 99)),
        bad("no name", set_(["person", "name"], " ")),
        bad("a role without a title, with a bad date", lambda d: d["roles"][0].update(title="", start="April 2022")),
        bad("a role that ends before it starts", lambda d: d["roles"][1].update(end="2018-01")),
        bad("the same id twice", lambda d: d["projects"][0].update(id="r1")),
        bad("a skill listed twice", lambda d: d["skills"].append({"name": "SQL", "source": "documents", "evidence": ["r1"]})),
        bad("a skill pointing nowhere", lambda d: d["skills"][0].update(evidence=["r9"])),
        bad("a skill from the documents with no evidence or notes", lambda d: d["skills"][3].update(notes="")),
        bad("an unknown skill source", lambda d: d["skills"][4].update(source="posting")),
        bad("an unknown certification status", lambda d: d["certifications"][0].update(status="pending")),
        bad("privacy and wording of the wrong shape", lambda d: d.update(privacy={"never_name": "Northside"}, wording={"avoid": ["managed"]})),
        bad("an achievement without text", lambda d: d["roles"][0]["achievements"].append({"skills": []})),
    ]
    good = json.dumps(sample, indent=1)
    replies = [
        {"name": "plain", "text": f"<career_file>\n{good}\n</career_file>"},
        {"name": "in a json fence, with words around it", "text": f"Here it is.\n<career_file>\n```json\n{good}\n```\n</career_file>\nDone."},
        {"name": "no tag", "text": good},
        {"name": "not JSON", "text": "<career_file>{name: Jane}</career_file>"},
        {"name": "JSON that is not a usable file", "text": '<career_file>{"format": "wildthing-career", "version": 1, "person": {"name": ""}}</career_file>'},
    ]
    for r in replies:
        data, problems = career.read_reply(r["text"])
        r["ok"], r["problems"] = data is not None, [p.split(":")[0] for p in problems]   # the JSON error's detail differs by language
    now = "2026-11-02T09:00:00+00:00"
    edits = {
        "add_new": career.add_confirmed(sample, "  Salesforce ", now),
        "add_known": career.add_confirmed(sample, "SQL", now),
        "remove_confirmed": career.remove_confirmed(sample, "ITIL", now),
        "remove_documents": career.remove_confirmed(sample, "sql", now),
        "replace": career.replace(sample, dict(career.empty("Jane Doe"), skills=[{"name": "sql", "source": "documents", "evidence": [], "notes": "x"}]), now),
        "empty": career.empty("Jane Doe"),
    }
    md = "# Title\n\nIntro.\n\n## Building the career file\n\nStep one.\n\nStep two.\n\n## Next part\n\nNot this.\n"
    sources = [("a.md", "A"), ('b "x".txt', "  B\n\n")]
    import datetime as _dt
    req = career.request_name(_dt.datetime(2026, 11, 2, 9, 5))
    listed = ["career_20261101-1000.reply.md", "TODO_x.md", "career_20261102-0905.reply.md", "career_20261102-0905.md"]
    docs = ["I implemented scheduling for a regional clinic network.", "At NORTHSIDE CLINICS I managed a team.",
            "Back from medical leave in 2023."]
    write("career.json", {"format": career.FORMAT, "version": career.VERSION, "file": career.FILE, "tag": career.TAG,
                          "sample_file": "career_sample.json", "sample_problems": career.validate(sample),
                          "sample_skills": career.skill_names(sample), "sample_text": career.text(sample),
                          "invalid": invalid, "replies": replies, "now": now, "edits": edits,
                          "check": [{"doc": d, "warnings": career.check_document(d, sample)} for d in docs],
                          "section": {"md": md, "expect": career.instructions_section(md)},
                          "request": {"section": "SECTION", "sources": [list(x) for x in sources],
                                      "expect": career.build_request("SECTION", sources)},
                          "names": {"request": req, "reply": career.reply_name(req), "request_for": career.request_for(career.reply_name(req)),
                                    "listed": listed, "newest": career.newest_reply(listed)},
                          "changes": [{"old": None, "new": sample, "expect": career.changes(None, sample)},
                                      {"old": sample, "new": edits["replace"], "expect": career.changes(sample, edits["replace"])}]})


if __name__ == "__main__":
    queue()
    shared()
    shared_postings()
    career_file()
    scoring()
    dedupe()
    gap_plans()
    replies()
    parsers()
    tracking_rules()
    docx()
    print("Fixtures written to", HERE)
