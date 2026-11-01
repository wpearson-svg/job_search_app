package wildthing.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.time.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Runs every case in shared_tests/ (the repo root), the same cases the desktop tests run.
 * Both versions must give these exact answers. See shared_tests/make_fixtures.py for how they are made.
 */
class SharedFixturesTest {
    private val dir = File(System.getProperty("shared.dir") ?: "../../shared_tests")
    private fun load(name: String) = Json.parseToJsonElement(File(dir, name).readText()).jsonObject
    private fun cases(file: JsonObject, key: String) = file.getValue(key).jsonArray.map { it.jsonObject }
    private val JsonElement.str: String? get() = if (this is JsonNull) null else jsonPrimitive.content
    private fun JsonElement.strings() = jsonArray.map { it.jsonPrimitive.content }
    private fun JsonElement.pairs() = jsonArray.map { it.jsonArray[0].jsonPrimitive.content to it.jsonArray[1].jsonPrimitive.int }

    private fun j(v: Any?): JsonElement = when (v) {
        null -> JsonNull
        is JsonElement -> v
        is String -> JsonPrimitive(v)
        is Number -> JsonPrimitive(v)
        is Boolean -> JsonPrimitive(v)
        is Pair<*, *> -> JsonArray(listOf(j(v.first), j(v.second)))
        is List<*> -> JsonArray(v.map { j(it) })
        is Map<*, *> -> JsonObject(v.entries.associate { it.key as String to j(it.value) })
        else -> error("cannot compare $v")
    }

    private fun posting(p: Posting) = j(mapOf("source" to p.source, "ext_id" to p.extId, "title" to p.title,
        "company" to p.company, "location" to p.location, "url" to p.url, "description" to p.description, "posted" to p.posted))

    private fun row(r: GapRow) = mapOf("term" to r.term, "kind" to r.kind, "jobs" to r.jobs, "required" to r.required,
        "weight" to r.weight, "action" to r.action)

    private fun gapJob(o: JsonObject) = GapJob(
        o["title"]?.str ?: "", o["company"]?.str ?: "", o["description"]?.str ?: "",
        o["matched"]?.strings() ?: emptyList(), o.getValue("gaps").pairs())

    private fun requestJob(o: JsonObject) = RequestJob(
        o["title"]?.str ?: "", o["company"]?.str ?: "", o["location"]?.str ?: "", o["description"]?.str ?: "",
        o["gaps"]?.pairs() ?: emptyList())

    @Test
    fun scoring() {
        val d = load("scoring.json")
        for (c in cases(d, "find_terms")) {
            assertEquals(c.getValue("expect").strings(), Matcher.findTerms(c.getValue("text").str).sorted(), c.getValue("text").str!!.take(40))
        }
        for (c in cases(d, "score_job")) {
            val r = Matcher.scoreJob(c.getValue("title").str, c.getValue("text").str, c.getValue("have").strings().toSet(),
                Lexicons.default, c.getValue("target_titles").strings())
            val got = j(mapOf("score" to r.score, "matched" to r.matched, "gaps" to r.gaps, "flags" to r.flags,
                "title_match" to r.titleMatch))
            assertEquals(c.getValue("expect"), got, c.getValue("name").str)
        }
        for (c in cases(d, "location_ok")) {
            assertEquals(c.getValue("expect").jsonPrimitive.boolean,
                Matcher.locationOk(c.getValue("location").str, c.getValue("allowed").strings()), c.getValue("location").str)
        }
    }

    @Test
    fun dedupe() {
        val d = load("dedupe.json")
        for (c in cases(d, "norm")) assertEquals(c.getValue("expect").str, Dedupe.norm(c.getValue("text").str))
        for (c in cases(d, "dup_key")) {
            assertEquals(c.getValue("expect").str, Dedupe.dupKey(c.getValue("title").str, c.getValue("company").str))
        }
        for (c in cases(d, "same_place")) {
            assertEquals(c.getValue("expect").jsonPrimitive.boolean, Dedupe.samePlace(c.getValue("a").str, c.getValue("b").str),
                "${c["a"]} / ${c["b"]}")
        }
    }

    @Test
    fun gaps() {
        val d = load("gaps.json")
        for (c in cases(d, "build_plan")) {
            val (rows, phases) = Gaps.buildPlan(c.getValue("jobs").jsonArray.map { gapJob(it.jsonObject) })
            val got = j(mapOf("rows" to rows.map(::row), "phases" to phases.map { mapOf("label" to it.label, "items" to it.items.map(::row)) }))
            assertEquals(c.getValue("expect"), got)
        }
        for (c in cases(d, "build_message")) {
            val jobs = c.getValue("jobs").jsonArray.map { gapJob(it.jsonObject) }
            val (rows, _) = Gaps.buildPlan(jobs)
            val got = Gaps.buildMessage(rows, jobs, Lexicons.default, c.getValue("focus").str!!, c.getValue("extras").strings(),
                c.getValue("hours").jsonPrimitive.int, c.getValue("weeks").jsonPrimitive.int, c.getValue("top").jsonPrimitive.int)
            assertEquals(c.getValue("expect").str, got)
        }
        for (c in cases(d, "parse_plan")) assertEquals(c.getValue("expect"), j(Gaps.parsePlan(c.getValue("text").str)))
        assertEquals(d.getValue("actions"), j(Gaps.ACTIONS))
        assertEquals(d.getValue("sections"), j(Gaps.PLAN_SECTIONS))
    }

    @Test
    fun repliesAndRequests() {
        val d = load("replies.json")
        for (c in cases(d, "parse_blocks")) {
            val p = Replies.parseBlocks(c.getValue("text").str)
            assertEquals(c.getValue("expect"), j(mapOf("resume" to p.resume, "cover_letter" to p.coverLetter, "review_notes" to p.reviewNotes)))
        }
        for (c in cases(d, "check_resume")) {
            val rules = c.getValue("rules").jsonArray.map { it.jsonArray[0].jsonPrimitive.content to it.jsonArray[1].jsonPrimitive.content }
            assertEquals(c.getValue("expect").strings(), Replies.checkResume(c.getValue("text").str, rules))
        }
        for (c in cases(d, "build_user_message")) {
            assertEquals(c.getValue("expect").str,
                Replies.buildUserMessage(requestJob(c.getValue("job").jsonObject), c.getValue("want_cover").jsonPrimitive.boolean))
        }
        for (c in cases(d, "build_prep_message")) {
            assertEquals(c.getValue("expect").str, Replies.buildPrepMessage(requestJob(c.getValue("job").jsonObject)))
        }
        for (c in cases(d, "parse_prep")) assertEquals(c.getValue("expect"), j(Replies.parsePrep(c.getValue("text").str)))
        for (c in cases(d, "with_context")) {
            assertEquals(c.getValue("expect").str,
                Replies.withContext(c.getValue("message").str!!, c.getValue("instructions").str, c.getValue("resume").str))
        }
        for (c in cases(d, "slug")) assertEquals(c.getValue("expect").str, Replies.slug(c.getValue("text").str))
        assertEquals(d.getValue("prep_sections"), j(Replies.PREP_SECTIONS))
    }

    @Test
    fun sourceParsers() {
        val d = load("sources.json")
        for (c in cases(d, "strip_html")) assertEquals(c.getValue("expect").str, Html.strip(c.getValue("html").str))
        val parsers = mapOf<String, (JsonObject) -> List<Posting>>(
            "remoteok" to { Sources.parseRemoteOk(it.getValue("data")) },
            "remotive" to { Sources.parseRemotive(it.getValue("data")) },
            "adzuna" to { Sources.parseAdzuna(it.getValue("data")) },
            "usajobs" to { Sources.parseUsajobs(it.getValue("data")) },
            "greenhouse" to { Sources.parseGreenhouse(it.getValue("data"), it.getValue("board").str!!) },
            "lever" to { Sources.parseLever(it.getValue("data"), it.getValue("company").str!!) },
        )
        for ((name, parse) in parsers) for (c in cases(d, name)) {
            assertEquals(c.getValue("expect"), JsonArray(parse(c).map(::posting)), name)
        }
        for (c in cases(d, "title_wanted")) {
            assertEquals(c.getValue("expect").jsonPrimitive.boolean,
                Sources.titleWanted(c.getValue("title").str, c.getValue("targets").strings()))
        }
    }

    @Test
    fun tracking() {
        val d = load("tracking.json")
        assertEquals(d.getValue("statuses"), j(Tracking.STATUSES))
        assertEquals(d.getValue("applied_stages"), j(Tracking.APPLIED_STAGES))
        assertEquals(d.getValue("follow_up_days").jsonPrimitive.int, Tracking.FOLLOW_UP_DAYS)
        for (c in cases(d, "needs_follow_up")) {
            assertEquals(c.getValue("expect").jsonPrimitive.boolean, Tracking.needsFollowUp(c.getValue("status").str!!,
                c.getValue("applied_on").str, LocalDate.parse(c.getValue("today").str)))
        }
        for (c in cases(d, "days_since")) {
            val want = c.getValue("expect").let { if (it is JsonNull) null else it.jsonPrimitive.int }
            assertEquals(want, Tracking.daysSince(c.getValue("applied_on").str, LocalDate.parse(c.getValue("today").str)))
        }
        for (c in cases(d, "weekly_summary")) {
            val a = c.getValue("args").jsonArray.map { it.jsonPrimitive.int }
            assertEquals(c.getValue("expect").str, Tracking.weeklySummary(a[0], a[1], a[2], a[3], a[4], a[5]))
        }
        for (c in cases(d, "interview_rate")) {
            assertEquals(c.getValue("expect").str,
                Tracking.interviewRate(c.getValue("applied").jsonPrimitive.int, c.getValue("interviews").jsonPrimitive.int))
        }
    }

    @Test
    fun queueFormat() {
        val d = load("queue.json")
        assertEquals(d.getValue("kinds"), j(AiQueue.KINDS))
        assertEquals(d.getValue("reply_tags"), j(AiQueue.REPLY_TAGS))
        for (c in cases(d, "render_todo")) {
            val items = c.getValue("items").jsonArray.map { it.jsonObject }.map {
                AiQueue.TodoItem(it.getValue("n").jsonPrimitive.int, it.getValue("kind").str!!, it.getValue("label").str!!)
            }
            assertEquals(c.getValue("expect").str, AiQueue.renderTodo(c.getValue("batch").str!!, c.getValue("origin").str!!,
                c.getValue("created").str!!, items, c.getValue("carries_context").jsonPrimitive.boolean))
        }
        for (c in cases(d, "render_request")) {
            assertEquals(c.getValue("expect").str, AiQueue.renderRequest(c.getValue("batch").str!!, c.getValue("n").jsonPrimitive.int,
                c.getValue("kind").str!!, c.getValue("label").str!!, c.getValue("body").str!!))
        }
        for (c in cases(d, "parse_item_name")) {
            val got = AiQueue.parseItemName(c.getValue("name").str)
            assertEquals(c.getValue("expect"), if (got == null) JsonNull else j(listOf(got.batch, got.n, got.kind)), c.getValue("name").str)
        }
        for (c in cases(d, "todo_names")) {
            assertEquals(c.getValue("todo").str, AiQueue.batchOfTodo(c.getValue("name").str))
            assertEquals(c.getValue("reply_todo").str, AiQueue.batchOfReplyTodo(c.getValue("name").str))
        }
        for (c in cases(d, "parse_reply_todo")) {
            val got = AiQueue.parseReplyTodo(c.getValue("text").str).mapKeys { it.key.toString() }
                .mapValues { mapOf("status" to it.value.status, "reply" to it.value.reply, "reason" to it.value.reason) }
            assertEquals(c.getValue("expect"), j(got))
        }
        for (c in cases(d, "plan_import")) {
            val items = c.getValue("items").jsonArray.map { it.jsonObject }.map { AiQueue.Item(it.getValue("n").jsonPrimitive.int, it.getValue("name").str!!) }
            val replies = c.getValue("replies").jsonArray.map { it.jsonObject }.map { AiQueue.ReplyFile(it.getValue("name").str!!, it["modified"]?.str) }
            val plan = AiQueue.planImport(items, c.getValue("requests_present").strings().toSet(), replies, c["reply_todo"]?.str)
            val got = j(mapOf("items" to plan.items.map { mapOf("n" to it.n, "action" to it.action, "reply" to it.reply,
                "delete" to it.delete, "reason" to it.reason) }, "complete" to plan.complete))
            assertEquals(c.getValue("expect"), got, c.getValue("name").str)
        }
    }

    @Test
    fun sharedDetails() {
        val d = load("shared_details.json")
        assertEquals(d.getValue("files").strings(), SharedDetails.FILES)
        assertEquals(d.getValue("meta_names"), j(SharedDetails.FILES.associateWith { SharedDetails.metaName(it) }))
        val sd = d.getValue("search_doc").jsonObject
        val st = sd.getValue("settings").jsonObject
        val profiles = sd.getValue("profiles").jsonArray.map { it.jsonObject }.map {
            SharedDetails.SharedProfile(it.getValue("name").str!!, it.getValue("keywords").str!!, it.getValue("titles").str!!, it.getValue("location").str!!)
        }
        val doc = SharedDetails.searchDoc(st.getValue("target_titles").strings(), st.getValue("search_keywords").strings(),
            st.getValue("locations").strings(), profiles)
        assertEquals(sd.getValue("expect").str, doc.toString(Charsets.UTF_8))
        assertEquals(sd.getValue("sha256").str, SharedDetails.sha256(doc))
        val sk = d.getValue("skills_doc").jsonObject
        assertEquals(sk.getValue("expect").str, SharedDetails.skillsDoc(sk.getValue("terms").strings()).toString(Charsets.UTF_8))
        fun meta(e: JsonElement?) = if (e == null || e is JsonNull) null else e.jsonObject.let {
            SharedDetails.Meta(it.getValue("file").str!!, it.getValue("version").jsonPrimitive.int.toLong(), it.getValue("changed_at").str!!,
                it.getValue("device").str!!, it.getValue("sha256").str!!)
        }
        fun base(e: JsonElement?) = if (e == null || e is JsonNull) null else e.jsonObject.let {
            SharedDetails.Base(it["local"]?.str, it.getValue("remote").str!!, it["version"]?.jsonPrimitive?.int?.toLong() ?: 0)
        }
        for (c in cases(d, "decide")) {
            assertEquals(c.getValue("expect").str, SharedDetails.decide(c["local"]?.str, meta(c["remote"]), base(c["base"])), c.getValue("name").str)
        }
        for (c in cases(d, "next_version")) {
            val r = c["remote"]?.takeIf { it !is JsonNull }?.jsonObject?.let { SharedDetails.Meta("x", it.getValue("version").jsonPrimitive.int.toLong(), "", "", "x") }
            val b = c["base"]?.takeIf { it !is JsonNull }?.jsonObject?.let { SharedDetails.Base("x", "x", it.getValue("version").jsonPrimitive.int.toLong()) }
            assertEquals(c.getValue("expect").jsonPrimitive.int.toLong(), SharedDetails.nextVersion(r, b))
        }
    }

    @Test
    fun docx() {
        val d = load("resume.json")
        assertEquals(d.getValue("expect").str, Docx.text(File(dir, d.getValue("docx_file").str!!).readBytes()))
    }

    @Test
    fun exportSampleReadsAndWritesBack() {
        val raw = File(dir, "export_sample.json").readText()
        assertNull(ExportFormat.check(raw))
        val f = ExportFormat.read(raw)
        assertEquals(listOf(2L, 5L), f.jobs.map { it.id })
        assertEquals(listOf("salesforce" to 1), f.jobs[0].gapPairs())
        assertEquals("America/Chicago", f.events[0].timeZone)
        assertEquals(listOf(1L, 3L), f.jobs[0].profileIds)
        assertEquals(listOf("c:Slow to reply", "scam"), f.jobs[0].tags)
        assertEquals(listOf(ExportAvoided("Bad Co", "Ghosted twice")), f.avoided)
        assertEquals("Jane Doe", f.settings["your_name"]?.jsonPrimitive?.content)
        // Writing it back gives the same data (field order and spacing aside).
        assertEquals(Json.parseToJsonElement(raw), Json.parseToJsonElement(ExportFormat.write(f)))
        assertTrue(ExportFormat.check("""{"format":"wildthing-export","version":99}""")!!.contains("newer"))
        assertTrue(ExportFormat.check("""{"format":"other"}""") != null)
        assertTrue(ExportFormat.check("not json") != null)
    }

    @Test
    fun sharedResourcesComeFromTheRepoRoot() {
        // The build copies these from the repo root; a missing or stale copy would show up here.
        val root = dir.parentFile
        assertEquals(File(root, "skills.json").readText(), Resources.text("skills.json"))
        assertEquals(File(root, "default_instructions.md").readText(), Resources.text("default_instructions.md"))
        assertEquals(File(root, "docs/AI_INSTRUCTIONS.md").readText(), Resources.text("AI_INSTRUCTIONS.md"))
    }

    // ---- shared postings database (shared_tests/shared_db.json) ----
    private fun JsonElement.o() = jsonObject
    private fun JsonObject.s(k: String) = getValue(k).jsonPrimitive.content
    private fun JsonObject.n(k: String) = getValue(k).jsonPrimitive.int

    private fun snap(o: JsonObject) = SharedDb.Snapshot(
        postings = o.getValue("postings").o().mapValues { (_, v) -> v.o().let { p ->
            SharedDb.Posting(p.s("source"), p.s("ext_id"), p.s("title"), p.s("company"), p.s("location"), p.s("url"), p.s("description"),
                p.s("posted"), p.n("pasted"), p.s("added_at"), p.s("status"), p.s("status_at"), p.s("applied_on"), p.s("notes"),
                p.getValue("links").jsonArray.map { l -> SharedDb.Link(l.o().s("source"), l.o().s("url")) })
        } },
        events = o.getValue("events").o().mapValues { (_, v) -> v.o().let { e ->
            SharedDb.Event(e.s("posting"), e.s("kind"), e.s("starts_at"), e.n("minutes"), e.s("place"), e.s("notes"), e.s("time_zone"), e.s("changed_at"))
        } },
        outputs = o.getValue("outputs").o().mapValues { (_, v) -> v.o().let { x ->
            SharedDb.Output(x.s("posting"), x.s("kind"), x.s("content"), x.s("warnings_json"), x.s("created_at"))
        } },
        gapPlans = o.getValue("gap_plans").o().mapValues { (_, v) -> v.o().let { g -> SharedDb.GapPlan(g.s("scope"), g.s("content"), g.s("created_at")) } },
        tombstones = o.getValue("tombstones").o().mapValues { (_, v) -> SharedDb.Tomb(v.o().s("kind"), v.o().s("at")) },
        avoided = o.getValue("avoided").o().mapValues { (_, v) -> v.o().let { a -> SharedDb.Avoid(a.s("company"), a.s("reason"), a.n("active"), a.s("changed_at")) } },
        tags = o.getValue("tags").o().mapValues { (_, v) -> v.o().let { g -> SharedDb.Tag(g.s("posting"), g.s("tag"), g.n("active"), g.s("changed_at")) } },
    )

    private fun json(s: SharedDb.Snapshot) = j(mapOf(
        "postings" to s.postings.mapValues { (_, p) -> mapOf("source" to p.source, "ext_id" to p.extId, "title" to p.title,
            "company" to p.company, "location" to p.location, "url" to p.url, "description" to p.description, "posted" to p.posted,
            "added_at" to p.addedAt, "status" to p.status, "status_at" to p.statusAt, "applied_on" to p.appliedOn, "notes" to p.notes,
            "pasted" to p.pasted, "links" to p.links.map { mapOf("source" to it.source, "url" to it.url) }) },
        "events" to s.events.mapValues { (_, e) -> mapOf("posting" to e.posting, "kind" to e.kind, "starts_at" to e.startsAt,
            "minutes" to e.minutes, "place" to e.place, "notes" to e.notes, "time_zone" to e.timeZone, "changed_at" to e.changedAt) },
        "outputs" to s.outputs.mapValues { (_, x) -> mapOf("posting" to x.posting, "kind" to x.kind, "content" to x.content,
            "warnings_json" to x.warningsJson, "created_at" to x.createdAt) },
        "gap_plans" to s.gapPlans.mapValues { (_, g) -> mapOf("scope" to g.scope, "content" to g.content, "created_at" to g.createdAt) },
        "tombstones" to s.tombstones.mapValues { (_, t) -> mapOf("kind" to t.kind, "at" to t.at) },
        "avoided" to s.avoided.mapValues { (_, a) -> mapOf("company" to a.company, "reason" to a.reason, "active" to a.active, "changed_at" to a.changedAt) },
        "tags" to s.tags.mapValues { (_, g) -> mapOf("posting" to g.posting, "tag" to g.tag, "active" to g.active, "changed_at" to g.changedAt) },
    ))

    @Test
    fun sharedPostingsMerge() {
        val d = load("shared_db.json")
        assertEquals(SharedDb.FILE, d.s("file")); assertEquals(SharedDb.FORMAT, d.s("format"))
        assertEquals(SharedDb.VERSION, d.n("version")); assertEquals(SharedDb.COMBINE, d.s("combine"))
        for (c in cases(d, "merge")) {
            val base = c.getValue("base").o().mapValues { it.value.jsonPrimitive.content }
            val res = SharedDb.merge(snap(c.getValue("here").o()), snap(c.getValue("there").o()), base)
            val expect = c.getValue("expect").o()
            assertEquals(expect.getValue("merged"), json(res.merged), c.s("name"))
            assertEquals(expect.getValue("rename"), j(res.rename), c.s("name"))
        }
    }

    // ---- the career file (shared_tests/career.json) ----
    @Test
    fun careerFile() {
        val d = load("career.json")
        assertEquals(listOf(Career.FORMAT, Career.FILE, Career.TAG), listOf(d.s("format"), d.s("file"), d.s("tag")))
        assertEquals(Career.VERSION, d.n("version"))
        val sample = load(d.s("sample_file"))
        assertEquals(emptyList(), Career.validate(sample))
        assertEquals(d.getValue("sample_skills").strings(), Career.skillNames(sample))
        assertEquals(d.s("sample_text"), Career.text(sample))
        for (c in cases(d, "invalid")) assertEquals(c.getValue("problems").strings(), Career.validate(c.getValue("data")), c.s("name"))
        for (r in cases(d, "replies")) {
            val (data, problems) = Career.readReply(r.s("text"))
            assertEquals(r.getValue("ok").jsonPrimitive.boolean, data != null, r.s("name"))
            assertEquals(r.getValue("problems").strings(), problems.map { it.substringBefore(":") }, r.s("name"))
        }
        assertEquals(sample, Career.readReply(cases(d, "replies")[1].s("text")).first)
        val now = d.s("now"); val e = d.getValue("edits").o()
        assertEquals(e.getValue("add_new"), Career.addConfirmed(sample, "  Salesforce ", now))
        assertEquals(e.getValue("add_known"), Career.addConfirmed(sample, "SQL", now))
        assertEquals(e.getValue("remove_confirmed"), Career.removeConfirmed(sample, "ITIL", now))
        assertEquals(e.getValue("remove_documents"), Career.removeConfirmed(sample, "sql", now))
        val rebuilt = JsonObject(Career.empty("Jane Doe") + ("skills" to Json.parseToJsonElement(
            """[{"name": "sql", "source": "documents", "evidence": [], "notes": "x"}]""")))
        assertEquals(e.getValue("replace"), Career.replace(sample, rebuilt, now))
        assertEquals(e.getValue("empty"), Career.empty("Jane Doe"))
        for (c in cases(d, "check")) assertEquals(c.getValue("warnings").strings(), Career.checkDocument(c.s("doc"), sample))
        val sec = d.getValue("section").o()
        assertEquals(sec.s("expect"), Career.instructionsSection(sec.s("md")))
        val rq = d.getValue("request").o()
        val sources = rq.getValue("sources").jsonArray.map { it.jsonArray[0].jsonPrimitive.content to it.jsonArray[1].jsonPrimitive.content }
        assertEquals(rq.s("expect"), Career.buildRequest(rq.s("section"), sources))
        val names = d.getValue("names").o()
        assertEquals(names.s("request"), Career.requestName(java.time.LocalDateTime.of(2026, 11, 2, 9, 5)))
        assertEquals(names.s("reply"), Career.replyName(names.s("request")))
        assertEquals(names.s("request_for"), Career.requestFor(names.s("reply")))
        assertEquals(names.s("newest"), Career.newestReply(names.getValue("listed").strings()))
        for (c in cases(d, "changes")) {
            val old = c.getValue("old").let { if (it is JsonNull) null else it.o() }
            val got = Career.changes(old, c.getValue("new").o()).mapValues { (_, v) -> mapOf("added" to v.added, "removed" to v.removed) }
            assertEquals(c.getValue("expect"), j(got))
        }
        // a rebuild request carries the current file, readable back as the same JSON
        val withCurrent = Career.buildRequest("S", emptyList(), sample)
        val inside = withCurrent.substringAfter("<current_career_file>\n").substringBefore("\n</current_career_file>")
        assertEquals(sample, Json.parseToJsonElement(inside))
    }
}
