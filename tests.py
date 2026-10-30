import json, os, shutil, tempfile, unittest

import db, matcher, gaps, sources, writer, settings, resume as resumemod
import app as appmod

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = matcher.load_lexicon()

# Tests run against a private data folder holding a sample user (the resume and settings the app was built around),
# never against the real data/ folder.
settings.DATA_DIR = tempfile.mkdtemp()
shutil.copy(os.path.join(HERE, "Willis_Pearson_Resume_Master.docx"), os.path.join(settings.DATA_DIR, "master_resume.docx"))
shutil.copy(os.path.join(HERE, "Willis_Resume_Builder_API_System_Prompt.md"),
            os.path.join(settings.DATA_DIR, "resume_instructions.md"))
SAMPLE_USER = json.loads(r"""{
 "resume_file": "Willis_Pearson_Resume_Master.docx",
 "system_prompt_file": "Willis_Resume_Builder_API_System_Prompt.md",
 "target_titles": [
  "it support",
  "technical support",
  "service desk",
  "help desk",
  "desktop support",
  "implementation",
  "project coordinator",
  "project manager",
  "program coordinator",
  "business analyst",
  "systems analyst",
  "analyst",
  "change management",
  "technical project",
  "customer success",
  "solutions",
  "operations coordinator",
  "it coordinator"
 ],
 "search_keywords": [
  "it support",
  "implementation specialist",
  "project coordinator",
  "business analyst",
  "change management",
  "service desk"
 ],
 "locations": [
  "kansas city",
  "overland park",
  "kansas",
  "missouri",
  "remote",
  "united states",
  "usa"
 ],
 "adzuna": {
  "where": "Kansas City",
  "country": "us"
 },
 "usajobs": {
  "location": "Kansas City, Missouri"
 },
 "your_name": "Willis Pearson",
 "send_resume_in_requests": false,
 "resume_check_phrases": [
  [
   "managed a team",
   "Says \"managed a team\" (the prompt's rules say use led/implemented/trained)."
  ],
  [
   "2.5",
   "Mentions 2.5 (the rules say \"over 2 years\")."
  ]
 ],
 "linkedin": {
  "location": "Kansas City, Missouri"
 },
 "jobspy": {
  "location": "Kansas City, MO"
 }
}""")
SAMPLE_USER.pop("resume_file", None); SAMPLE_USER.pop("system_prompt_file", None)
with open(os.path.join(settings.DATA_DIR, "user_settings.json"), "w") as _f:
    json.dump(SAMPLE_USER, _f)
appmod.app.config["KEYS_PATH"] = os.path.join(settings.DATA_DIR, "keys.local.json")
CFG = settings.load()
RESUME = resumemod.read_resume(settings.resume_path(CFG))

GOOD = """Implementation Specialist. We roll out our scheduling software to customers.
Requirements: 2+ years of software implementation or IT support experience. Strong troubleshooting, end user training,
SQL and Excel skills. Experience with vendor management and stakeholder communication. Preferred: ITIL, Salesforce."""
SENIOR = """Senior Director of Engineering. Requirements: 10+ years of experience. Kubernetes, AWS, Terraform, Go, Java."""


class ResumeTests(unittest.TestCase):
    def test_reads_docx(self):
        self.assertIn("TrackTik", RESUME)
        self.assertIn("Champion National Security", RESUME)

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
        r = self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme", "location": "Kansas City, MO",
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

    def test_fetch_with_no_network_does_not_crash(self):
        r = self.c.post("/fetch", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"fetched 0 postings", r.data)


FAKE_REPLY = """Built it.
<resume>
**Willis T. Pearson III**
Kansas City, MO

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
        self.assertTrue(p["resume"].startswith("**Willis"))
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

    def test_system_prompt_is_the_whole_file(self):
        sp = writer.load_system_prompt(CFG)
        self.assertIn("career_knowledge_base", sp)
        self.assertIn("skills_bank", sp)
        self.assertGreater(len(sp), 30000)

    def test_generate_with_fake_model_and_files(self):
        tmp = tempfile.mkdtemp()
        seen = {}
        def fake(system, user, key, model, max_tokens):
            seen.update(system=system, user=user, key=key, model=model)
            return FAKE_REPLY
        job = {"id": 4, "title": "Analyst", "company": "Acme Co", "location": "", "description": GOOD}
        res = writer.generate(job, True, {**CFG, "output_dir": tmp}, {"anthropic_api_key": "k"}, caller=fake)
        self.assertEqual(seen["key"], "k")
        self.assertEqual(seen["model"], "claude-sonnet-5-5")
        self.assertIn("career_knowledge_base", seen["system"])
        names = [os.path.basename(f) for f in res["files"] if f.endswith(".md")]
        self.assertTrue(any(n.endswith("_resume.md") for n in names))
        self.assertTrue(any(n.endswith("_cover_letter.md") for n in names))
        self.assertTrue(any(n.endswith("_review_notes.md") for n in names))
        self.assertEqual(res["warnings"], [])

    def test_no_key_and_no_resume_block(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with self.assertRaises(RuntimeError) as c:
            writer.generate({"description": "x"}, False, CFG, {})
        self.assertIn("No Anthropic API key", str(c.exception))
        with self.assertRaises(RuntimeError) as c:
            writer.generate({"id": 1, "description": "x"}, False, CFG, {"anthropic_api_key": "k"}, caller=lambda *a: "oops")
        self.assertIn("no <resume> block", str(c.exception))


class BuildRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmp, "t.db")
        appmod.app.config["TESTING"] = True
        self.c = appmod.app.test_client()
        self.c.post("/add", data={"title": "Implementation Specialist", "company": "Acme", "text": GOOD})
        self.jid = db.connect().execute("SELECT id FROM jobs").fetchone()[0]
        self._gen = writer.generate

    def tearDown(self):
        writer.generate = self._gen

    def test_build_without_key_shows_message(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        r = self.c.post(f"/job/{self.jid}/build", data={}, follow_redirects=True)
        self.assertIn(b"No Anthropic API key", r.data)

    def test_build_stores_and_shows_documents(self):
        out = os.path.join(self.tmp, "out")
        writer.generate = lambda job, cover, cfg, keys, caller=None: self._gen(
            job, cover, {**cfg, "output_dir": out}, {"anthropic_api_key": "k"}, caller=lambda *a: FAKE_REPLY)
        r = self.c.post(f"/job/{self.jid}/build", data={"cover_letter": "1"}, follow_redirects=True)
        self.assertIn(b"Built.", r.data)
        self.assertIn(b"Led a software rollout", r.data)
        self.assertIn(b"Dear Hiring Team", r.data)
        self.assertIn(b"Hard gaps", r.data)
        self.assertTrue(os.listdir(out))


class PackageTests(BuildRouteTests):
    def test_page_offers_copy_and_import_and_hides_api_without_key(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        r = self.c.get(f"/job/{self.jid}")
        self.assertIn(b"Copy for Claude: resume", r.data)
        self.assertIn(b"Build a resume and a cover letter for this listing.", r.data)
        self.assertIn(b"Build a resume for this listing.", r.data)
        self.assertIn(b"Company: Acme", r.data)
        self.assertNotIn(b"Build with the API instead", r.data)

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
        self.assertIn(b"Paste Claude", r.data)


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
        ins("a", "Anywhere in the world"); ins("b", "Kansas City"); ins("c", "Berlin", "saved")
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
        sources.fetch_all = lambda cfg, keys: ([mk("w1", "Worldwide"), mk("k1", "Kansas City, MO"), mk("u1", "USA")], [])
        try:
            self.c.post("/fetch")
        finally:
            sources.fetch_all = orig
        conn = db.connect()
        got = {r[0] for r in conn.execute("SELECT ext_id FROM jobs WHERE source='remoteok'")}
        conn.close()
        self.assertEqual(got, {"k1", "u1"})

    def test_worldwide_is_never_in_area(self):
        allowed = ["kansas city", "remote", "usa"]
        for loc in ("Worldwide", "Anywhere", "Remote - Worldwide", "Remote (Anywhere)"):
            self.assertFalse(matcher.location_ok(loc, "", allowed), loc)
        for loc in ("Kansas City, MO", "Remote", "USA", ""):
            self.assertTrue(matcher.location_ok(loc, "", allowed), loc)

    def test_linkedin_parse_and_description(self):
        items = [{"position": "IT Support Specialist", "company": "Acme", "location": "Kansas City, MO", "date": "2026-10-29",
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
                                  "location": "Kansas City, MO", "url": url, "description": "d", "posted": ""}
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
        def ins(ext, status="new", loc="Kansas City", score=10):
            conn.execute("INSERT INTO jobs(source, ext_id, title, company, location, url, description, status, score, added_at) "
                         "VALUES ('x', ?, 'Analyst', 'Beta LLC', ?, ?, 'd', ?, ?, 'x')", (ext, loc, "https://x/" + ext, status, score))
        ins("a", score=50); ins("b", score=20); ins("c", status="applied"); ins("d", loc="Tulsa")
        conn.commit()
        self.c.post("/dedupe")
        left = {r[0] for r in conn.execute("SELECT ext_id FROM jobs WHERE company='Beta LLC'")}
        self.assertEqual(left, {"c", "d"})                       # applied one kept, other Kansas City copies merged into it
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
            return ([{"source": "remoteok", "ext_id": kw, "title": kw.title(), "company": "Co " + kw, "location": "Kansas City",
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
        job = {"source": "remoteok", "ext_id": "z1", "title": "Coordinator", "company": "Zed", "location": "Kansas City",
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
        rows = [{"site": "indeed", "id": "in-1", "title": "Help Desk Technician", "company": "Acme", "location": "Kansas City, MO, US",
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

    # ---- gap plan with Claude ----
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

    # ---- folder queue ----
    def test_queue_request_files_todo_and_import(self):
        root = tempfile.mkdtemp()
        appmod.app.config["QUEUE_ROOT"] = root
        try:
            self.c.post(f"/job/{self.jid}/queue", data={"kind": "resume_cover"})
            self.c.post(f"/job/{self.jid}/queue", data={"kind": "prep"})
            self.assertEqual(self.c.post(f"/job/{self.jid}/queue", data={"kind": "nope"}).status_code, 400)
            names = sorted(os.listdir(os.path.join(root, "requests")))
            self.assertEqual(len(names), 2)
            req = open(os.path.join(root, "requests", names[0]), encoding="utf-8").read()
            self.assertIn("replies/" + names[0], req); self.assertIn("<job_listing>", req)
            self.assertIn("cover letter", req)
            todo = open(os.path.join(root, "TODO.md"), encoding="utf-8").read()
            for n in names:
                self.assertIn(f"`requests/{n}`", todo)
            self.assertIn("Waiting for a reply", self.c.get("/queue").data.decode())
            self.c.post("/queue/import")                                   # nothing written yet: nothing imported
            self.assertIn("Waiting for a reply", self.c.get("/queue").data.decode())
            rdir = os.path.join(root, "replies")
            open(os.path.join(rdir, names[0]), "w", encoding="utf-8").write("<resume>Folder resume body</resume>")
            open(os.path.join(rdir, names[1]), "w", encoding="utf-8").write("<questions_to_ask>Folder question?</questions_to_ask>")
            self.assertIn("ready to import", self.c.get("/queue").data.decode())
            self.c.post("/queue/import")
            page = self.c.get(f"/job/{self.jid}").data.decode()
            self.assertIn("Folder resume body", page); self.assertIn("Folder question?", page)
            self.assertIn("Nothing waiting", open(os.path.join(root, "TODO.md"), encoding="utf-8").read())
            self.assertIn("Imported", self.c.get("/queue").data.decode())
        finally:
            appmod.app.config.pop("QUEUE_ROOT", None)

    def test_queue_gap_plan_roundtrip(self):
        root = tempfile.mkdtemp()
        appmod.app.config["QUEUE_ROOT"] = root
        try:
            self.c.post("/gaps/queue", data={"profile": "", "min": "0", "hours": "7", "weeks": "10", "top": "10"})
            name = os.listdir(os.path.join(root, "requests"))[0]
            self.assertIn("about 7 hours a week for 10 weeks", open(os.path.join(root, "requests", name), encoding="utf-8").read())
            open(os.path.join(root, "replies", name), "w", encoding="utf-8").write("<priorities>Queue priority one</priorities>")
            self.c.post("/queue/import")
            self.assertIn("Queue priority one", self.c.get("/gaps").data.decode())
        finally:
            appmod.app.config.pop("QUEUE_ROOT", None)

    def test_filter_by_new_status(self):
        self.c.post(f"/job/{self.jid}/status", data={"status": "offer"})
        self.assertIn(b"Implementation Specialist", self.c.get("/?status=offer").data)
        self.assertNotIn(b"Implementation Specialist", self.c.get("/?status=rejected").data)


if __name__ == "__main__":
    unittest.main(verbosity=1)


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
        self.assertNotIn(b"Willis", self.c.get("/settings").data)

    def test_upload_resume(self):
        import io
        r = self.c.post("/settings/resume", data={"resume": (io.BytesIO(b"Jane Doe\nSQL and Excel. Help desk support."), "me.txt")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"Master resume saved", r.data)
        self.assertTrue(os.path.exists(os.path.join(settings.DATA_DIR, "master_resume.txt")))
        self.assertIn("sql", matcher.find_terms(appmod.resume_text(), LEX))
        # replacing with a different type removes the old one
        with open(os.path.join(HERE, "Willis_Pearson_Resume_Master.docx"), "rb") as f:
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

    def test_requests_carry_resume_unless_claude_project_has_it(self):
        self.c.post("/settings/resume", data={"resume": (__import__("io").BytesIO(b"Jane Doe. SQL, help desk."), "r.txt")},
                    content_type="multipart/form-data")
        msg = appmod.with_context("DO THE THING")
        self.assertIn("<master_resume>", msg)
        self.assertIn("Jane Doe", msg)
        self.assertTrue(msg.endswith("DO THE THING"))
        self.c.post("/settings", data={"target_titles": "x", "claude_has_resume": "on"})
        self.assertEqual(appmod.with_context("DO THE THING"), "DO THE THING")
