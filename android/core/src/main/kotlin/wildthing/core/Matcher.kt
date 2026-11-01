package wildthing.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.util.regex.Pattern

/**
 * Scores a job posting against the resume, and lists what the posting wants that the resume does not show.
 * A port of matcher.py: plain rules, no AI. A term found in the posting's requirements part counts double.
 * The two versions are held to the same answers by shared_tests/scoring.json.
 */

/** Flags that make Java regex behave like Python 3 `re` on text: Unicode \s \d \w \b and case-insensitive matching. */
internal const val PY = Pattern.UNICODE_CHARACTER_CLASS or Pattern.UNICODE_CASE
internal fun py(regex: String, flags: Int = 0): Pattern = try {
    Pattern.compile(regex, PY or flags)
} catch (e: IllegalArgumentException) {
    // Android's regex engine (ICU) is Unicode-aware already and may not take the JDK-only flag.
    Pattern.compile(regex, (PY or flags) and Pattern.UNICODE_CHARACTER_CLASS.inv())
}
internal fun pyI(regex: String, flags: Int = 0): Pattern = py(regex, Pattern.CASE_INSENSITIVE or flags)

data class Term(val kind: String, val pattern: Pattern)

typealias Lexicon = Map<String, Term>

object Lexicons {
    /** The skill list from skills.json at the repo root (copied into the build). */
    val default: Lexicon by lazy { load(Resources.text("skills.json")) }

    fun load(json: String): Lexicon {
        val terms = Json.parseToJsonElement(json).jsonObject["terms"]!!.jsonObject
        val out = LinkedHashMap<String, Term>()
        for ((term, el) in terms) {
            val info = el.jsonObject
            val custom = info["pattern"]?.jsonPrimitive?.content
            val pat = if (!custom.isNullOrEmpty()) pyI(custom) else {
                val alts = info["aliases"]!!.jsonArray.map { it.jsonPrimitive.content }
                    .sortedByDescending { it.length }
                    .joinToString("|") { Pattern.quote(it.lowercase()) }
                pyI("(?<![a-z0-9])(?:$alts)(?![a-z0-9])")
            }
            out[term] = Term(info["kind"]?.jsonPrimitive?.content ?: "skill", pat)
        }
        return out
    }
}

data class ScoreResult(
    val score: Int,
    val matched: List<String>,
    val gaps: List<Pair<String, Int>>,
    val flags: List<String>,
    val titleMatch: Boolean,
)

object Matcher {
    private val SENIOR = pyI("\\b(senior|sr\\.?|principal|director|vice president|vp|head of|chief)\\b")
    private val REQ_HEAD = pyI(
        "(requirements|qualifications|what you.ll need|what you bring|must have|minimum qualifications|" +
            "skills and experience|experience required|who you are)")
    private val PREF_HEAD = pyI("(preferred|nice to have|bonus|a plus|desired)")
    private val YEARS = pyI("(\\d{1,2})\\s*\\+?\\s*(?:-\\s*\\d{1,2}\\s*)?years")

    /** "Worldwide" and "Anywhere" mean no real place, so they never count as in your area (even beside "Remote"). */
    val NOT_APPLICABLE = listOf("worldwide", "anywhere", "global")

    /** Terms from the lexicon that appear in the text. */
    fun findTerms(text: String?, lexicon: Lexicon = Lexicons.default): Set<String> =
        lexicon.filter { (_, t) -> t.pattern.matcher(text ?: "").find() }.keys

    /** (start, end) of the requirements part of a posting, or null when it has no such heading. */
    private fun zones(text: String): IntRange? {
        val m = REQ_HEAD.matcher(text)
        if (!m.find()) return null
        val p = PREF_HEAD.matcher(text)
        val end = if (p.find(m.end())) p.start() else text.length
        return m.start() until end
    }

    fun scoreJob(
        title: String?, text: String?, have: Set<String>, lexicon: Lexicon = Lexicons.default,
        targetTitles: List<String>,
    ): ScoreResult {
        val body = text ?: ""
        val head = title ?: ""
        val zone = zones(body)
        val weights = LinkedHashMap<String, Int>()
        for ((term, info) in lexicon) {
            if (!info.pattern.matcher(body).find()) continue
            var w = 1
            if (zone != null && info.pattern.matcher(body.substring(zone.first, zone.last + 1)).find()) w = 2
            weights[term] = w
        }
        val flags = mutableListOf<String>()
        val total = weights.values.sum()
        val matched = weights.keys.filter { it in have }.sorted()
        val gaps = weights.filterKeys { it !in have }.map { it.key to it.value }
            .sortedWith(compareBy<Pair<String, Int>>({ -it.second }, { it.first }))
        val got = matched.sumOf { weights.getValue(it) }

        val skillPct = if (total == 0) {
            flags += "No skills from your list found in this posting. It may be a short snippet or an unusual role."
            0.0
        } else 100.0 * got / total

        val lowTitle = head.lowercase()
        val titleMatch = targetTitles.any { it.lowercase() in lowTitle }
        var score = skillPct * 0.85 + (if (titleMatch) 15 else 0)

        if (SENIOR.matcher(head).find()) {
            score -= 15
            flags += "Senior-level title."
        }
        var top = 0
        val ym = YEARS.matcher(body)
        while (ym.find()) top = maxOf(top, ym.group(1).toInt())
        if (top >= 7) {
            score -= 10
            flags += "Asks for $top+ years of experience."
        } else if (top >= 5) {
            score -= 5
            flags += "Asks for $top+ years of experience."
        }
        if (body.codePointCount(0, body.length) < 400) {
            flags += "Very short description (possibly only a snippet), so the score is a rough guide."
        }
        // Python's round() rounds halves to even; Math.rint does the same.
        val rounded = Math.rint(score).toInt()
        return ScoreResult(rounded.coerceIn(0, 100), matched, gaps, flags, titleMatch)
    }

    fun locationOk(location: String?, allowed: List<String>): Boolean {
        val hay = (location ?: "").lowercase()
        if (hay.isBlank()) return true
        if (NOT_APPLICABLE.any { it in hay }) return false
        return allowed.any { it in hay }
    }
}

/** Reads text files the build copies from the repo root (skills.json, config.json, default_instructions.md). */
object Resources {
    fun text(name: String): String {
        val s = Resources::class.java.getResourceAsStream("/wildthing/$name")
            ?: error("$name is missing from the build (it is copied from the repo root).")
        return s.use { it.readBytes().toString(Charsets.UTF_8) }
    }

    /** config.json from the repo root: the neutral defaults that ship with the app. */
    val config: JsonObject by lazy { Json.parseToJsonElement(text("config.json")).jsonObject }
}
