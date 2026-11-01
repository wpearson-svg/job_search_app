import json, os, shutil, tempfile, unittest

import db, matcher, gaps, sources, writer, settings, resume as resumemod
import app as appmod

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = matcher.load_lexicon()

# Tests run against a private data folder holding a sample user (the resume and settings the app was built around),
# never against the real data/ folder.
settings.DATA_DIR = tempfile.mkdtemp()
writer.BASE = tempfile.mkdtemp()                       # generated files never land in the app folder
import home; home.ROOT = writer.BASE                       # nor the default work folder
SHARED = os.path.join(HERE, "shared_tests")   # the same made-up user and cases the Android tests use
with open(os.path.join(SHARED, "sample_resume.md"), encoding="utf-8") as _f:
    SAMPLE_RESUME = _f.read()
with open(os.path.join(settings.DATA_DIR, "master_resume.md"), "w", encoding="utf-8") as _f:
    _f.write(SAMPLE_RESUME)


def make_docx(text):
    """A minimal valid .docx holding the given text, for upload tests."""
    import zipfile
    path = os.path.join(tempfile.mkdtemp(), "r.docx")
    paras = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % l for l in text.splitlines() if l.strip())
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s</w:body></w:document>' % paras)
    return path


with open(os.path.join(SHARED, "sample_user.json"), encoding="utf-8") as _f:
    SAMPLE_USER = json.load(_f)
with open(os.path.join(settings.DATA_DIR, "user_settings.json"), "w") as _f:
    json.dump(SAMPLE_USER, _f)
appmod.app.config["KEYS_PATH"] = os.path.join(settings.DATA_DIR, "keys.local.json")
CFG = settings.load()
RESUME = resumemod.read_resume(settings.resume_path(CFG))

GOOD = """Implementation Specialist. We roll out our scheduling software to customers.
Requirements: 2+ years of software implementation or IT support experience. Strong troubleshooting, end user training,
SQL and Excel skills. Experience with vendor management and stakeholder communication. Preferred: ITIL, Salesforce."""
SENIOR = """Senior Director of Engineering. Requirements: 10+ years of experience. Kubernetes, AWS, Terraform, Go, Java."""


def offline(test):
    """Runs a test with every web request failing, as if there were no network."""
    def run(self):
        import requests
        def fail(*a, **k):
            raise requests.ConnectionError("no network in tests")
        orig, sources.requests.get = sources.requests.get, fail
        try:
            return test(self)
        finally:
            sources.requests.get = orig
    return run


def shared(name):
    with open(os.path.join(SHARED, name), encoding="utf-8") as f:
        return json.load(f)


class SharedFixtureTests(unittest.TestCase):
    """The cases in shared_tests/, which the Android tests run too. Both versions must give these exact answers."""

    def test_scoring(self):
        d = shared("scoring.json")
        for c in d["find_terms"]:
            self.assertEqual(sorted(matcher.find_terms(c["text"], LEX)), c["expect"], c["text"][:40])
        for c in d["score_job"]:
            r = matcher.score_job(c["title"], c["text"], set(c["have"]), LEX, c["target_titles"])
            got = {"score": r["score"], "matched": r["matched"], "gaps": [list(g) for g in r["gaps"]],
                   "flags": r["flags"], "title_match": r["title_match"]}
            self.assertEqual(got, c["expect"], c["name"])
        for c in d["location_ok"]:
            self.assertEqual(matcher.location_ok(c["location"], "", c["allowed"]), c["expect"], c["location"])

    def test_dedupe(self):
        d = shared("dedupe.json")
        for c in d["norm"]:
            self.assertEqual(db.norm(c["text"]), c["expect"])
        for c in d["dup_key"]:
            self.assertEqual(db.dup_key(c["title"], c["company"]), c["expect"])
        for c in d["same_place"]:
            self.assertEqual(db.same_place(c["a"], c["b"]), c["expect"], (c["a"], c["b"]))

    def test_gaps(self):
        d = shared("gaps.json")
        for c in d["build_plan"]:
            rows, phases = gaps.build_plan(c["jobs"], LEX)
            self.assertEqual({"rows": rows, "phases": phases}, c["expect"])
        for c in d["build_message"]:
            rows, _ = gaps.build_plan(c["jobs"], LEX)
            self.assertEqual(gaps.build_message(rows, c["jobs"], LEX, c["focus"], c["extras"], c["hours"], c["weeks"],
                                                c["top"]), c["expect"])
        for c in d["parse_plan"]:
            self.assertEqual([list(x) for x in gaps.parse_plan(c["text"])], c["expect"])
        self.assertEqual(gaps.ACTIONS, d["actions"])

    def test_replies_and_requests(self):
        d = shared("replies.json")
        for c in d["parse_blocks"]:
            self.assertEqual(writer.parse_blocks(c["text"]), c["expect"])
        for c in d["check_resume"]:
            self.assertEqual(writer.check_resume(c["text"], c["rules"]), c["expect"])
        for c in d["build_user_message"]:
            self.assertEqual(writer.build_user_message(c["job"], c["want_cover"]), c["expect"])
        for c in d["build_prep_message"]:
            self.assertEqual(writer.build_prep_message(c["job"]), c["expect"])
        for c in d["parse_prep"]:
            self.assertEqual([list(x) for x in writer.parse_prep(c["text"])], c["expect"])
        for c in d["with_context"]:
            self.assertEqual(writer.with_context(c["message"], c["instructions"], c["resume"]), c["expect"])
        for c in d["slug"]:
            self.assertEqual(writer.slug(c["text"]), c["expect"])

    def test_source_parsers(self):
        d = shared("sources.json")
        for c in d["strip_html"]:
            self.assertEqual(sources.strip_html(c["html"]), c["expect"])
        for name in ("remoteok", "remotive", "adzuna", "usajobs"):
            for c in d[name]:
                self.assertEqual(getattr(sources, "parse_" + name)(c["data"]), c["expect"], name)
        for c in d["greenhouse"]:
            self.assertEqual(sources.parse_greenhouse(c["data"], c["board"]), c["expect"])
        for c in d["lever"]:
            self.assertEqual(sources.parse_lever(c["data"], c["company"]), c["expect"])
        for c in d["title_wanted"]:
            self.assertEqual(sources.title_wanted(c["title"], c["targets"]), c["expect"])

    def test_tracking(self):
        import tracking
        from datetime import date
        d = shared("tracking.json")
        self.assertEqual([list(x) for x in db.STATUSES], d["statuses"])
        self.assertEqual(db.APPLIED_STAGES, d["applied_stages"])
        for c in d["needs_follow_up"]:
            self.assertEqual(tracking.needs_follow_up(c["status"], c["applied_on"], date.fromisoformat(c["today"])), c["expect"])
        for c in d["days_since"]:
            self.assertEqual(tracking.days_since(c["applied_on"], date.fromisoformat(c["today"])), c["expect"])
        for c in d["weekly_summary"]:
            self.assertEqual(tracking.weekly_summary(*c["args"]), c["expect"])
        for c in d["interview_rate"]:
            self.assertEqual(tracking.interview_rate(c["applied"], c["interviews"]), c["expect"])

    def test_queue_format(self):
        import aiqueue
        d = shared("queue.json")
        self.assertEqual(aiqueue.KINDS, d["kinds"])
        self.assertEqual(aiqueue.REPLY_TAGS, d["reply_tags"])
        for c in d["render_todo"]:
            self.assertEqual(aiqueue.render_todo(c["batch"], c["origin"], c["created"], c["items"], c["carries_context"]), c["expect"])
        for c in d["render_request"]:
            self.assertEqual(aiqueue.render_request(c["batch"], c["n"], c["kind"], c["label"], c["body"]), c["expect"])
        for c in d["parse_item_name"]:
            got = aiqueue.parse_item_name(c["name"])
            self.assertEqual(list(got) if got else None, c["expect"], c["name"])
        for c in d["todo_names"]:
            self.assertEqual(aiqueue.batch_of_todo(c["name"]), c["todo"])
            self.assertEqual(aiqueue.batch_of_reply_todo(c["name"]), c["reply_todo"])
        for c in d["parse_reply_todo"]:
            self.assertEqual({str(k): v for k, v in aiqueue.parse_reply_todo(c["text"]).items()}, c["expect"])
        for c in d["plan_import"]:
            self.assertEqual(aiqueue.plan_import(c["items"], set(c["requests_present"]), c["replies"], c["reply_todo"]),
                             c["expect"], c["name"])

    def test_shared_details(self):
        import shared_details as sd
        d = shared("shared_details.json")
        self.assertEqual(list(sd.FILES), d["files"])
        self.assertEqual({k: sd.meta_name(k) for k in sd.FILES}, d["meta_names"])
        c = d["search_doc"]
        self.assertEqual(sd.search_doc(c["settings"], c["profiles"]).decode("utf-8"), c["expect"])
        self.assertEqual(sd.skills_doc(d["skills_doc"]["terms"]).decode("utf-8"), d["skills_doc"]["expect"])
        for c in d["decide"]:
            self.assertEqual(sd.decide(c["local"], c["remote"], c["base"]), c["expect"], c["name"])
        for c in d["next_version"]:
            self.assertEqual(sd.next_version(c["remote"], c["base"]), c["expect"])

    def test_shared_postings_merge(self):
        import shared_db
        d = shared("shared_db.json")
        self.assertEqual((d["file"], d["format"], d["version"], d["combine"]),
                         (shared_db.FILE, shared_db.FORMAT, shared_db.VERSION, shared_db.COMBINE))
        for c in d["merge"]:
            self.assertEqual(shared_db.merge(c["here"], c["there"], c["base"]), c["expect"], c["name"])

    def test_docx(self):
        d = shared("resume.json")
        self.assertEqual(resumemod.read_resume(os.path.join(SHARED, d["docx_file"])), d["expect"])


class CareerTests(unittest.TestCase):
    """The career file (career.py, docs/formats.md section 9), against the shared cases in shared_tests/career.json."""

    def setUp(self):
        import career
        self.career = career
        self.d = shared("career.json")
        self.sample = shared(self.d["sample_file"])

    def test_constants_and_sample(self):
        c, d = self.career, self.d
        self.assertEqual((d["format"], d["version"], d["file"], d["tag"]), (c.FORMAT, c.VERSION, c.FILE, c.TAG))
        self.assertEqual(c.validate(self.sample), [])
        self.assertEqual(c.skill_names(self.sample), d["sample_skills"])
        self.assertEqual(c.text(self.sample), d["sample_text"])
        self.assertEqual(c.validate(c.empty("Jane Doe")), [])

    def test_invalid_files_say_why(self):
        for case in self.d["invalid"]:
            self.assertTrue(case["problems"], case["name"])
            self.assertEqual(self.career.validate(case["data"]), case["problems"], case["name"])

    def test_reading_replies(self):
        for r in self.d["replies"]:
            data, problems = self.career.read_reply(r["text"])
            self.assertEqual((data is not None, [p.split(":")[0] for p in problems]), (r["ok"], r["problems"]), r["name"])
        data, _ = self.career.read_reply(self.d["replies"][1]["text"])
        self.assertEqual(data, self.sample)

    def test_app_edits_and_rebuilds(self):
        c, e, now = self.career, self.d["edits"], self.d["now"]
        self.assertEqual(c.add_confirmed(self.sample, "  Salesforce ", now), e["add_new"])
        self.assertEqual(c.add_confirmed(self.sample, "SQL", now), e["add_known"])
        self.assertEqual(c.add_confirmed(self.sample, "SQL", now), self.sample)       # already there: unchanged
        self.assertEqual(c.remove_confirmed(self.sample, "ITIL", now), e["remove_confirmed"])
        self.assertEqual(c.remove_confirmed(self.sample, "sql", now), self.sample)    # from the documents: stays
        rebuilt = c.replace(self.sample, dict(c.empty("Jane Doe"), skills=[{"name": "sql", "source": "documents", "evidence": [], "notes": "x"}]), now)
        self.assertEqual(rebuilt, e["replace"])
        self.assertEqual(c.skill_names(rebuilt), ["sql", "itil"])                     # the confirmed one carried over
        self.assertEqual(e["add_new"]["skills"][-1], {"name": "Salesforce", "source": "confirmed", "evidence": [], "notes": ""})

    def test_privacy_and_wording_check(self):
        for case in self.d["check"]:
            self.assertEqual(self.career.check_document(case["doc"], self.sample), case["warnings"])
        self.assertEqual(self.d["check"][0]["warnings"], [])
        self.assertEqual(len(self.d["check"][1]["warnings"]), 2)


class ResumeTests(unittest.TestCase):
    def test_reads_docx(self):
        self.assertIn("Acme Services", RESUME)
        p = make_docx("Line one\nLine two about SQL")
        self.assertIn("Line two about SQL", resumemod.read_resume(p))

    def test_resume_terms(self):
        t = matcher.find_terms(RESUME, LEX)
        for want in ("sql", "excel", "software implementation", "user training", "tier 1-3 support", "agile / scrum",
                     "vendor management", "scheduling software", "docker", "ai / llm", "c#"):
            self.assertIn(want, t, want)
        self.assertNotIn("salesforce", t)
        self.assertNotIn("itil", t)


class MatchTests(unittest.TestCase):
    have = matcher.find_terms(RESUME, LEX)

    def test_good_fit_scores_high_with_gaps(self):
        r = matcher.score_job("Implementation Specialist", GOOD, self.have, LEX, CFG["target_titles"])
        self.assertGreaterEqual(r["score"], 70)
        gap_terms = [g[0] for g in r["gaps"]]
        self.assertIn("itil", gap_terms)
        self.assertIn("salesforce", gap_terms)
        self.assertTrue(r["title_match"])

    def test_required_weighs_double(self):
        r = matcher.score_job("x", GOOD, set(), LEX, [])
        w = dict(r["gaps"])
        self.assertEqual(w["sql"], 2)      # in the requirements part
        self.assertEqual(w["itil"], 1)     # in the preferred part

    def test_senior_and_years_penalised(self):
        r = matcher.score_job("Senior Director of Engineering", SENIOR, self.have, LEX, CFG["target_titles"])
        self.assertLessEqual(r["score"], 20)
        self.assertTrue(any("Senior" in f for f in r["flags"]))
        self.assertTrue(any("10+" in f for f in r["flags"]))

    def test_excel_verb_is_not_the_tool(self):
        t = matcher.find_terms("You will excel in a fast team and love to excel at support.", LEX)
        self.assertNotIn("excel", t)
        self.assertIn("excel", matcher.find_terms("Advanced Excel and pivot tables", LEX))

    def test_no_terms_flag(self):
        r = matcher.score_job("Barista", "Make coffee. Smile.", self.have, LEX, CFG["target_titles"])
        self.assertEqual(r["score"], 0)
        self.assertTrue(r["flags"])

    def test_gap_plan_ranking(self):
        jobs = [{"gaps": [["itil", 2], ["salesforce", 1]]}, {"gaps": [["itil", 1]]}, {"gaps": [["docker", 1]]}]
        rows, phases = gaps.build_plan(jobs, LEX)
        self.assertEqual(rows[0]["term"], "itil")
        self.assertEqual(rows[0]["jobs"], 2)
        self.assertEqual(rows[0]["kind"], "cert")
        self.assertEqual(phases[0]["label"], "Weeks 1-2")


class SourceParseTests(unittest.TestCase):
    def test_remoteok(self):
        data = [{"legal": "notice"}, {"id": 5, "position": "IT Support", "company": "Acme", "location": "",
                                       "url": "https://r/5", "description": "<p>Help &amp; fix</p>", "date": "d"}]
        j = sources.parse_remoteok(data)
        self.assertEqual(len(j), 1)
        self.assertEqual(j[0]["description"], "Help & fix")
        self.assertEqual(j[0]["location"], "Remote")

    def test_remotive(self):
        j = sources.parse_remotive({"jobs": [{"id": 1, "title": "Analyst", "company_name": "C", "url": "u",
                                              "candidate_required_location": "USA", "description": "<b>SQL</b>"}]})
        self.assertEqual(j[0]["company"], "C")

    def test_greenhouse_escaped_html(self):
        j = sources.parse_greenhouse({"jobs": [{"id": 9, "title": "Coordinator", "location": {"name": "KC"},
                                                "absolute_url": "u", "content": "&lt;p&gt;Use Excel&lt;/p&gt;"}]}, "acme")
        self.assertEqual(j[0]["description"], "Use Excel")

    def test_lever(self):
        j = sources.parse_lever([{"id": "a", "text": "Support", "categories": {"location": "Remote"}, "hostedUrl": "u",
                                  "descriptionPlain": "Desc", "lists": [{"text": "Requirements", "content": "<li>SQL</li>"}]}], "co")
        self.assertIn("SQL", j[0]["description"])

    def test_adzuna_and_usajobs(self):
        a = sources.parse_adzuna({"results": [{"id": 3, "title": "T", "company": {"display_name": "X"},
                                               "location": {"display_name": "KC"}, "redirect_url": "u", "description": "d"}]})
        self.assertEqual(a[0]["company"], "X")
        u = sources.parse_usajobs({"SearchResult": {"SearchResultItems": [{"MatchedObjectId": "7", "MatchedObjectDescriptor": {
            "PositionTitle": "IT Specialist", "OrganizationName": "Agency", "PositionLocationDisplay": "KC",
            "PositionURI": "u", "UserArea": {"Details": {"JobSummary": "Support users"}}, "QualificationSummary": "SQL"}}]}})
        self.assertIn("SQL", u[0]["description"])

    @offline
    def test_missing_keys_reported_not_fatal(self):
        jobs, report = sources.fetch_all({**CFG, "greenhouse_boards": [], "lever_companies": []}, {})
        names = {n: err for n, _, err in report}
        self.assertIn("no Adzuna key", names["Adzuna"])
        self.assertIn("no USAJOBS key", names["USAJOBS"])


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()

    def test_paste_flow_and_gap_plan_and_have(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        r = self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme", "location": "Springfield, IL",
                                      "text": GOOD}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"itil", r.data)
        r = self.c.get("/gaps")
        self.assertIn(b"Weeks 1-2", r.data)
        before = db.connect().execute("SELECT score FROM jobs").fetchone()[0]
        self.c.post("/have", data={"term": "itil"})
        self.c.post("/have", data={"term": "salesforce"})
        after = db.connect().execute("SELECT score FROM jobs").fetchone()[0]
        self.assertGreater(after, before)
        r = self.c.get("/resume")
        self.assertIn(b"itil", r.data)
        self.c.post("/unhave", data={"term": "itil"})
        self.assertEqual(db.connect().execute("SELECT COUNT(*) FROM extras").fetchone()[0], 1)

    def test_empty_paste_rejected(self):
        r = self.c.post("/add", data={"text": "  "})
        self.assertIn(b"Paste the posting text first", r.data)

    def test_status_and_filters(self):
        self.c.post("/add", data={"title": "IT Support", "text": GOOD})
        jid = db.connect().execute("SELECT id FROM jobs").fetchone()[0]
        self.c.post(f"/job/{jid}/status", data={"status": "dismissed"})
        self.assertNotIn(b"IT Support", self.c.get("/").data)
        self.assertIn(b"IT Support", self.c.get("/?status=all").data)
        self.assertEqual(self.c.post(f"/job/{jid}/status", data={"status": "bogus"}).status_code, 400)

    def test_bad_term_ignored(self):
        self.c.post("/have", data={"term": "not a real term"})
        self.assertEqual(db.connect().execute("SELECT COUNT(*) FROM extras").fetchone()[0], 0)

    def test_html_in_posting_is_escaped(self):
        self.c.post("/add", data={"title": "<script>alert(1)</script>", "text": GOOD})
        jid = db.connect().execute("SELECT id FROM jobs").fetchone()[0]
        self.assertNotIn(b"<script>alert(1)</script>", self.c.get(f"/job/{jid}").data)

    @offline
    def test_fetch_with_no_network_does_not_crash(self):
        r = self.c.post("/fetch", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"fetched 0 postings", r.data)


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


class WriterTests(unittest.TestCase):
    def test_parse_blocks(self):
        p = writer.parse_blocks(FAKE_REPLY)
        self.assertTrue(p["resume"].startswith("**Jane"))
        self.assertIn("Hard gaps", p["review_notes"])
        self.assertIn("Dear Hiring Team", p["cover_letter"])
        self.assertIsNone(writer.parse_blocks("<resume>x</resume>")["cover_letter"])

    def test_checks(self):
        w = writer.check_resume("I managed a team of 5 and have 2.5 years. [FILL IN]", CFG["resume_check_phrases"])
        self.assertEqual(len(w), 3)
        self.assertEqual(writer.check_resume("Led a rollout. Trained users."), [])
        self.assertTrue(writer.check_resume(None))
        self.assertEqual(len(writer.check_resume("I managed a team of 5.")), 0)   # no personal rules by default

    def test_user_message_has_listing_and_no_extras(self):
        m = writer.build_user_message({"title": "Analyst", "company": "Acme", "location": "KC", "description": "Do SQL"}, True)
        self.assertIn("resume and a cover letter", m)
        self.assertIn("<job_listing>", m)
        self.assertIn("Company: Acme", m)

    def test_default_instructions_are_the_whole_file(self):
        text = settings.instructions_text(CFG)
        self.assertIn("Hard rules", text)
        self.assertEqual(text, open(os.path.join(HERE, "default_instructions.md"), encoding="utf-8").read())

    def test_no_api_path_left(self):
        # The app never calls an AI itself; any assistant gets the request through copy, share or the folder.
        for name in ("generate", "call_model", "system_with_resume"):
            self.assertFalse(hasattr(writer, name), name)
        self.assertNotIn("anthropic_api_key", dict(appmod.KEY_FIELDS))


class PostingPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()
        self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme", "text": GOOD})
        self.jid = db.connect().execute("SELECT id FROM jobs").fetchone()[0]

    def test_build_route_is_gone(self):
        self.assertEqual(self.c.post(f"/job/{self.jid}/build", data={}).status_code, 404)


class PackageTests(PostingPageTests):
    def test_page_offers_copy_and_import_and_names_no_ai(self):
        r = self.c.get(f"/job/{self.jid}")
        self.assertIn(b"Copy for your AI: resume", r.data)
        self.assertIn(b"Build a resume and a cover letter for this listing.", r.data)
        self.assertIn(b"Build a resume for this listing.", r.data)
        self.assertIn(b"Company: Acme", r.data)
        self.assertNotIn(b"Build with the API instead", r.data)
        self.assertNotIn(b"Claude", r.data)

    def test_import_tagged_reply(self):
        r = self.c.post(f"/job/{self.jid}/import", data={"reply": FAKE_REPLY}, follow_redirects=True)
        self.assertIn(b"Saved.", r.data)
        self.assertIn(b"Led a software rollout", r.data)
        self.assertIn(b"Dear Hiring Team", r.data)

    def test_import_plain_reply_and_warnings(self):
        r = self.c.post(f"/job/{self.jid}/import", data={"reply": "I managed a team. [FILL IN]"}, follow_redirects=True)
        self.assertIn(b"whole reply was kept as the resume", r.data)
        self.assertIn(b"Bracket marker", r.data)

    def test_import_empty_rejected(self):
        r = self.c.post(f"/job/{self.jid}/import", data={"reply": " "}, follow_redirects=True)
        self.assertIn(b"Paste your AI", r.data)


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()
        self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme", "text": GOOD})
        self.jid = db.connect().execute("SELECT id FROM jobs").fetchone()[0]

    def row(self):
        return dict(db.connect().execute("SELECT * FROM jobs WHERE id=?", (self.jid,)).fetchone())

    def test_status_dropdown_values_and_applied_date(self):
        from datetime import date
        self.assertIn(b"Phone screen", self.c.get(f"/job/{self.jid}").data)
        self.c.post(f"/job/{self.jid}/status", data={"status": "applied"})
        r = self.row()
        self.assertEqual(r["status"], "applied")
        self.assertEqual(r["applied_on"], date.today().isoformat())
        self.c.post(f"/job/{self.jid}/status", data={"status": "interview"})
        self.assertEqual(self.row()["applied_on"], date.today().isoformat())   # date is kept
        self.assertEqual(self.row()["status"], "interview")
        self.assertEqual(self.c.post(f"/job/{self.jid}/status", data={"status": "bogus"}).status_code, 400)

    def test_applications_page_counts_and_follow_up(self):
        self.assertNotIn(b"Implementation Specialist", self.c.get("/applications").data)
        self.c.post(f"/job/{self.jid}/status", data={"status": "applied"})
        self.c.post(f"/job/{self.jid}/application", data={"applied_on": "2026-01-01", "notes": "Spoke to Dana"})
        page = self.c.get("/applications").data
        self.assertIn(b"Implementation Specialist", page)
        self.assertIn(b"Spoke to Dana", page)
        self.assertIn(b"Maybe follow up", page)            # applied long ago, still just "applied"
        self.c.post(f"/job/{self.jid}/status", data={"status": "interview"})
        self.assertNotIn(b"Maybe follow up", self.c.get("/applications").data)

    def test_bad_date_rejected(self):
        self.c.post(f"/job/{self.jid}/status", data={"status": "applied"})
        before = self.row()["applied_on"]
        r = self.c.post(f"/job/{self.jid}/application", data={"applied_on": "13/45/2026", "notes": "x"}, follow_redirects=True)
        self.assertIn(b"date picker", r.data)
        self.assertEqual(self.row()["applied_on"], before)

    def test_log_application_elsewhere(self):
        r = self.c.post("/applications/log", data={"title": "IT Coordinator", "company": "Beta", "applied_on": "2026-10-01",
                                                   "status": "phone_screen"}, follow_redirects=True)
        self.assertIn(b"Logged: IT Coordinator", r.data)
        self.assertIn(b"Beta", r.data)
        self.assertIn(b"Phone screen", r.data)
        r = self.c.post("/applications/log", data={"title": " "}, follow_redirects=True)
        self.assertIn(b"Give the job a title", r.data)

    def test_old_database_is_upgraded(self):
        import sqlite3
        path = os.path.join(self.tmp, "old.db")
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, ext_id TEXT NOT NULL, title TEXT, "
                  "company TEXT, location TEXT, url TEXT, description TEXT, posted TEXT, pasted INTEGER NOT NULL DEFAULT 0, "
                  "status TEXT NOT NULL DEFAULT 'new', score INTEGER NOT NULL DEFAULT 0, matched_json TEXT NOT NULL DEFAULT '[]', "
                  "gaps_json TEXT NOT NULL DEFAULT '[]', flags_json TEXT NOT NULL DEFAULT '[]', title_match INTEGER NOT NULL DEFAULT 0, "
                  "added_at TEXT NOT NULL, UNIQUE(source, ext_id))")
        c.execute("INSERT INTO jobs(source, ext_id, title, added_at) VALUES ('x','1','Old job','t')")
        c.commit(); c.close()
        conn = db.connect(path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
        self.assertTrue({"applied_on", "notes", "status_updated"} <= cols)
        self.assertEqual(conn.execute("SELECT title FROM jobs").fetchone()[0], "Old job")
        conn.close()

    def test_apply_button_marks_applied_once(self):
        from datetime import date
        self.c.post("/job/%d/application" % self.jid, data={"applied_on": "", "notes": ""})
        r = self.c.post(f"/job/{self.jid}/apply")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.row()["status"], "applied")
        self.assertEqual(self.row()["applied_on"], date.today().isoformat())
        self.c.post(f"/job/{self.jid}/status", data={"status": "interview"})
        self.c.post(f"/job/{self.jid}/apply")                       # pressing again never moves it back
        self.assertEqual(self.row()["status"], "interview")
        self.assertEqual(self.c.post("/job/999/apply").status_code, 404)

    def test_apply_button_shows_only_before_applying_and_uses_safe_links_only(self):
        conn = db.connect()
        conn.execute("UPDATE jobs SET url='https://example.com/jobs/1' WHERE id=?", (self.jid,)); conn.commit()
        page = self.c.get(f"/job/{self.jid}").data
        self.assertIn(b'data-url="https://example.com/jobs/1"', page)
        self.assertIn(b"open the posting and mark applied", page)
        self.assertIn(b">Apply<", self.c.get("/").data)
        conn.execute("UPDATE jobs SET url='javascript:alert(1)' WHERE id=?", (self.jid,)); conn.commit()
        page = self.c.get(f"/job/{self.jid}").data
        self.assertNotIn(b"javascript:", page)
        self.assertIn(b"Mark applied", page)
        self.c.post(f"/job/{self.jid}/apply")
        self.assertNotIn(b'onclick="applyTo', self.c.get(f"/job/{self.jid}").data)
        conn.close()

    def test_sort_by_applied_date(self):
        self.c.post("/add", data={"title": "Second Job", "text": GOOD})
        self.c.post(f"/job/{self.jid}/status", data={"status": "applied"})
        body = self.c.get("/?sort=applied").data
        self.assertLess(body.index(b"Implementation Specialist"), body.index(b"Second Job"))

    def test_purge_removes_only_untouched_fetched(self):
        conn = db.connect()
        def ins(ext, loc, status="new", pasted=0):
            conn.execute("INSERT INTO jobs(source, ext_id, title, location, description, pasted, status, added_at) "
                         "VALUES ('remoteok', ?, 'T', ?, 'd', ?, ?, 'x')", (ext, loc, pasted, status))
        ins("a", "Anywhere in the world"); ins("b", "Springfield"); ins("c", "Berlin", "saved")
        ins("d", "Berlin", "applied"); ins("e", "Berlin", "dismissed"); ins("f", "Berlin", "new", 1)
        conn.commit()
        self.assertEqual(self.c.post("/purge", data={"scope": "bogus"}).status_code, 400)
        self.c.post("/purge", data={"scope": "outside"})
        left = {r[0] for r in conn.execute("SELECT ext_id FROM jobs WHERE source='remoteok'")}
        self.assertEqual(left, {"b", "c", "d", "e", "f"})
        self.c.post("/purge", data={"scope": "untouched"})
        left = {r[0] for r in conn.execute("SELECT ext_id FROM jobs WHERE source='remoteok'")}
        self.assertEqual(left, {"c", "d", "e", "f"})
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs WHERE id=?", (self.jid,)).fetchone()[0], 1)
        conn.close()

    def test_fetch_skips_postings_outside_locations(self):
        import sources
        mk = lambda e, loc: {"source": "remoteok", "ext_id": e, "title": "IT Support", "company": "A", "location": loc,
                             "url": "", "description": "d", "posted": ""}
        orig = sources.fetch_all
        sources.fetch_all = lambda cfg, keys: ([mk("w1", "Worldwide"), mk("k1", "Springfield, IL"), mk("u1", "USA")], [])
        try:
            self.c.post("/fetch")
        finally:
            sources.fetch_all = orig
        conn = db.connect()
        got = {r[0] for r in conn.execute("SELECT ext_id FROM jobs WHERE source='remoteok'")}
        conn.close()
        self.assertEqual(got, {"k1", "u1"})

    def test_worldwide_is_never_in_area(self):
        allowed = ["springfield", "remote", "usa"]
        for loc in ("Worldwide", "Anywhere", "Remote - Worldwide", "Remote (Anywhere)"):
            self.assertFalse(matcher.location_ok(loc, "", allowed), loc)
        for loc in ("Springfield, IL", "Remote", "USA", ""):
            self.assertTrue(matcher.location_ok(loc, "", allowed), loc)

    def test_linkedin_parse_and_description(self):
        items = [{"position": "IT Support Specialist", "company": "Acme", "location": "Springfield, IL", "date": "2026-10-29",
                  "agoTime": "1 day ago", "jobUrl": "https://www.linkedin.com/jobs/view/it-support-specialist-at-acme-3987654321?trk=x"},
                 {"position": "", "jobUrl": "https://www.linkedin.com/jobs/view/1"}]
        j = sources.parse_linkedin(items)
        self.assertEqual(len(j), 1)
        self.assertEqual((j[0]["source"], j[0]["ext_id"], j[0]["company"]), ("linkedin", "3987654321", "Acme"))
        page = '<div class="x"><div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5">' \
               '<p>Reset passwords</p><ul><li>Active Directory</li></ul></div></div>'
        text = sources.parse_linkedin_description(page)
        self.assertIn("Reset passwords", text); self.assertIn("Active Directory", text)
        self.assertEqual(sources.parse_linkedin_description("<html></html>"), "")

    def test_linkedin_reports_missing_node(self):
        from unittest import mock
        with mock.patch("sources.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                sources._run_linkedin_query({"keyword": "x"})
        self.assertIn("Node.js", str(cm.exception))
        self.assertIn("off", self._off("linkedin"))

    def test_linkedin_bridge_output_survives_package_log_lines(self):
        from unittest import mock
        def run(out, err="", code=0):
            return mock.Mock(stdout=out, stderr=err, returncode=code)
        noisy = 'https://www.linkedin.com/jobs-guest/x\nReturning cached results\n@@JSON@@[{"position":"A"}]@@END@@'
        with mock.patch("sources.shutil.which", return_value="node"), mock.patch("sources.os.path.isdir", return_value=True):
            with mock.patch("sources.subprocess.run", return_value=run(noisy)):
                self.assertEqual(sources._run_linkedin_query({}), [{"position": "A"}])
            blocked = run("@@JSON@@[]@@END@@", "Error fetching batch (attempt 3): Request failed with status code 403\n")
            with mock.patch("sources.subprocess.run", return_value=blocked):
                with self.assertRaises(RuntimeError) as cm:
                    sources._run_linkedin_query({})
            self.assertIn("403", str(cm.exception))
            with mock.patch("sources.subprocess.run", return_value=run("garbage", "", 0)):
                with self.assertRaises(RuntimeError):
                    sources._run_linkedin_query({})

    def _off(self, name):
        try:
            if name == "linkedin":
                sources.fetch_linkedin({"linkedin": {"enabled": False}, "search_keywords": [], "target_titles": []})
        except RuntimeError as e:
            return str(e)
        return ""

    def test_prep_message_and_import_keeps_resume_outputs(self):
        job = {"title": "Help Desk", "company": "Acme", "location": "KC", "description": "Do SQL", "gaps": [("itil", 2), ("sql", 1)]}
        m = writer.build_prep_message(job)
        self.assertIn("itil, sql", m); self.assertIn("<questions_to_ask>", m); self.assertIn("<job_listing>", m)
        reply = "<likely_questions>Q1 answer</likely_questions><questions_to_ask>What does success look like?</questions_to_ask>"
        self.assertEqual([l for l, _ in writer.parse_prep(reply)], ["Questions they may ask you", "Questions to ask them"])
        self.c.post(f"/job/{self.jid}/import", data={"reply": "<resume>R body</resume>"})
        r = self.c.post(f"/job/{self.jid}/prep", data={"reply": reply})
        self.assertEqual(r.status_code, 302)
        page = self.c.get(f"/job/{self.jid}").data
        self.assertIn(b"What does success look like?", page); self.assertIn(b"R body", page)
        self.c.post(f"/job/{self.jid}/import", data={"reply": "<resume>R2 body</resume>"})   # rebuilding keeps the prep
        self.assertIn(b"What does success look like?", self.c.get(f"/job/{self.jid}").data)

    # ---- calendar ----
    def test_event_google_link_and_ics(self):
        self.c.post(f"/job/{self.jid}/event", data={"kind": "Interview", "starts_at": "2030-05-06T14:30", "minutes": "45",
                                                   "place": "Zoom, room 2", "notes": "Bring; questions"})
        page = self.c.get(f"/job/{self.jid}").data.decode()
        self.assertIn("calendar.google.com/calendar/render?action=TEMPLATE", page)
        self.assertIn("dates=20300506T143000/20300506T151500", page)
        ics = self.c.get("/event/1.ics")
        self.assertEqual(ics.mimetype, "text/calendar")
        body = ics.data.decode()
        self.assertIn("DTSTART:20300506T143000", body); self.assertIn("DTEND:20300506T151500", body)
        self.assertIn("LOCATION:Zoom\\, room 2", body); self.assertIn("DESCRIPTION:Bring\\; questions", body)
        self.assertIn("END:VCALENDAR", self.c.get("/calendar.ics").data.decode())
        self.assertEqual(self.c.post(f"/job/{self.jid}/event", data={"starts_at": "nonsense"}).status_code, 302)
        self.assertEqual(self.c.get("/event/99.ics").status_code, 404)
        self.assertIn(b"Interview", self.c.get("/applications").data)
        self.c.post("/event/1/delete")
        self.assertEqual(self.c.get("/event/1.ics").status_code, 404)

    # ---- weekly ----
    def test_weekly_counts(self):
        self.c.post(f"/job/{self.jid}/apply")
        body = self.c.get("/weekly").data.decode()
        self.assertIn("1 application(s) sent", body)
        self.assertEqual(self.c.get("/weekly?days=abc").status_code, 200)

    # ---- duplicates ----
    def test_fetch_merges_same_job_from_another_source(self):
        import sources
        mk = lambda src, e, url: {"source": src, "ext_id": e, "title": "Help Desk Technician", "company": "Acme Inc.",
                                  "location": "Springfield, IL", "url": url, "description": "d", "posted": ""}
        orig = sources.fetch_all
        sources.fetch_all = lambda cfg, keys: ([mk("linkedin", "1", "https://linkedin.com/jobs/1"),
                                                mk("indeed", "a", "https://indeed.com/viewjob?jk=a")], [])
        try:
            self.c.post("/fetch"); self.c.post("/fetch")
        finally:
            sources.fetch_all = orig
        conn = db.connect()
        rows = conn.execute("SELECT id FROM jobs WHERE title='Help Desk Technician'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_links WHERE job_id=?", (rows[0][0],)).fetchone()[0], 1)
        page = self.c.get(f"/job/{rows[0][0]}").data
        self.assertIn(b"indeed.com/viewjob", page)
        conn.close()

    def test_merge_duplicates_button_keeps_touched_ones(self):
        conn = db.connect()
        def ins(ext, status="new", loc="Springfield", score=10):
            conn.execute("INSERT INTO jobs(source, ext_id, title, company, location, url, description, status, score, added_at) "
                         "VALUES ('x', ?, 'Analyst', 'Beta LLC', ?, ?, 'd', ?, ?, 'x')", (ext, loc, "https://x/" + ext, status, score))
        ins("a", score=50); ins("b", score=20); ins("c", status="applied"); ins("d", loc="Tulsa")
        conn.commit()
        self.c.post("/dedupe")
        left = {r[0] for r in conn.execute("SELECT ext_id FROM jobs WHERE company='Beta LLC'")}
        self.assertEqual(left, {"c", "d"})                       # applied one kept, other Springfield copies merged into it
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_links").fetchone()[0], 2)
        self.assertEqual(db.dup_key("IT Support", ""), "")
        conn.close()

    # ---- profiles ----
    def test_profiles_drive_fetch_and_tag_results(self):
        import sources
        seen = []
        def fake(cfg, keys):
            seen.append((cfg["search_keywords"], cfg["target_titles"], cfg["jobspy"]["location"]))
            kw = cfg["search_keywords"][0]
            return ([{"source": "remoteok", "ext_id": kw, "title": kw.title(), "company": "Co " + kw, "location": "Springfield",
                      "url": "https://x/" + kw, "description": "d", "posted": ""}], [])
        self.c.get("/profiles")                       # first visit creates the General profile
        self.c.post("/profiles/save", data={"name": "PM", "keywords": "project coordinator\nprogram manager",
                                             "titles": "", "location": "Overland Park, KS"})
        self.assertIn(b"PM", self.c.get("/profiles").data)
        orig = sources.fetch_all
        sources.fetch_all = fake
        try:
            conn = db.connect()
            gen = conn.execute("SELECT id FROM profiles WHERE name='General'").fetchone()
            pm = conn.execute("SELECT id FROM profiles WHERE name='PM'").fetchone()
            self.c.post("/fetch", data={"profile": str(pm["id"])})
            self.assertEqual(seen[-1][0], ["project coordinator", "program manager"])
            self.assertEqual(seen[-1][1], ["project coordinator", "program manager"])   # blank titles fall back to keywords
            self.assertEqual(seen[-1][2], "Overland Park, KS")
            n_after_pm = len(seen)
            self.c.post("/fetch", data={"profile": "all"})
            self.assertEqual(len(seen), n_after_pm + 2)                                  # one run per profile
        finally:
            sources.fetch_all = orig
        tags = [r[0] for r in conn.execute("SELECT p.name FROM job_profiles jp JOIN profiles p ON p.id=jp.profile_id "
                                           "JOIN jobs j ON j.id=jp.job_id WHERE j.ext_id='project coordinator'")]
        self.assertEqual(tags, ["PM"])
        body = self.c.get(f"/?profile={pm['id']}").data
        self.assertIn(b"Project Coordinator", body); self.assertNotIn(b"Implementation Specialist", body)
        self.c.post(f"/profiles/{pm['id']}/delete")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_profiles WHERE profile_id=?", (pm["id"],)).fetchone()[0], 0)
        self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM jobs WHERE ext_id='project coordinator'").fetchone()[0], 1)
        conn.close()

    def test_same_job_found_by_two_profiles_gets_both_tags(self):
        import sources
        job = {"source": "remoteok", "ext_id": "z1", "title": "Coordinator", "company": "Zed", "location": "Springfield",
               "url": "https://x/z1", "description": "d", "posted": ""}
        orig = sources.fetch_all
        sources.fetch_all = lambda cfg, keys: ([dict(job)], [])
        try:
            self.c.get("/profiles")
            self.c.post("/profiles/save", data={"name": "Second", "keywords": "coordinator"})
            self.c.post("/fetch", data={"profile": "all"})
        finally:
            sources.fetch_all = orig
        conn = db.connect()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs WHERE ext_id='z1'").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM job_profiles jp JOIN jobs j ON j.id=jp.job_id WHERE j.ext_id='z1'").fetchone()[0], 2)
        conn.close()

    def test_jobspy_parse_and_fetch(self):
        import sys, types
        nan = float("nan")
        rows = [{"site": "indeed", "id": "in-1", "title": "Help Desk Technician", "company": "Acme", "location": "Springfield, IL, US",
                 "job_url": "https://www.indeed.com/viewjob?jk=1", "description": "Reset passwords", "min_amount": 20.0,
                 "max_amount": nan, "interval": "hourly", "job_type": "fulltime", "date_posted": "2026-10-29"},
                {"site": "linkedin", "id": None, "title": "Cook", "company": "X", "job_url": "https://linkedin.com/jobs/view/9", "description": nan},
                {"site": "indeed", "id": "in-3", "title": "", "job_url": "u"}]
        j = sources.parse_jobspy(rows)
        self.assertEqual(len(j), 2)
        self.assertEqual((j[0]["source"], j[0]["ext_id"], j[0]["company"]), ("indeed", "in-1", "Acme"))
        self.assertIn("Reset passwords", j[0]["description"]); self.assertIn("Salary: 20.0 hourly", j[0]["description"])
        self.assertEqual((j[1]["ext_id"], j[1]["description"], j[1]["location"]), ("https://linkedin.com/jobs/view/9", "", ""))

        calls = []
        class Frame:
            attrs = {}
            def __init__(self, data): self.data = data
            def to_dict(self, how): return self.data
        def fake_scrape(**kw):
            calls.append(kw)
            if "linkedin_fetch_description" not in kw and "fetch_description" in kw and kw["site_name"] == ["linkedin"]:
                raise TypeError("scrape_jobs() got an unexpected keyword argument 'fetch_description'")
            return Frame([r for r in rows if r["site"] in kw["site_name"]])
        mod = types.ModuleType("jobspy"); mod.scrape_jobs = fake_scrape
        cfg = {"jobspy": {"enabled": True, "sites": ["indeed", "linkedin"], "pause_seconds": 0, "max_keywords": 2},
               "search_keywords": ["help desk", "analyst", "ignored"], "target_titles": ["help desk"]}
        sys.modules["jobspy"] = mod
        try:
            got = sources.fetch_jobspy(cfg)
        finally:
            del sys.modules["jobspy"]
        self.assertEqual([g["ext_id"] for g in got], ["in-1"])                 # duplicates across keywords collapse, titles filtered
        self.assertEqual(len(calls), 6)                                          # 2 keywords x 2 sites, plus a retry for each LinkedIn call (old option name)
        self.assertTrue(any("linkedin_fetch_description" in k for k in calls))
        self.assertEqual(sources.fetch_all({"jobspy": {"enabled": False}, "search_keywords": [], "target_titles": [],
                                            "locations": []}, {})[1][-1][2][:12], "JobSpy is of")

    # ---- gap plan with your AI ----
    def test_gap_message_has_evidence_and_plan_roundtrip(self):
        self.c.post("/add", data={"title": "Systems Analyst", "company": "Beta",
                                  "text": "Requirements:\nStrong SQL skills and Power BI dashboards.\nITIL certification required."})
        page = self.c.get("/gaps?hours=6&weeks=8").data.decode()
        self.assertIn("about 6 hours a week for 8 weeks", page)
        self.assertIn("Reply using exactly these tags", page)
        self.assertIn("Systems Analyst (Beta)", page)
        self.assertIn('listed as required in', page)
        self.assertIn("ITIL", page)                                   # a quote from the posting, not just the term
        reply = "<priorities>Start with ITIL</priorities><plan>Week 1: read the guide</plan><skip>Tableau</skip>"
        r = self.c.post("/gaps/plan", data={"reply": reply, "scope": "all postings", "back": ""})
        self.assertEqual(r.status_code, 302)
        page = self.c.get("/gaps").data.decode()
        self.assertIn("Start with ITIL", page); self.assertIn("Week-by-week plan", page)
        self.assertEqual(self.c.post("/gaps/plan", data={"reply": " "}).status_code, 302)
        self.c.post("/gaps/plan/1/delete")
        self.assertNotIn("Start with ITIL", self.c.get("/gaps").data.decode())

    def test_gap_scope_follows_profile_filter(self):
        self.c.get("/profiles")                                          # creates the General profile; nothing is tagged to it
        conn = db.connect()
        pid = conn.execute("SELECT id FROM profiles").fetchone()[0]
        conn.close()
        self.assertIn("Built from 0 postings", self.c.get(f"/gaps?profile={pid}").data.decode())
        self.assertNotIn("Built from 0 postings", self.c.get("/gaps").data.decode())

    # ---- AI work queue (batches) ----
    def _items(self, root):
        return sorted(n for n in os.listdir(os.path.join(root, "requests")) if not n.startswith("TODO_"))

    def _write(self, path, text):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _readf(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_queue_batch_files_import_and_cleanup(self):
        import aiqueue
        root = tempfile.mkdtemp()
        appmod.app.config["QUEUE_ROOT"] = root
        try:
            self.c.post(f"/job/{self.jid}/queue", data={"kind": "resume_cover"})
            self.c.post(f"/job/{self.jid}/queue", data={"kind": "prep"})
            self.assertEqual(self.c.post(f"/job/{self.jid}/queue", data={"kind": "nope"}).status_code, 400)
            names = self._items(root)
            self.assertEqual(len(names), 2)
            batch = aiqueue.parse_item_name(names[0])[0]
            self.assertEqual(aiqueue.parse_item_name(names[1])[0], batch)          # both joined the open batch
            self.assertTrue(os.path.exists(os.path.join(root, "AI_INSTRUCTIONS.md")))
            req = self._readf(os.path.join(root, "requests", names[0]))
            self.assertIn("replies/" + names[0], req); self.assertIn("<job_listing>", req); self.assertIn("cover letter", req)
            todo = self._readf(os.path.join(root, "requests", aiqueue.todo_name(batch)))
            for n in names:
                self.assertIn(n, todo)
            self.assertIn(settings.device_id(), todo)
            self.assertIn("Waiting for a reply", self.c.get("/queue").data.decode())
            rdir = os.path.join(root, "replies")
            self._write(os.path.join(rdir, names[0]), "<resume>Folder resume body</resume>")
            self._write(os.path.join(rdir, aiqueue.reply_todo_name(batch)), aiqueue.render_reply_todo(
                batch, [(1, "done", names[0], ""), (2, "skipped", "", "The posting text was too short.")]))
            page = self.c.get("/queue").data.decode()                            # opening the page imports
            self.assertIn("Imported 1 reply", page)
            self.assertIn("The posting text was too short.", page)
            self.assertIn("Folder resume body", self.c.get(f"/job/{self.jid}").data.decode())
            self.assertFalse(os.path.exists(os.path.join(rdir, names[0])))        # imported: reply and request gone
            self.assertFalse(os.path.exists(os.path.join(root, "requests", names[0])))
            self.assertTrue(os.path.exists(os.path.join(root, "requests", names[1])))   # skipped: stays
            self.assertTrue(os.path.exists(os.path.join(root, "requests", aiqueue.todo_name(batch))))
            # the batch has reported, so a new request starts a new batch
            self.c.post(f"/job/{self.jid}/queue", data={"kind": "resume"})
            newer = [n for n in self._items(root) if aiqueue.parse_item_name(n)[0] != batch]
            self.assertEqual(len(newer), 1)
            # removing the skipped item finishes the first batch: its TODO files go too
            conn = db.connect()
            iid = conn.execute("SELECT id FROM queue_items WHERE name=?", (names[1],)).fetchone()[0]
            conn.close()
            self.c.post(f"/queue/{iid}/delete")
            self.assertFalse(os.path.exists(os.path.join(root, "requests", aiqueue.todo_name(batch))))
            self.assertFalse(os.path.exists(os.path.join(rdir, aiqueue.reply_todo_name(batch))))
            # with no report, a reply is matched by its file name
            self._write(os.path.join(rdir, newer[0]), "<resume>Second resume</resume>")
            self.c.post("/queue/import")
            self.assertEqual(self._items(root), [])
            self.assertEqual([n for n in os.listdir(rdir)], [])
            self.assertEqual([n for n in os.listdir(os.path.join(root, "requests"))], [])
        finally:
            appmod.app.config.pop("QUEUE_ROOT", None)

    def test_queue_gap_plan_roundtrip(self):
        root = tempfile.mkdtemp()
        appmod.app.config["QUEUE_ROOT"] = root
        try:
            self.c.post("/gaps/queue", data={"profile": "", "min": "0", "hours": "7", "weeks": "10", "top": "10"})
            name = self._items(root)[0]
            self.assertIn("about 7 hours a week for 10 weeks", self._readf(os.path.join(root, "requests", name)))
            self._write(os.path.join(root, "replies", name), "<priorities>Queue priority one</priorities>")
            self.c.post("/queue/import")
            self.assertIn("Queue priority one", self.c.get("/gaps").data.decode())
        finally:
            appmod.app.config.pop("QUEUE_ROOT", None)

    def test_queue_help_page(self):
        page = self.c.get("/queue/help").data.decode()
        self.assertIn("AI_INSTRUCTIONS.md", page)
        self.assertNotIn("Claude", page)
        self.assertIn("How the AI queue works", self.c.get("/queue").data.decode())

    def test_filter_by_new_status(self):
        self.c.post(f"/job/{self.jid}/status", data={"status": "offer"})
        self.assertIn(b"Implementation Specialist", self.c.get("/?status=offer").data)
        self.assertNotIn(b"Implementation Specialist", self.c.get("/?status=rejected").data)



class SharedDetailsTests(unittest.TestCase):
    """Two computers sharing one WildThing/user folder, played by switching the data folder and database."""

    def setUp(self):
        self.saved_dir = settings.DATA_DIR
        self.shared = tempfile.mkdtemp()
        self.a, self.b = self._device(), self._device()
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()

    def tearDown(self):
        settings.DATA_DIR = self.saved_dir

    def _device(self):
        d = {"data": tempfile.mkdtemp(), "db": os.path.join(tempfile.mkdtemp(), "t.db")}
        settings.DATA_DIR = d["data"]
        settings.save_user({"shared_folder": self.shared, "target_titles": ["help desk"]})
        return d

    def use(self, d):
        settings.DATA_DIR, db.DB_PATH = d["data"], d["db"]

    def test_sync_both_ways_and_conflict(self):
        import usersync
        self.use(self.a)
        self.c.post("/settings/resume", data={"resume": (__import__("io").BytesIO(b"Jane Doe. SQL, help desk."), "r.txt")},
                    content_type="multipart/form-data")
        self.c.post("/profiles/save", data={"name": "Desk", "keywords": "help desk"})
        self.assertTrue(os.path.exists(os.path.join(self.shared, "resume.txt")))
        meta = json.load(open(os.path.join(self.shared, "search.json.meta.json"), encoding="utf-8"))
        self.assertEqual(meta["device"], settings.device_id())
        # the second computer has no resume yet, so it takes that; its own default search settings differ from
        # the folder's, and on a first sync that is a question, not a silent overwrite
        self.use(self.b)
        res = usersync.sync(db.connect())
        self.assertIn("resume", res["pulled"])
        self.assertEqual([c["key"] for c in res["conflicts"]], ["search.json"])
        self.c.post("/sync/resolve", data={"key": "search.json", "keep": "folder"})
        self.assertIn("Jane Doe", open(settings.resume_path(), encoding="utf-8").read())
        self.assertIn("Desk", [r[0] for r in db.connect().execute("SELECT name FROM profiles")])
        # B marks a skill; A picks it up on its next sync
        self.c.post("/have", data={"term": "itil"})
        self.use(self.a)
        usersync.sync(db.connect())
        self.assertEqual([r[0] for r in db.connect().execute("SELECT term FROM extras")], ["itil"])
        # both change the search settings: asked, not overwritten
        settings.save_user({"target_titles": ["analyst"]})
        self.use(self.b)
        settings.save_user({"target_titles": ["nurse"]})
        usersync.sync(db.connect())                                  # B pushes first
        self.use(self.a)
        res = usersync.sync(db.connect())
        self.assertEqual([c["key"] for c in res["conflicts"]], ["search.json"])
        self.assertEqual(settings.load()["target_titles"], ["analyst"])   # nothing changed yet
        self.assertIn("Changed in both places", self.c.get("/sync").data.decode())
        self.c.post("/sync/resolve", data={"key": "search.json", "keep": "folder"})
        self.assertEqual(settings.load()["target_titles"], ["nurse"])
        self.assertEqual(usersync.sync(db.connect())["conflicts"], [])

    def test_old_settings_file_is_split(self):
        settings.DATA_DIR = tempfile.mkdtemp()
        with open(os.path.join(settings.DATA_DIR, "user_settings.json"), "w", encoding="utf-8") as f:
            json.dump({"target_titles": ["x"], "your_name": "Jane"}, f)
        self.assertEqual(settings.load()["target_titles"], ["x"])
        self.assertEqual(json.load(open(os.path.join(settings.DATA_DIR, "shared_settings.json")))["target_titles"], ["x"])
        self.assertNotIn("target_titles", json.load(open(os.path.join(settings.DATA_DIR, "user_settings.json"))))

    def test_old_anthropic_key_is_ignored(self):
        settings.DATA_DIR = tempfile.mkdtemp()
        with open(appmod.keys_path(), "w", encoding="utf-8") as f:
            json.dump({"anthropic_api_key": "old", "adzuna_app_id": "ID9"}, f)
        db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
        self.assertEqual(self.c.get("/settings").status_code, 200)
        self.c.post("/settings", data={"target_titles": "x", "usajobs_key": "K"})
        saved = json.load(open(appmod.keys_path(), encoding="utf-8"))
        self.assertNotIn("anthropic_api_key", saved)
        self.assertEqual(saved["adzuna_app_id"], "ID9")



class FakeGoogleDrive:
    """Just enough of the Drive v3 REST API (the calls gdrive.Drive makes), kept in memory."""

    def __init__(self):
        self.files, self.calls, self._n = {}, [], 0

    class Resp:
        def __init__(self, status, body=None, content=b""):
            self.status_code, self._body, self.content = status, body, content

        def json(self):
            if self._body is None:
                raise ValueError("no json")
            return self._body

    def add(self, parent, name, data=b"", folder=False, modified=None):
        self._n += 1
        fid = f"f{self._n}"
        self.files[fid] = {"name": name, "parent": parent, "folder": folder, "data": data, "trashed": False,
                           "modified": modified or f"2030-01-01T00:00:{self._n:02d}Z"}
        return fid

    def find(self, path):
        """Ids of live files at a path like 'WildThing/requests/x.md'."""
        parent, ids = "root", []
        for i, part in enumerate(path.split("/")):
            ids = [k for k, f in self.files.items() if f["parent"] == parent and f["name"] == part and not f["trashed"]]
            if i < len(path.split("/")) - 1:
                if not ids:
                    return []
                parent = ids[0]
        return ids

    def names(self, path):
        folder = self.find(path)[0]
        return sorted(f["name"] for f in self.files.values() if f["parent"] == folder and not f["trashed"])

    def request(self, method, url, headers=None, timeout=None, params=None, json=None, data=None):
        import re
        self.calls.append((method, url))
        assert headers["Authorization"] == "Bearer test-token"
        params = params or {}
        if method == "GET" and url.endswith("/drive/v3/files"):
            parent = re.match(r"'([^']+)' in parents and trashed=false$", params["q"]).group(1)
            return self.Resp(200, {"files": [
                {"id": k, "name": f["name"], "modifiedTime": f["modified"],
                 "mimeType": "application/vnd.google-apps.folder" if f["folder"] else "text/markdown"}
                for k, f in self.files.items() if f["parent"] == parent and not f["trashed"]]})
        if method == "POST" and url.endswith("/drive/v3/files") and "/upload/" not in url:
            return self.Resp(200, {"id": self.add(json["parents"][0], json["name"], folder=True)})
        if method == "GET" and "/drive/v3/files/" in url:
            f = self.files.get(url.rsplit("/", 1)[1])
            return self.Resp(200, content=f["data"]) if f else self.Resp(404, {"error": {"message": "not found"}})
        if method == "POST" and url.endswith("/upload/drive/v3/files"):
            boundary = headers["Content-Type"].split("boundary=")[1].encode()
            parts = data.split(b"--" + boundary)
            meta = __import__("json").loads(parts[1].split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0])
            body = parts[2].split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
            return self.Resp(200, {"id": self.add(meta["parents"][0], meta["name"], body)})
        if method == "PATCH" and "/upload/drive/v3/files/" in url:
            self.files[url.rsplit("/", 1)[1]]["data"] = data
            return self.Resp(200, {})
        if method == "PATCH":
            self.files[url.rsplit("/", 1)[1]]["trashed"] = json["trashed"]
            return self.Resp(200, {})
        if method == "DELETE":
            del self.files[url.rsplit("/", 1)[1]]
            return self.Resp(204, {})
        raise AssertionError((method, url))


class GoogleDriveTests(unittest.TestCase):
    """The desktop app using the WildThing folder in Google Drive directly (gdrive.py), against a fake Drive."""

    def setUp(self):
        import gdrive
        self.gdrive = gdrive
        self.saved_dir = settings.DATA_DIR
        settings.DATA_DIR = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
        settings.save_user({"use_drive": True, "target_titles": ["implementation specialist"]})
        self.fake = FakeGoogleDrive()
        appmod.app.config["DRIVE"] = gdrive.Drive(lambda: "test-token", http=self.fake)
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()
        self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme", "text": GOOD})
        self.jid = db.connect().execute("SELECT id FROM jobs").fetchone()[0]

    def tearDown(self):
        appmod.app.config.pop("DRIVE", None)
        settings.DATA_DIR = self.saved_dir

    def test_queue_round_trip_in_drive(self):
        import aiqueue
        self.c.post(f"/job/{self.jid}/queue", data={"kind": "resume"})
        names = self.fake.names("WildThing/requests")
        self.assertEqual(len(names), 2)                                    # the request and its batch TODO
        item = [n for n in names if not n.startswith("TODO_")][0]
        batch = aiqueue.parse_item_name(item)[0]
        self.assertIn("AI_INSTRUCTIONS.md", self.fake.names("WildThing"))
        self.assertEqual(self.fake.names("WildThing/replies"), [])
        self.assertIn(b"<job_listing>", self.fake.files[self.fake.find("WildThing/requests/" + item)[0]]["data"])
        # the AI writes two copies with the same name (Drive allows that): the newest wins, both go
        replies = self.fake.find("WildThing/replies")[0]
        self.fake.add(replies, item, b"<resume>Older copy</resume>", modified="2030-01-01T00:00:00Z")
        self.fake.add(replies, item, b"<resume>Drive resume body</resume>", modified="2030-06-01T00:00:00Z")
        page = self.c.get("/queue").data.decode()
        self.assertIn("Imported 1 reply", page)
        self.assertIn("Google Drive: WildThing", page)
        self.assertIn("Drive resume body", self.c.get(f"/job/{self.jid}").data.decode())
        self.assertEqual(self.fake.names("WildThing/replies"), [])
        self.assertEqual(self.fake.names("WildThing/requests"), [])        # batch done: its TODO went too
        trashed = [f["name"] for f in self.fake.files.values() if f["trashed"]]
        self.assertEqual(sorted(trashed), sorted([item, item, item, aiqueue.todo_name(batch)]))   # to the trash by default
        self.assertEqual(len(self.fake.find("WildThing")), 1)             # one WildThing folder, found again each time

    def test_permanent_delete_setting(self):
        settings.save_user({"drive_permanent_delete": True})
        self.c.post(f"/job/{self.jid}/queue", data={"kind": "prep"})
        item = [n for n in self.fake.names("WildThing/requests") if not n.startswith("TODO_")][0]
        self.fake.add(self.fake.find("WildThing/replies")[0], item, b"<likely_questions>Q</likely_questions>")
        self.c.post("/queue/import")
        self.assertFalse(any(f["trashed"] for f in self.fake.files.values()))
        self.assertEqual(sum(1 for c in self.fake.calls if c[0] == "DELETE"), 3)    # reply, request, batch TODO
        self.assertEqual(self.fake.names("WildThing/replies"), [])

    def test_batches_in_another_folder_are_kept_not_dropped(self):
        root = tempfile.mkdtemp()
        settings.save_user({"use_drive": False, "queue_folder": root})
        self.c.post(f"/job/{self.jid}/queue", data={"kind": "resume"})
        settings.save_user({"use_drive": True})
        page = self.c.get("/queue").data.decode()
        self.assertIn("still wait in", page)
        self.assertEqual(db.connect().execute("SELECT COUNT(*) FROM queue_items WHERE status='waiting'").fetchone()[0], 1)
        settings.save_user({"use_drive": False})
        self.assertIn("Waiting for a reply", self.c.get("/queue").data.decode())

    def test_drive_trouble_is_a_message(self):
        def down():
            raise self.gdrive.DriveError("Google access has run out. Link Google again in Settings.")
        appmod.app.config["DRIVE"] = self.gdrive.Drive(down, http=self.fake)
        r = self.c.post(f"/job/{self.jid}/queue", data={"kind": "resume"}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Link Google again", r.data.decode())
        self.assertEqual(db.connect().execute("SELECT COUNT(*) FROM queue_items").fetchone()[0], 0)
        self.assertIn("Link Google again", self.c.get("/queue").data.decode())

    def test_shared_details_sync_through_drive(self):
        res = appmod.usersync.sync(db.connect(), None, None)              # no folder setting: nothing to do
        self.assertIsNone(res)
        self.c.post("/settings/resume", data={"resume": (__import__("io").BytesIO(b"Jane Doe. SQL, help desk."), "r.txt")},
                    content_type="multipart/form-data")
        names = self.fake.names("WildThing/user")
        for n in ("resume.txt", "resume.meta.json", "search.json", "search.json.meta.json"):
            self.assertIn(n, names)
        # the phone changes the search settings (a newer version in Drive); this computer takes them
        user = self.fake.find("WildThing/user")[0]
        doc = json.loads(self.fake.files[self.fake.find("WildThing/user/search.json")[0]]["data"])
        doc["target_titles"] = ["analyst"]
        data = json.dumps(doc).encode()
        meta_id = self.fake.find("WildThing/user/search.json.meta.json")[0]
        meta = json.loads(self.fake.files[meta_id]["data"])
        self.fake.files[self.fake.find("WildThing/user/search.json")[0]]["data"] = data
        meta.update({"version": meta["version"] + 1, "device": "android-test", "sha256": __import__("shared_details").sha256(data)})
        self.fake.files[meta_id]["data"] = json.dumps(meta).encode()
        self.assertIn("1 received", self.c.post("/sync", follow_redirects=True).data.decode())
        self.assertEqual(settings.load()["target_titles"], ["analyst"])
        self.assertIn("Google Drive: WildThing/user", self.c.get("/sync").data.decode())

    def test_check_drive_access_lists_what_the_app_sees(self):
        self.fake.add(self.fake.add("root", "WildThing", folder=True), "from-my-ai.md", b"x")
        page = self.c.post("/google/check", follow_redirects=True).data.decode()
        self.assertIn("from-my-ai.md", page)
        self.assertIn("AI_INSTRUCTIONS.md", page)


class GoogleSignInTests(unittest.TestCase):
    """Linking Google on the desktop: the browser goes to Google and comes back to the home page with a code."""

    def setUp(self):
        import gdrive
        self.gdrive = gdrive
        self.saved_dir = settings.DATA_DIR
        settings.DATA_DIR = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
        self.keys = os.path.join(tempfile.mkdtemp(), "keys.json")
        appmod.app.config["KEYS_PATH"] = self.keys
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()
        self.saved_post = gdrive.requests.post
        self.posts = []

    def tearDown(self):
        self.gdrive.requests.post = self.saved_post
        settings.DATA_DIR = self.saved_dir
        appmod.app.config["KEYS_PATH"] = os.path.join(self.saved_dir, "keys.local.json")

    def fake_post(self, *answers):
        answers = list(answers)

        class R:
            def __init__(self, status, body):
                self.status_code, self._b = status, body

            def json(self):
                return self._b

        def post(url, data=None, timeout=None):
            self.posts.append((url, data))
            return R(*answers.pop(0))
        self.gdrive.requests.post = post

    def test_link_needs_the_client_first(self):
        r = self.c.post("/google/link", follow_redirects=True)
        self.assertIn("client id and secret", r.data.decode())

    def test_link_round_trip_and_refresh(self):
        from urllib.parse import parse_qs, urlparse
        self.c.post("/settings", data={"google_client_id": "cid.apps.googleusercontent.com", "google_client_secret": "csecret"})
        self.assertIn("(saved)", self.c.get("/settings").data.decode())
        self.assertNotIn("csecret", self.c.get("/settings").data.decode())
        r = self.c.post("/google/link")
        q = parse_qs(urlparse(r.headers["Location"]).query)
        self.assertTrue(r.headers["Location"].startswith("https://accounts.google.com/"))
        self.assertEqual(q["client_id"], ["cid.apps.googleusercontent.com"])
        self.assertEqual(q["scope"], [self.gdrive.SCOPE_NARROW])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["redirect_uri"], ["http://localhost/"])
        self.assertNotIn("csecret", r.headers["Location"])
        # a reply with the wrong state is refused
        self.assertIn("did not come from this page", self.c.get("/?state=nope&code=x", follow_redirects=True).data.decode())
        r = self.c.post("/google/link")
        state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
        self.fake_post((200, {"access_token": "a1", "expires_in": 3600, "refresh_token": "r1", "scope": self.gdrive.SCOPE_NARROW}))
        page = self.c.get(f"/?state={state}&code=thecode", follow_redirects=True).data.decode()
        self.assertIn("Google is linked", page)
        self.assertEqual(self.posts[0][1]["code"], "thecode")
        self.assertEqual(self.posts[0][1]["client_secret"], "csecret")
        self.assertTrue(self.posts[0][1]["code_verifier"])
        self.assertTrue(settings.load()["use_drive"])
        self.assertTrue(os.path.exists(os.path.join(settings.DATA_DIR, "google_token.json")))
        # asking for full access afterwards says to link again
        self.c.post("/settings", data={"drive_section": "1", "use_drive": "on", "drive_full": "full"})
        self.assertIn("Link again", self.c.get("/settings").data.decode())
        # an expired access token is refreshed; a refused refresh unlinks with a clear message
        auth = self.gdrive.Auth("cid", "csecret")
        t = self.gdrive.load_token(); t["expires_at"] = 0; self.gdrive._save_token(t)
        self.fake_post((200, {"access_token": "a2", "expires_in": 3600}))
        self.assertEqual(auth(), "a2")
        self.assertEqual(self.gdrive.load_token()["refresh_token"], "r1")
        t = self.gdrive.load_token(); t["expires_at"] = 0; self.gdrive._save_token(t)
        self.fake_post((400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}))
        with self.assertRaises(self.gdrive.DriveError) as e:
            auth()
        self.assertIn("Link Google again", str(e.exception))
        self.assertFalse(self.gdrive.linked())

    def test_unlink_revokes_and_forgets(self):
        self.gdrive._save_token({"access_token": "a", "expires_at": 9e9, "refresh_token": "r9", "scope": ""})
        self.fake_post((200, {}))
        self.c.post("/google/unlink")
        self.assertEqual(self.posts[0], (self.gdrive.REVOKE_URL, {"token": "r9"}))
        self.assertFalse(self.gdrive.linked())

    def test_google_token_and_client_are_never_exported(self):
        self.gdrive._save_token({"access_token": "a", "expires_at": 9e9, "refresh_token": "r-secret", "scope": ""})
        self.c.post("/settings", data={"google_client_secret": "c-secret"})
        body = self.c.get("/export").data.decode()
        self.assertNotIn("r-secret", body)
        self.assertNotIn("c-secret", body)


class DataFolderTests(unittest.TestCase):
    """home.py: personal data lives outside the app folder, and moves when a new folder is chosen."""

    def setUp(self):
        import home, writer as writermod
        self.home, self.writer = home, writermod
        self.saved = (home.DEFAULT, home.APP_FOLDER, home.ROOT, settings.DATA_DIR, db.DB_PATH, writermod.BASE)
        self.app_folder, self.default = tempfile.mkdtemp(), os.path.join(tempfile.mkdtemp(), "WildThing")
        home.DEFAULT, home.APP_FOLDER, home.ROOT = self.default, self.app_folder, None

    def tearDown(self):
        (self.home.DEFAULT, self.home.APP_FOLDER, self.home.ROOT, settings.DATA_DIR, db.DB_PATH, self.writer.BASE) = self.saved

    def _put(self, folder, name, text="x"):
        p = os.path.join(folder, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def test_old_copy_in_the_app_folder_moves_out_at_start(self):
        self._put(self.app_folder, os.path.join("data", "user_settings.json"), "{}")
        self._put(self.app_folder, "keys.local.json", "{}")
        self._put(self.app_folder, "app.py", "code stays")
        root, moved = self.home.start()
        self.assertEqual(root, self.default)
        self.assertEqual(sorted(moved), ["data", "keys.local.json"])
        self.assertFalse(os.path.exists(os.path.join(self.app_folder, "data")))
        self.assertTrue(os.path.exists(os.path.join(self.app_folder, "app.py")))
        self.assertEqual(settings.DATA_DIR, os.path.join(self.default, "data"))
        self.assertEqual(db.DB_PATH, os.path.join(self.default, "jobs.db"))
        self.assertEqual(self.writer.BASE, self.default)

    def test_move_to_another_folder_and_back(self):
        self.home.start()
        self._put(self.default, os.path.join("data", "master_resume.md"), "Jane")
        db.connect().close()
        new = os.path.join(tempfile.mkdtemp(), "Mine")
        self.assertIn("Moved 2 item(s)", self.home.move_to(new))
        self.assertTrue(os.path.exists(os.path.join(new, "data", "master_resume.md")))
        self.assertTrue(os.path.exists(os.path.join(new, "jobs.db")))
        self.assertEqual(self.home.chosen(), new)                      # remembered for the next start
        self.assertEqual(settings.DATA_DIR, os.path.join(new, "data"))
        with self.assertRaises(ValueError):
            self.home.move_to(os.path.join(self.app_folder, "inside"))   # never into the app folder
        self.home.move_to("")                                              # empty: back to the default
        self.assertEqual(self.home.chosen(), self.default)
        self.assertTrue(os.path.exists(os.path.join(self.default, "data", "master_resume.md")))

    def test_move_refuses_a_folder_that_already_has_data(self):
        self.home.start()
        db.connect().close()
        other = tempfile.mkdtemp()
        self._put(other, "jobs.db", "someone else's")
        with self.assertRaises(ValueError):
            self.home.move_to(other)
        self.assertTrue(os.path.exists(os.path.join(self.default, "jobs.db")))


class SharedPostingsTests(unittest.TestCase):
    """Two devices sharing WildThing/user/wildthing.db in (a fake) Google Drive, played by switching data folders."""

    def setUp(self):
        import gdrive, workfolder, shared_db
        self.sdb, self.wf = shared_db, workfolder
        self.saved = (settings.DATA_DIR, db.DB_PATH)
        self.fake = FakeGoogleDrive()
        self.drive = gdrive.Drive(lambda: "test-token", http=self.fake)
        self.a, self.b = self._device(), self._device()

    def tearDown(self):
        settings.DATA_DIR, db.DB_PATH = self.saved

    def _device(self):
        return {"data": tempfile.mkdtemp(), "db": os.path.join(tempfile.mkdtemp(), "t.db")}

    def sync(self, d):
        settings.DATA_DIR, db.DB_PATH = d["data"], d["db"]
        conn = db.connect()
        user = self.wf.DriveDir(self.drive, "WildThing").sub("user")
        res = self.sdb.sync(conn, user, settings.device_id())
        conn.close()
        return res

    def q(self, d, sql, args=()):
        conn = db.connect(d["db"])
        rows = [dict(r) for r in conn.execute(sql, args)]
        conn.commit(); conn.close()
        return rows

    def add_job(self, d, ext_id="1", url="https://example.com/1", **kw):
        conn = db.connect(d["db"])
        cur = conn.execute("INSERT INTO jobs(source, ext_id, title, company, location, url, description, added_at, status, status_updated, notes) "
                           "VALUES ('remoteok',?,?,?,?,?,?,?,?,?,?)", (ext_id, kw.get("title", "Help Desk Analyst"), "Acme", "Remote", url,
                           "Help desk and SQL.", db.now(), kw.get("status", "new"), kw.get("status_updated"), kw.get("notes", "")))
        conn.commit(); jid = cur.lastrowid; conn.close()
        return jid

    def test_tags_and_avoided_companies_travel_both_ways(self):
        ja = self.add_job(self.a)
        conn = db.connect(self.a["db"])
        db.set_tag(conn, ja, "scam", True)
        db.set_avoided(conn, "Acme, Inc.", "ghosted", True)
        conn.commit(); conn.close()
        self.sync(self.a)
        jb = self.add_job(self.b)                              # the same posting, fetched on B too
        self.sync(self.b)
        self.assertEqual(self.q(self.b, "SELECT job_id, tag, active FROM job_tags"), [{"job_id": jb, "tag": "scam", "active": 1}])
        self.assertEqual([(r["key"], r["reason"]) for r in self.q(self.b, "SELECT * FROM avoided WHERE active=1")], [("acme", "ghosted")])
        # B removes both, later than A's changes: the removals reach A
        self.q(self.b, "UPDATE job_tags SET active=0, changed_at='2099-01-01T00:00:00+00:00'")
        self.q(self.b, "UPDATE avoided SET active=0, changed_at='2099-01-01T00:00:00+00:00'")
        self.sync(self.b); self.sync(self.a)
        self.assertEqual(self.q(self.a, "SELECT * FROM job_tags WHERE active=1"), [])
        self.assertEqual(self.q(self.a, "SELECT * FROM avoided WHERE active=1"), [])

    def test_a_version_1_file_reads_as_no_tags_or_avoided(self):
        import sqlite3
        snap = self.sdb.empty()
        snap["avoided"] = {"acme": {"company": "Acme", "reason": "", "active": 1, "changed_at": "2026-10-01T00:00:00+00:00"}}
        p = os.path.join(tempfile.mkdtemp(), "old.db")
        with open(p, "wb") as f:
            f.write(self.sdb.write_file(snap, "dev"))
        c = sqlite3.connect(p)
        c.executescript("DROP TABLE avoided; DROP TABLE tags; UPDATE info SET value='1' WHERE key='version';")
        c.commit(); c.close()
        with open(p, "rb") as f:
            old = self.sdb.read_file(f.read())
        self.assertEqual((old["avoided"], old["tags"]), ({}, {}))
        bad = self.sdb.write_file(self.sdb.empty(), "dev")
        p2 = os.path.join(tempfile.mkdtemp(), "new.db")
        with open(p2, "wb") as f:
            f.write(bad)
        c = sqlite3.connect(p2)
        c.execute("UPDATE info SET value='3' WHERE key='version'"); c.commit(); c.close()
        with open(p2, "rb") as f:
            with self.assertRaises(ValueError):
                self.sdb.read_file(f.read())

    def test_two_devices_share_status_notes_interviews_and_deletions(self):
        ja = self.add_job(self.a, status="applied", status_updated="2026-10-20T09:00:00+00:00", notes="sent")
        self.q(self.a, "INSERT INTO events(job_id, kind, starts_at) VALUES (?, 'Interview', '2026-11-05T10:00')", (ja,))
        self.assertEqual(self.sync(self.a)["arrived"], [])
        self.assertEqual(self.fake.names("WildThing/user"), ["wildthing.db"])
        # B already had the same posting (fetched there too): matched, not doubled; A's newer status and notes arrive
        self.add_job(self.b)
        res = self.sync(self.b)
        self.assertEqual(res["arrived"], [])
        jobs = self.q(self.b, "SELECT * FROM jobs")
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["status"], jobs[0]["notes"]), ("applied", "sent"))
        self.assertEqual(self.q(self.b, "SELECT uid FROM jobs")[0]["uid"], self.q(self.a, "SELECT uid FROM jobs")[0]["uid"])
        self.assertEqual(len(self.q(self.b, "SELECT * FROM events")), 1)
        # both write notes before syncing: both kept; B moves the status on; A sees it all
        self.q(self.a, "UPDATE jobs SET notes='sent; thank-you note too'")
        self.q(self.b, "UPDATE jobs SET notes='recruiter is Sam', status='interview', status_updated='2026-10-28T09:00:00+00:00'")
        self.sync(self.b); self.sync(self.a); self.sync(self.b)
        for d in (self.a, self.b):
            j = self.q(d, "SELECT status, notes FROM jobs")[0]
            self.assertEqual(j["status"], "interview")
            self.assertIn("thank-you note too", j["notes"]); self.assertIn("recruiter is Sam", j["notes"])
        # a posting only B has arrives on A, to be scored there
        self.add_job(self.b, ext_id="2", url="https://example.com/2", title="Project Coordinator")
        self.sync(self.b)
        self.assertEqual(len(self.sync(self.a)["arrived"]), 1)
        # A deletes the first posting: B loses it, with its interview
        self.q(self.a, "DELETE FROM jobs WHERE ext_id='1'")
        self.sync(self.a); self.sync(self.b)
        self.assertEqual([j["ext_id"] for j in self.q(self.b, "SELECT ext_id FROM jobs")], ["2"])
        self.assertEqual(self.q(self.b, "SELECT * FROM events"), [])

    def test_two_copies_in_drive_are_merged_into_one(self):
        self.add_job(self.a)
        self.sync(self.a)
        first = self.fake.files[self.fake.find("WildThing/user/wildthing.db")[0]]["data"]
        self.add_job(self.b, ext_id="2", url="https://example.com/2", title="Business Analyst")
        self.sync(self.b)
        # an upload that crossed: an older copy with the same name appears beside the current one
        self.fake.add(self.fake.find("WildThing/user")[0], "wildthing.db", first, modified="2000-01-01T00:00:00Z")
        self.add_job(self.a, ext_id="3", url="https://example.com/3", title="Project Coordinator")
        self.sync(self.a)
        self.assertEqual(self.fake.names("WildThing/user"), ["wildthing.db"])
        self.assertEqual(sorted(j["ext_id"] for j in self.q(self.a, "SELECT ext_id FROM jobs")), ["1", "2", "3"])

    def test_a_file_from_a_newer_version_is_refused(self):
        self.add_job(self.a)
        self.sync(self.a)
        import sqlite3
        f = self.fake.files[self.fake.find("WildThing/user/wildthing.db")[0]]
        p = os.path.join(tempfile.mkdtemp(), "x.db")
        open(p, "wb").write(f["data"])
        c = sqlite3.connect(p); c.execute("UPDATE info SET value='99' WHERE key='version'"); c.commit(); c.close()
        f["data"] = open(p, "rb").read()
        with self.assertRaises(ValueError):
            self.sync(self.b)

    def test_import_does_not_delete_elsewhere(self):
        import exchange
        self.add_job(self.a)
        conn = db.connect(self.a["db"])
        data = exchange.export_data(conn)
        exchange.import_data(conn, data)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tombstones").fetchone()[0], 0)
        conn.close()

class SettingsTests(unittest.TestCase):
    def setUp(self):
        self._dir = settings.DATA_DIR
        settings.DATA_DIR = tempfile.mkdtemp()           # a brand-new user: nothing set up yet
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        appmod.app.config["KEYS_PATH"] = os.path.join(self.tmp, "keys.json")
        self.c = appmod.app.test_client()

    def tearDown(self):
        settings.DATA_DIR = self._dir
        appmod.app.config["KEYS_PATH"] = os.path.join(self._dir, "keys.local.json")

    def test_new_user_sees_setup_banner_and_pages_still_load(self):
        for url in ("/", "/settings", "/resume", "/gaps", "/profiles", "/weekly", "/queue"):
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200, url)
        self.assertIn(b"Finish setup", self.c.get("/").data)
        self.assertNotIn(b"Jane", self.c.get("/settings").data)

    def test_upload_resume(self):
        import io
        r = self.c.post("/settings/resume", data={"resume": (io.BytesIO(b"Jane Doe\nSQL and Excel. Help desk support."), "me.txt")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"Master resume saved", r.data)
        self.assertTrue(os.path.exists(os.path.join(settings.DATA_DIR, "master_resume.txt")))
        self.assertIn("sql", matcher.find_terms(appmod.resume_text(), LEX))
        # replacing with a different type removes the old one
        with open(make_docx("Jane Doe\nSQL"), "rb") as f:
            self.c.post("/settings/resume", data={"resume": (f, "x.docx")}, content_type="multipart/form-data")
        self.assertFalse(os.path.exists(os.path.join(settings.DATA_DIR, "master_resume.txt")))
        self.assertTrue(os.path.exists(os.path.join(settings.DATA_DIR, "master_resume.docx")))

    def test_upload_rejects_bad_files(self):
        import io
        for name, data in (("a.exe", b"MZ"), ("b.docx", b"not a zip"), ("c.txt", b"")):
            r = self.c.post("/settings/resume", data={"resume": (io.BytesIO(data), name)},
                            content_type="multipart/form-data", follow_redirects=True)
            self.assertNotIn(b"Master resume saved", r.data, name)
        self.assertIsNone(settings.resume_path({}))

    def test_save_settings_and_keys(self):
        r = self.c.post("/settings", data={"your_name": "Jane", "target_titles": "Nurse, Care Coordinator",
                                           "search_keywords": "nurse", "locations": "denver\nremote", "place": "Denver, CO",
                                           "jobspy_enabled": "on", "instructions": "Be brief.", "adzuna_app_id": "ID1"},
                        follow_redirects=True)
        self.assertIn(b"Settings saved", r.data)
        c = appmod.cfg()
        self.assertEqual(c["target_titles"], ["nurse", "care coordinator"])
        self.assertEqual(c["locations"], ["denver", "remote"])
        self.assertEqual((c["jobspy"]["location"], c["adzuna"]["where"], c["linkedin"]["enabled"]), ("Denver, CO", "Denver, CO", False))
        self.assertTrue(c["send_resume_in_requests"])
        self.assertEqual(settings.instructions_text(c).strip(), "Be brief.")
        self.assertEqual(json.load(open(appmod.keys_path()))["adzuna_app_id"], "ID1")
        page = self.c.get("/settings").data
        self.assertNotIn(b"ID1", page)
        self.assertIn(b"(saved)", page)
        # blank key box keeps the saved key; reset restores the default instructions
        self.c.post("/settings", data={"target_titles": "nurse", "reset_instructions": "on"})
        self.assertEqual(json.load(open(appmod.keys_path()))["adzuna_app_id"], "ID1")
        self.assertIn("resume", settings.instructions_text(appmod.cfg()).lower())
        self.assertNotEqual(settings.instructions_text(appmod.cfg()).strip(), "Be brief.")

    def test_requests_carry_resume_unless_the_ai_already_has_it(self):
        self.c.post("/settings/resume", data={"resume": (__import__("io").BytesIO(b"Jane Doe. SQL, help desk."), "r.txt")},
                    content_type="multipart/form-data")
        msg = appmod.with_context("DO THE THING")
        self.assertIn("<master_resume>", msg)
        self.assertIn("Jane Doe", msg)
        self.assertTrue(msg.endswith("DO THE THING"))
        self.c.post("/settings", data={"target_titles": "x", "ai_has_resume": "on"})
        self.assertEqual(appmod.with_context("DO THE THING"), "DO THE THING")


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()
        self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme", "text": GOOD})
        self.jid = db.connect().execute("SELECT id FROM jobs").fetchone()[0]

    def test_nothing_selected_shows_the_dashboard_and_no_bottom_panel(self):
        page = self.c.get("/").data
        self.assertIn(b"Follow-ups due", page)
        self.assertIn(b'id="right"', page)
        self.assertNotIn(b'id="bottom"', page)
        self.assertIn(b"wildthing-64.png", page)

    def test_selecting_a_posting_fills_both_panels(self):
        page = self.c.get(f"/?sel={self.jid}").data.decode()
        self.assertIn('id="bottom"', page)
        self.assertIn("My progress", page)
        self.assertIn("AI work", page)
        self.assertIn("Why this score", page)
        self.assertIn("Posting text", page)
        self.assertIn("tr class=\"job sel\"", page)
        self.assertIn("itil", page)                        # a gap, with its I-have-this button
        self.assertEqual(self.c.get("/?sel=99999").status_code, 200)   # unknown id falls back to the dashboard
        self.assertEqual(self.c.get("/?sel=abc").status_code, 200)

    def test_panel_forms_return_to_the_same_page_and_never_leave_the_site(self):
        back = f"/?status=active&sel={self.jid}"
        r = self.c.post(f"/job/{self.jid}/event", data={"kind": "Interview", "starts_at": "2030-01-05T10:00", "back": back})
        self.assertEqual(r.headers["Location"], back)
        page = self.c.get(back).data.decode()
        self.assertIn("Add to Google Calendar", page)
        for bad in ("https://evil.example/x", "//evil.example/x"):
            r = self.c.post(f"/job/{self.jid}/event", data={"kind": "Interview", "starts_at": "2030-01-06T10:00", "back": bad})
            self.assertIn("/job/", r.headers["Location"])
        eid = db.connect().execute("SELECT id FROM events").fetchone()[0]
        r = self.c.post(f"/event/{eid}/delete", data={"back": back})
        self.assertEqual(r.headers["Location"], back)

    def test_queue_and_status_from_the_panel(self):
        self.c.application.config["QUEUE_ROOT"] = self.tmp
        r = self.c.post(f"/job/{self.jid}/queue", data={"kind": "prep"}, headers={"Referer": f"http://localhost/?sel={self.jid}"})
        self.assertIn(f"sel={self.jid}", r.headers["Location"])
        page = self.c.get(f"/?sel={self.jid}").data.decode()
        self.assertIn("waiting for a reply", page)
        self.c.application.config.pop("QUEUE_ROOT")

    def test_dashboard_lists_follow_ups(self):
        conn = db.connect()
        conn.execute("UPDATE jobs SET status='applied', applied_on='2020-01-01' WHERE id=?", (self.jid,)); conn.commit()
        self.assertIn(b"applied", self.c.get("/").data)
        self.assertIn(b"time to follow up", self.c.get(f"/?sel={self.jid}").data)


class MarksTests(unittest.TestCase):
    """Tags on postings and the companies you avoid, on the desktop's pages."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()
        self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme Inc", "text": GOOD})
        self.c.post("/add", data={"title": "Support Analyst", "company": "Beta", "text": GOOD})
        ids = [r[0] for r in db.connect().execute("SELECT id FROM jobs ORDER BY id")]
        self.acme, self.beta = ids

    def tags(self, jid):
        return db.job_tags(db.connect(), jid).get(jid, [])

    def test_tags_are_saved_shown_filtered_and_removed(self):
        self.c.post(f"/job/{self.acme}/tags", data={"tag": ["scam", "bogus"], "custom": "  Slow   to reply "})
        self.assertEqual(self.tags(self.acme), ["c:Slow to reply", "scam"])          # an unknown key is ignored
        page = self.c.get("/").data.decode()
        self.assertIn("Possible scam", page); self.assertIn("Slow to reply", page)
        filtered = self.c.get("/?tag=scam").data.decode()
        self.assertIn("Implementation Specialist", filtered); self.assertNotIn("Support Analyst", filtered)
        self.c.post(f"/job/{self.acme}/tags", data={"custom": "possible SCAM"})       # the built-in name ticks the box
        self.assertEqual(self.tags(self.acme), ["scam"])
        rows = db.connect().execute("SELECT tag, active FROM job_tags WHERE job_id=? ORDER BY tag", (self.acme,)).fetchall()
        self.assertEqual([tuple(r) for r in rows], [("c:Slow to reply", 0), ("scam", 1)])   # the removal is kept, to sync
        self.assertEqual(self.c.post("/job/99999/tags", data={}).status_code, 404)

    def test_tagged_postings_are_never_purged(self):
        self.c.post(f"/job/{self.acme}/tags", data={"tag": "ghost"})
        db.connect().execute("UPDATE jobs SET pasted=0").connection.commit()
        self.c.post("/purge", data={"scope": "untouched"})
        self.assertEqual([r[0] for r in db.connect().execute("SELECT id FROM jobs")], [self.acme])

    def test_avoided_company_is_hidden_until_shown_and_can_be_undone(self):
        r = self.c.post("/avoid", data={"company": "ACME", "reason": "lowball", "on": "1", "back": "/settings"}, follow_redirects=True)
        self.assertIn(b"lowball", r.data)                                           # listed in Settings
        page = self.c.get("/").data.decode()
        self.assertNotIn("Implementation Specialist", page); self.assertIn("Support Analyst", page)
        self.assertIn("1 hidden", page)
        shown = self.c.get("/?avoided=1").data.decode()
        self.assertIn("Implementation Specialist", shown); self.assertIn("avoided", shown)
        self.assertIn("You avoid ACME", self.c.get(f"/?sel={self.acme}&avoided=1").data.decode())
        self.c.post("/avoid", data={"company": "Acme Inc", "on": "0"})
        self.assertIn("Implementation Specialist", self.c.get("/").data.decode())
        r = self.c.post("/avoid", data={"company": " , ", "on": "1"}, follow_redirects=True)
        self.assertIn(b"no company name", r.data)
        r = self.c.post("/avoid", data={"company": "Acme", "on": "1", "back": "https://evil.example/"})
        self.assertNotIn("evil", r.headers["Location"])

    def test_merging_duplicates_keeps_the_tags(self):
        conn = db.connect()
        conn.execute("UPDATE jobs SET pasted=0, title='Analyst', company='Acme', source='remoteok'")
        conn.execute("UPDATE jobs SET ext_id='x' || id")
        conn.commit()
        db.set_tag(conn, self.beta, "agency", True); conn.commit()
        self.c.post("/dedupe")
        left = [r[0] for r in db.connect().execute("SELECT id FROM jobs")]
        self.assertEqual(len(left), 1)
        self.assertEqual(self.tags(left[0]), ["agency"])


class CareerPageTests(unittest.TestCase):
    """Building the career file on the desktop: the request, the work folder, the review, and the shared copy."""

    def setUp(self):
        import io
        self.io = io
        self.saved_dir = settings.DATA_DIR
        settings.DATA_DIR = tempfile.mkdtemp()
        self.folder = tempfile.mkdtemp()
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        appmod.app.config["QUEUE_ROOT"] = self.folder
        self.c = appmod.app.test_client()
        self.sample = shared("career_sample.json")

    def tearDown(self):
        settings.DATA_DIR = self.saved_dir
        appmod.app.config.pop("QUEUE_ROOT", None)

    def reply(self, data):
        return "<career_file>\n" + json.dumps(data) + "\n</career_file>"

    def test_scoring_reads_the_career_file_once_accepted(self):
        conn = db.connect()
        conn.execute("INSERT INTO jobs(source, ext_id, title, description, added_at) VALUES ('x','1','Analyst',?,'t')",
                     ("Requirements: SQL, Excel, ITIL and CompTIA A+ certification.",))
        conn.commit()
        jid = conn.execute("SELECT id FROM jobs").fetchone()["id"]
        appmod.rescore_all(conn)
        row = lambda: conn.execute("SELECT matched_json, gaps_json FROM jobs WHERE id=?", (jid,)).fetchone()
        self.assertEqual(json.loads(row()["matched_json"]), [])      # no resume and no career file yet
        self.assertEqual(appmod.scoring_source()[1], "resume")
        data = json.loads(json.dumps(self.sample))
        data["skills"] = [s for s in data["skills"] if s["name"] != "itil"]   # leaves only the in-progress certification
        self.c.post("/career/reply", data={"reply": self.reply(data)})
        self.assertIn(b"re-scored", self.c.post("/career/accept", follow_redirects=True).data)
        self.assertEqual(appmod.scoring_source()[1], "career")
        matched, gaps = json.loads(row()["matched_json"]), [g[0] for g in json.loads(row()["gaps_json"])]
        self.assertTrue({"sql", "excel", "comptia a+"} <= set(matched), matched)
        self.assertIn("itil", gaps)                                  # still in progress, so not counted
        page = self.c.get("/career").data.decode()
        self.assertIn("Skills scoring finds in it", page)
        self.assertIn("scored against your", self.c.get("/resume").data.decode())

    def test_i_have_this_lives_in_the_career_file(self):
        self.c.post("/have", data={"term": "python"})                 # no career file yet: kept in the list
        conn = db.connect()
        self.assertEqual([r["term"] for r in conn.execute("SELECT term FROM extras")], ["python"])
        self.c.post("/career/reply", data={"reply": self.reply(self.sample)})
        self.c.post("/career/accept")                                # the list moves into the file
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM extras").fetchone()[0], 0)
        skills = {s["name"]: s["source"] for s in settings.load_career()["skills"]}
        self.assertEqual(skills["python"], "confirmed")
        self.assertIn(b"to your career file", self.c.post("/have", data={"term": "linux"}, follow_redirects=True).data)
        self.assertEqual({s["name"]: s["source"] for s in settings.load_career()["skills"]}.get("linux"), "confirmed")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM extras").fetchone()[0], 0)
        self.assertIn("python", appmod.have_terms(conn))
        self.c.post("/unhave", data={"term": "python"})
        self.c.post("/unhave", data={"term": "sql"})                 # from the documents: stays
        names = career_mod().skill_names(settings.load_career())
        self.assertNotIn("python", names)
        self.assertIn("sql", names)
        self.assertNotIn("python", appmod.have_terms(conn))
        self.assertTrue(career_mod().validate(settings.load_career()) == [])

    def test_request_from_documents_then_folder_reply_then_accept(self):
        self.assertIn(b"No career file yet", self.c.get("/career").data)
        with open(make_docx("Systems Analyst at Northside Clinics, 2022 to now."), "rb") as f:
            docx = f.read()
        r = self.c.post("/career/request", data={
            "sources": [(self.io.BytesIO(docx), "kb_v3.docx"), (self.io.BytesIO(b"# Skills\n- SQL"), "skills.md"),
                        (self.io.BytesIO(b"%PDF"), "old.pdf")],
            "typed": "I did not manage anyone."}, content_type="multipart/form-data", follow_redirects=True)
        page = r.data.decode()
        self.assertIn("old.pdf was left out", page)
        self.assertIn("from 3 sources", page)
        draft = open(os.path.join(settings.DATA_DIR, "career_request.md"), encoding="utf-8").read()
        for want in ('<source_document name="kb_v3.docx">', "Northside Clinics", '<source_document name="skills.md">',
                     "I did not manage anyone.", "<career_file_instructions>", "A job posting is never a source"):
            self.assertIn(want, draft)
        self.assertNotIn("<current_career_file>", draft)

        r = self.c.post("/career/fetch", follow_redirects=True)
        self.assertIn(b"No career file reply", r.data)
        r = self.c.post("/career/send", follow_redirects=True)
        sent = os.listdir(os.path.join(self.folder, "requests"))
        self.assertEqual(len(sent), 1)
        self.assertRegex(sent[0], r"^career_\d{8}-\d{4}\.md$")
        self.assertTrue(os.path.exists(os.path.join(self.folder, "AI_INSTRUCTIONS.md")))
        os.makedirs(os.path.join(self.folder, "replies"), exist_ok=True)
        reply = sent[0][:-3] + ".reply.md"
        with open(os.path.join(self.folder, "replies", reply), "w", encoding="utf-8") as f:
            f.write(self.reply(self.sample))

        r = self.c.post("/career/fetch", follow_redirects=True)
        page = r.data.decode()
        self.assertIn("Review your new career file", page)
        self.assertIn("agile backlogs", page)                     # the AI's flag is shown
        self.assertIsNone(settings.load_career())                  # nothing kept before accepting
        r = self.c.post("/career/accept", follow_redirects=True)
        self.assertIn(b"Career file saved", r.data)
        saved = settings.load_career()
        self.assertEqual(saved["person"]["name"], "Jane Doe")
        self.assertEqual(career_mod().validate(saved), [])
        self.assertEqual(os.listdir(os.path.join(self.folder, "replies")), [])
        self.assertEqual(os.listdir(os.path.join(self.folder, "requests")), [])
        self.assertFalse(os.path.exists(os.path.join(settings.DATA_DIR, "career_request.md")))
        page = self.c.get("/career").data.decode()
        self.assertIn("Systems Analyst", page); self.assertIn("Never name: Northside Clinics", page)

    def test_a_bad_reply_is_refused_with_the_reasons(self):
        bad = dict(self.sample, roles=[dict(self.sample["roles"][0], start="April 2022")])
        r = self.c.post("/career/reply", data={"reply": self.reply(bad)}, follow_redirects=True)
        self.assertIn(b"was not used", r.data)
        self.assertIn(b"should be YYYY or YYYY-MM", r.data)
        r = self.c.post("/career/reply", data={"reply": "Sorry, I cannot."}, follow_redirects=True)
        self.assertIn(b"no &lt;career_file&gt; block", r.data)
        self.assertIsNone(appmod.career_pending())
        self.assertEqual(self.c.get("/career/review").status_code, 302)

    def test_rebuild_keeps_confirmed_skills_and_discard_changes_nothing(self):
        settings.save_career(self.sample)                          # has "itil", confirmed in the app
        r = self.c.post("/career/request", data={"typed": "New job since.", "include_current": "1"},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("<current_career_file>", open(os.path.join(settings.DATA_DIR, "career_request.md"), encoding="utf-8").read())
        new = json.loads(json.dumps(self.sample))
        new["skills"] = [s for s in new["skills"] if s["source"] == "documents"] + [{"name": "python", "source": "documents", "evidence": ["p1"]}]
        new["roles"].insert(0, dict(new["roles"][0], id="r0", title="IT Manager", employer="Delta", start="2025-01", end=""))
        page = self.c.post("/career/reply", data={"reply": self.reply(new)}, follow_redirects=True).data.decode()
        self.assertIn("Review your rebuilt career file", page)
        self.assertIn("+ python", page)
        self.assertIn("IT Manager at Delta", page)
        self.assertIn("because you confirmed them here: itil", page)
        self.c.post("/career/discard")
        self.assertEqual(settings.load_career(), self.sample)
        self.c.post("/career/reply", data={"reply": self.reply(new)})
        self.c.post("/career/accept")
        names = [s["name"] for s in settings.load_career()["skills"]]
        self.assertIn("python", names); self.assertIn("itil", names)

    def test_shared_with_the_other_device_and_a_bad_copy_is_refused(self):
        import usersync, workfolder
        user = tempfile.mkdtemp()
        settings.save_career(self.sample)
        conn = db.connect()
        res = usersync.sync(conn, target=workfolder.LocalDir(user))
        self.assertIn("career.json", res["pushed"])
        other = tempfile.mkdtemp()
        settings.DATA_DIR = other
        res = usersync.sync(db.connect(os.path.join(tempfile.mkdtemp(), "b.db")), target=workfolder.LocalDir(user))
        self.assertIn("career.json", res["pulled"])
        self.assertEqual(settings.load_career(), self.sample)
        # a copy someone broke in the folder (with a matching meta) is not used; the good one stays
        broken = b'{"format": "wildthing-career", "version": 1, "person": {"name": ""}}'
        with open(os.path.join(user, "career.json"), "wb") as f:
            f.write(broken)
        meta = json.load(open(os.path.join(user, "career.json.meta.json"), encoding="utf-8"))
        meta.update(sha256=__import__("shared_details").sha256(broken), version=meta["version"] + 1)
        with open(os.path.join(user, "career.json.meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        res = usersync.sync(db.connect(os.path.join(tempfile.mkdtemp(), "c.db")), target=workfolder.LocalDir(user))
        self.assertTrue(any("career file was not used" in e for e in res["errors"]), res)
        self.assertEqual(settings.load_career(), self.sample)


def career_mod():
    import career
    return career


class ExchangeTests(unittest.TestCase):
    """Export and import (docs/formats.md), using the same sample file the Android tests read."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        self.saved_dir = settings.DATA_DIR
        settings.DATA_DIR = tempfile.mkdtemp()
        self.c = appmod.app.test_client()

    def tearDown(self):
        settings.DATA_DIR = self.saved_dir

    def test_sample_imports_and_exports_the_same(self):
        import io
        with open(os.path.join(SHARED, "export_sample.json"), "rb") as f:
            raw = f.read()
        r = self.c.post("/import", data={"data": (io.BytesIO(raw), "x.json")}, follow_redirects=True)
        self.assertIn(b"Imported", r.data)
        sample = json.loads(raw)
        out = json.loads(self.c.get("/export").data)
        self.assertEqual(out["format"], "wildthing-export")
        self.assertEqual(out["resume"]["base64"], sample["resume"]["base64"])
        self.assertEqual(out["instructions"].strip(), sample["instructions"].strip())
        self.assertEqual(out["profiles"], sample["profiles"])
        self.assertEqual([x["term"] for x in out["extras"]], ["itil"])
        for got, want in zip(out["jobs"], sample["jobs"]):
            for k in ("id", "title", "status", "applied_on", "notes", "profile_ids", "links", "pasted", "tags"):
                self.assertEqual(got[k], want[k], k)
        self.assertEqual(out["avoided"], sample["avoided"])
        self.assertEqual(out["events"][0]["starts_at"], "2030-05-06T14:30")
        self.assertEqual([(o["job_id"], o["kind"]) for o in out["outputs"]], [(2, "prep"), (2, "resume")])
        self.assertEqual(out["gap_plans"][0]["scope"], "all postings")
        self.assertEqual(out["settings"]["your_name"], "Jane Doe")
        self.assertNotIn("api_key", json.dumps(out))

    def test_rejects_other_files(self):
        import io
        for body in (b"not json", b'{"format": "other"}', b'{"format": "wildthing-export", "version": 99}'):
            r = self.c.post("/import", data={"data": (io.BytesIO(body), "x.json")}, follow_redirects=True)
            self.assertIn(b"Could not import", r.data)


if __name__ == "__main__":
    unittest.main(verbosity=1)
