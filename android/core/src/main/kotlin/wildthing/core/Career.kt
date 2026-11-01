package wildthing.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * The career file (career.py; docs/formats.md section 9; shared_tests/career.json): everything true about the person,
 * in WildThing/user/career.json. An AI builds it; the app checks it, shows it for review and keeps it, and after that
 * only the app changes it. It stays a JsonObject, so fields this version does not know are kept.
 */
object Career {
    const val FORMAT = "wildthing-career"
    const val VERSION = 1
    const val FILE = "career.json"
    const val TAG = "career_file"
    val SKILL_SOURCES = listOf("documents", "confirmed")
    val CERT_STATUSES = listOf("earned", "in_progress", "expired")
    private val DATE = Regex("^\\d{4}(-(0[1-9]|1[0-2]))?$")
    private val REPLY = Regex("^career_(\\d{8}-\\d{4})\\.reply\\.md$")
    private val FENCE = Regex("^```[a-zA-Z]*\\s*\\n(.*)\\n```$", RegexOption.DOT_MATCHES_ALL)
    private val PRETTY = Json { prettyPrint = true; prettyPrintIndent = " " }

    /** Each list section: the fields its items must have (non-empty text) and may have (text). Order matters (messages). */
    private val TEXT = linkedMapOf(
        "roles" to (listOf("id", "employer", "title", "start") to listOf("end", "show_as", "location", "type", "scope", "details")),
        "projects" to (listOf("id", "name") to listOf("date", "description", "link")),
        "skills" to (listOf("name", "source") to listOf("notes")),
        "certifications" to (listOf("name", "status") to listOf("issuer", "date")),
        "education" to (listOf("school") to listOf("credential", "field", "start", "end", "notes")),
        "flags" to (listOf("text") to emptyList()),
    )
    private val DATES = mapOf("roles" to listOf("start", "end"), "projects" to listOf("date"), "certifications" to listOf("date"),
        "education" to listOf("start", "end"))
    private val LISTS = mapOf("roles" to listOf("achievements"), "projects" to listOf("skills"), "skills" to listOf("evidence"),
        "flags" to listOf("sources"))

    // ---- small JSON helpers, read the way Python reads a dict ----
    private fun JsonElement?.str(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.content
    private fun JsonElement?.isText() = this.str() != null
    private fun JsonElement?.obj() = this as? JsonObject
    private fun JsonElement?.arr() = this as? JsonArray
    private fun JsonObject.text(k: String) = this[k].str() ?: ""
    private fun JsonObject.list(k: String): List<JsonElement> = this[k].arr() ?: emptyList()
    /** str(v) in Python, for messages. */
    private fun show(v: JsonElement): String = v.str() ?: (v as? JsonPrimitive)?.let { p ->
        p.booleanOrNull?.let { if (it) "True" else "False" } ?: p.content.takeIf { p !is JsonNull } ?: "None"
    } ?: v.toString()

    fun empty(name: String = ""): JsonObject = Json.parseToJsonElement("""
        {"format": "$FORMAT", "version": $VERSION, "updated_at": "",
         "person": {"name": ${JsonPrimitive(name)}, "headline": "", "contact": {"email": "", "phone": "", "location": "", "links": []}},
         "summary": "", "roles": [], "skills": [], "certifications": [], "education": [], "projects": [],
         "privacy": {"never_name": [], "never_mention": []}, "wording": {"avoid": []}, "flags": []}
    """).obj()!!

    /** Plain reasons the data is not a usable career file (career.validate); empty means it is fine. */
    fun validate(data: JsonElement?): List<String> {
        val d = data.obj() ?: return listOf("That is not a career file (it should be one JSON object).")
        if (d["format"].str() != FORMAT) return listOf("That is not a WildThing career file (\"format\" should be \"$FORMAT\").")
        val v = (d["version"] as? JsonPrimitive)?.takeIf { !it.isString && it.longOrNull != null }?.longOrNull
            ?: return listOf("\"version\" should be a whole number.")
        if (v > VERSION) return listOf("That career file comes from a newer version of WildThing. Update this copy first.")
        val bad = mutableListOf<String>()
        val person = d["person"].obj()
        if (person == null || !person["name"].isText() || person.text("name").isBlank()) bad += "\"person.name\" is missing."
        else if (person["contact"] != null && person["contact"].obj() == null) bad += "\"person.contact\" should be an object."
        for (k in listOf("summary", "updated_at")) if (d[k] != null && !d[k].isText()) bad += "\"$k\" should be text."

        val ids = mutableSetOf<String>()
        for ((section, fields) in TEXT) {
            val (need, may) = fields
            val raw = d[section]
            if (raw != null && raw.arr() == null) { bad += "\"$section\" should be a list."; continue }
            for ((i, el) in d.list(section).withIndex()) {
                val at = "$section[$i]"
                val it = el.obj() ?: run { bad += "$at should be an object."; null } ?: continue
                for (f in need) if (!it[f].isText() || it.text(f).isBlank()) bad += "$at needs \"$f\"."
                for (f in may) if (it[f] != null && !it[f].isText()) bad += "$at.$f should be text."
                for (f in DATES[section].orEmpty()) {
                    val dv = it[f].str() ?: ""
                    if (dv.isNotEmpty() && !DATE.matches(dv)) bad += "$at.$f should be YYYY or YYYY-MM, not \"$dv\"."
                }
                for (f in LISTS[section].orEmpty()) if (it[f] != null && it[f].arr() == null) bad += "$at.$f should be a list."
                if ((section == "roles" || section == "projects") && it["id"].isText() && it.text("id").isNotBlank()) {
                    val id = it.text("id")
                    if (id in ids) bad += "$at uses the id \"$id\" again; every role and project needs its own."
                    ids += id
                }
                if (section == "roles") {
                    val s = it["start"].let { x -> if (x == null) "" else x.str() }
                    val e = it["end"].let { x -> if (x == null) "" else x.str() }
                    if (s != null && e != null && DATE.matches(s.ifEmpty { "x" }) && DATE.matches(e.ifEmpty { "x" }) && e < s.take(e.length))
                        bad += "$at ends before it starts."
                    for ((j, a) in it.list("achievements").withIndex()) {
                        val ao = a.obj()
                        if (ao == null || !ao["text"].isText() || ao.text("text").isBlank()) bad += "$at.achievements[$j] needs \"text\"."
                        else if (!listOf("skills", "numbers").all { k -> ao[k] == null || (ao[k].arr()?.all { x -> x.isText() } == true) })
                            bad += "$at.achievements[$j] skills and numbers should be lists of text."
                    }
                }
                if (section == "certifications" && it["status"].isText() && it.text("status").isNotBlank() && it.text("status") !in CERT_STATUSES)
                    bad += "$at.status should be one of ${CERT_STATUSES.joinToString(", ")}."
            }
        }

        val seen = mutableMapOf<String, Int>()
        for ((i, el) in d.list("skills").withIndex()) {
            val s = el.obj() ?: continue
            if (!s["name"].isText()) continue
            val at = "skills[$i]"
            val key = s.text("name").trim().lowercase()
            if (key in seen) bad += "$at repeats the skill \"${s.text("name")}\" (also skills[${seen.getValue(key)}])."
            seen.putIfAbsent(key, i)
            if (s["source"].isText() && s.text("source").isNotBlank() && s.text("source") !in SKILL_SOURCES)
                bad += "$at.source should be \"documents\" or \"confirmed\"."
            val ev = if (s["evidence"] == null) JsonArray(emptyList()) else s["evidence"].arr()
            if (ev != null) {
                for (e in ev) if (e.str() == null || e.str() !in ids) bad += "$at points to \"${show(e)}\", which is not a role or project id."
                val notes = s["notes"]?.let(::show) ?: ""
                if (s["source"].str() == "documents" && ev.isEmpty() && notes.isBlank())
                    bad += "$at (\"${s.text("name")}\") needs evidence (a role or project id) or notes saying where it comes from."
            }
        }

        for ((section, fields) in listOf("privacy" to listOf("never_name", "never_mention"), "wording" to listOf("avoid"))) {
            val raw = d[section]
            val part = if (raw == null) JsonObject(emptyMap()) else raw.obj()
            if (part == null) { bad += "\"$section\" should be an object."; continue }
            for (f in fields) {
                val fv = if (part[f] == null) JsonArray(emptyList()) else part[f]
                if (f == "avoid") {
                    if (fv.arr()?.all { x -> x.obj()?.let { o -> o["phrase"].isText() && o.text("phrase").isNotBlank() } == true } != true)
                        bad += "\"wording.avoid\" should be a list of {\"phrase\", \"why\"}."
                } else if (fv.arr()?.all { x -> x.isText() && x.str()!!.isNotBlank() } != true) bad += "\"$section.$f\" should be a list of text."
            }
        }
        return bad
    }

    /** (career file, problems) from an AI's reply (career.read_reply). The file is null when there are problems. */
    fun readReply(text: String?): Pair<JsonObject?, List<String>> {
        val m = Regex("<$TAG>(.*?)</$TAG>", RegexOption.DOT_MATCHES_ALL).find(text ?: "")
            ?: return null to listOf("The reply has no <$TAG> block.")
        var body = m.groupValues[1].trim()
        FENCE.matchEntire(body)?.let { body = it.groupValues[1].trim() }
        val data = try { Json.parseToJsonElement(body) } catch (e: Exception) {
            return null to listOf("The career file is not valid JSON: ${e.message}")
        }
        val problems = validate(data)
        return if (problems.isEmpty()) data.obj() to emptyList() else null to problems
    }

    fun skillNames(data: JsonObject) = data.list("skills").mapNotNull { it.obj()?.text("name") }

    private fun find(data: JsonObject, name: String): Int? {
        val key = name.trim().lowercase()
        return data.list("skills").indexOfFirst { it.obj()?.text("name")?.trim()?.lowercase() == key }.takeIf { it >= 0 }
    }

    private fun withSkills(data: JsonObject, skills: List<JsonElement>, now: String) =
        JsonObject(data + mapOf("skills" to JsonArray(skills), "updated_at" to JsonPrimitive(now)))

    /** "I have this": adds the skill as confirmed unless the file already lists it. */
    fun addConfirmed(data: JsonObject, name: String, now: String): JsonObject {
        if (name.isBlank() || find(data, name) != null) return data
        val skill = JsonObject(mapOf("name" to JsonPrimitive(name.trim()), "source" to JsonPrimitive("confirmed"),
            "evidence" to JsonArray(emptyList()), "notes" to JsonPrimitive("")))
        return withSkills(data, data.list("skills") + skill, now)
    }

    /** Undoes "I have this". Only a confirmed skill is removed. */
    fun removeConfirmed(data: JsonObject, name: String, now: String): JsonObject {
        val i = find(data, name) ?: return data
        if (data.list("skills")[i].obj()?.text("source") != "confirmed") return data
        return withSkills(data, data.list("skills").filterIndexed { j, _ -> j != i }, now)
    }

    /** A rebuilt file replacing the current one; confirmed skills it does not list are carried over. */
    fun replace(old: JsonObject?, new: JsonObject, now: String): JsonObject {
        var skills = new.list("skills")
        var out = new
        for (s in old?.list("skills").orEmpty()) {
            val o = s.obj() ?: continue
            if (o.text("source") == "confirmed" && find(out, o.text("name")) == null) {
                skills = skills + o
                out = JsonObject(out + ("skills" to JsonArray(skills)))
            }
        }
        return JsonObject(out + ("updated_at" to JsonPrimitive(now)))
    }

    /** All the factual text, for matching postings against (career.text). */
    fun text(data: JsonObject): String {
        val parts = mutableListOf(data.text("summary"), data["person"].obj()?.text("headline") ?: "")
        for (r in data.list("roles").mapNotNull { it.obj() }) {
            parts += listOf(r.text("title"), r.text("scope"), r.text("details"))
            for (a in r.list("achievements").mapNotNull { it.obj() }) parts += listOf(a.text("text")) + a.list("skills").mapNotNull { it.str() }
        }
        for (p in data.list("projects").mapNotNull { it.obj() }) parts += listOf(p.text("name"), p.text("description")) + p.list("skills").mapNotNull { it.str() }
        parts += skillNames(data)
        for (c in data.list("certifications").mapNotNull { it.obj() }) {     // one in progress, or lapsed, does not close a gap
            if ((c["status"].str() ?: "earned") == "earned") parts += listOf(c.text("name"), c.text("issuer"))
        }
        for (e in data.list("education").mapNotNull { it.obj() }) parts += listOf(e.text("credential"), e.text("field"))
        return parts.filter { it.isNotEmpty() }.joinToString("\n")
    }

    /** Warnings for a document that breaks the file's privacy and wording rules (career.check_document). */
    fun checkDocument(doc: String?, data: JsonObject): List<String> {
        val low = (doc ?: "").lowercase()
        val out = mutableListOf<String>()
        val privacy = data["privacy"].obj()
        for (n in privacy?.list("never_name").orEmpty().mapNotNull { it.str() }) if (n.lowercase() in low) out += "Names \"$n\", which your career file says never to name."
        for (n in privacy?.list("never_mention").orEmpty().mapNotNull { it.str() }) if (n.lowercase() in low) out += "Mentions \"$n\", which your career file says never to mention."
        for (w in data["wording"].obj()?.list("avoid").orEmpty().mapNotNull { it.obj() }) {
            val phrase = w.text("phrase"); val why = w.text("why")
            if (phrase.lowercase() in low) out += "Uses \"$phrase\"" + (if (why.isNotEmpty()) ": $why" else ".")
        }
        return out
    }

    // ---- the request and the reply's file names ----
    fun instructionsSection(md: String?): String =
        Regex("^## Building the career file\\s*$(.*?)(?=^## |\\z)", setOf(RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL))
            .find(md ?: "")?.groupValues?.get(1)?.trim() ?: ""

    /** sources: (file name, text). */
    fun buildRequest(section: String, sources: List<Pair<String, String>>, current: JsonObject? = null): String {
        val parts = mutableListOf("Build my career file, following these instructions. Use only the documents below and the current file. " +
            "Reply with the whole file between <$TAG> and </$TAG>, and nothing else.",
            "<career_file_instructions>\n" + section.trim() + "\n</career_file_instructions>")
        if (current != null) parts += "<current_career_file>\n" + PRETTY.encodeToString(JsonObject.serializer(), current) + "\n</current_career_file>"
        for ((name, body) in sources) parts += "<source_document name=\"${name.replace("\"", "")}\">\n" + body.trim() + "\n</source_document>"
        return parts.joinToString("\n\n") + "\n"
    }

    fun requestName(now: LocalDateTime): String = "career_" + now.format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmm")) + ".md"
    fun replyName(request: String) = request.dropLast(3) + ".reply.md"
    fun requestFor(reply: String) = reply.dropLast(".reply.md".length) + ".md"
    fun newestReply(names: List<String>): String? = names.filter { REPLY.matches(it) }.maxOrNull()

    // ---- what the review shows ----
    private fun labels(data: JsonObject): Map<String, List<String>> {
        fun span(a: String, b: String) = "${a.ifEmpty { "?" }} to ${b.ifEmpty { "now" }}"
        fun items(k: String) = data.list(k).mapNotNull { it.obj() }
        return linkedMapOf(
            "roles" to items("roles").map { "${it.text("title")} at ${it.text("employer")} (${span(it.text("start"), it.text("end"))})" },
            "skills" to items("skills").map { it.text("name") },
            "certifications" to items("certifications").map { it.text("name") + (if (it.text("status").isNotEmpty()) " (${it.text("status")})" else "") },
            "education" to items("education").map { e ->
                listOf(listOf(e.text("credential"), e.text("field")).filter { it.isNotEmpty() }.joinToString(" "), e.text("school"))
                    .filter { it.isNotEmpty() }.joinToString(", ")
            },
            "projects" to items("projects").map { it.text("name") },
        )
    }

    data class Change(val added: List<String>, val removed: List<String>)

    /** What a new file adds and removes compared with the current one (or null), by section; unchanged sections left out. */
    fun changes(old: JsonObject?, new: JsonObject): Map<String, Change> {
        val a = labels(old ?: empty()); val b = labels(new)
        val out = linkedMapOf<String, Change>()
        for ((k, now) in b) {
            val before = a.getValue(k)
            val added = now.filter { it !in before }; val removed = before.filter { it !in now }
            if (added.isNotEmpty() || removed.isNotEmpty()) out[k] = Change(added, removed)
        }
        return out
    }

    fun pretty(data: JsonObject): String = PRETTY.encodeToString(JsonObject.serializer(), data)
}
