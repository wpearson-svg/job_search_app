package wildthing.core

/** Turns the gaps across all saved postings into one ranked plan. A port of gaps.py (shared_tests/gaps.json). */

/** What the gap plan needs from a posting. */
data class GapJob(
    val title: String = "",
    val company: String = "",
    val description: String = "",
    val matched: List<String> = emptyList(),
    val gaps: List<Pair<String, Int>> = emptyList(),
)

data class GapRow(val term: String, val kind: String, val jobs: Int, val required: Int, val weight: Int, val action: String)
data class Phase(val label: String, val items: List<GapRow>)

object Gaps {
    val ACTIONS = linkedMapOf(
        "cert" to "Certification. Look up the exam objectives, book the exam, and add it to the resume only after you pass.",
        "tool" to "Tool. Use it for a small real project (a week or two), then add the project to the resume with what you built.",
        "skill" to "Skill. First check whether your past work already shows it and the resume just does not say so (use \"I have this\"). If not, practice it on a project or in a volunteer role.",
        "method" to "Method. Take a short course or read the standard guide, then apply it to your current project and write down the result.",
    )

    val PLAN_SECTIONS = listOf(
        "priorities" to "What to work on first, and why", "plan" to "Week-by-week plan",
        "proof" to "Projects that prove each skill", "resume_changes" to "Resume changes (only what is true)",
        "skip" to "What not to chase", "questions" to "Questions for you",
    )

    fun buildPlan(jobs: List<GapJob>, lexicon: Lexicon = Lexicons.default, perPhase: Int = 2): Pair<List<GapRow>, List<Phase>> {
        data class Agg(var jobs: Int = 0, var weight: Int = 0, var required: Int = 0)
        val agg = LinkedHashMap<String, Agg>()
        for (j in jobs) for ((term, w) in j.gaps) {
            val a = agg.getOrPut(term) { Agg() }
            a.jobs += 1
            a.weight += w
            if (w >= 2) a.required += 1
        }
        val rows = agg.map { (term, a) ->
            val kind = lexicon[term]?.kind ?: "skill"
            GapRow(term, kind, a.jobs, a.required, a.weight, ACTIONS[kind] ?: ACTIONS.getValue("skill"))
        }.sortedWith(compareBy<GapRow>({ -it.weight }, { -it.jobs }, { it.term }))
        val phases = mutableListOf<Phase>()
        var i = 0
        while (i < minOf(rows.size, 10)) {
            val start = (i / perPhase) * 2 + 1
            phases += Phase("Weeks $start-${start + 1}", rows.subList(i, minOf(i + perPhase, rows.size)))
            i += perPhase
        }
        return rows to phases
    }

    /** Short quotes from postings that ask for the term, so the planner sees how employers actually phrase it. */
    fun snippets(term: String, jobs: List<GapJob>, lexicon: Lexicon, limit: Int = 2, width: Int = 220): List<String> {
        val pat = lexicon.getValue(term).pattern
        val out = mutableListOf<String>()
        for (j in jobs) {
            if (j.gaps.none { it.first == term }) continue
            val text = j.description
            val m = pat.matcher(text)
            if (!m.find()) continue
            // Python's rfind(sub, 0, end) only finds a match that ends before `end`.
            val start = maxOf(text.lastIndexOf("\n", m.start() - 1), text.lastIndexOf(". ", m.start() - 2)) + 1
            val ends = listOf(text.indexOf("\n", m.end()), text.indexOf(". ", m.end())).filter { it != -1 }
            var sentence = text.substring(start, ends.minOrNull() ?: text.length).squeeze()
            if (sentence.length > width) sentence = sentence.substring(0, width).trimEnd() + "..."
            out += "${j.title} (${j.company.ifEmpty { "company not listed" }}): \"$sentence\""
            if (out.size >= limit) break
        }
        return out
    }

    fun topMatched(jobs: List<GapJob>, n: Int = 12): List<Pair<String, Int>> {
        val c = LinkedHashMap<String, Int>()
        for (j in jobs) for (t in j.matched) c[t] = (c[t] ?: 0) + 1
        return c.entries.sortedByDescending { it.value }.take(n).map { it.key to it.value }
    }

    fun buildMessage(
        rows: List<GapRow>, jobs: List<GapJob>, lexicon: Lexicon = Lexicons.default, focus: String = "all postings",
        extras: Collection<String> = emptyList(), hours: Int = 5, weeks: Int = 12, top: Int = 15,
    ): String {
        val lines = mutableListOf(
            "Build me a realistic skills plan from the gaps below. Use only facts from my master resume " +
                "when you talk about what I already have. Do not invent experience, and do not tell me to claim a skill I " +
                "have not shown. If you are unsure whether I have something, ask me in <questions>.",
            "",
            "Focus: $focus. Based on ${jobs.size} saved job postings.",
            "Time I can give: about $hours hours a week for $weeks weeks.",
            "",
            "Reply using exactly these tags:",
            "<priorities> the gaps in the order I should work on them, and why that order (what employers ask for most, " +
                "what is required rather than preferred, and what builds on what) </priorities>",
            "<plan> a week-by-week plan that fits my hours, with specific free or low-cost resources and what to finish " +
                "each week </plan>",
            "<proof> for each priority skill, a small project or result I can show an employer, ideally built on my real " +
                "work from my resume </proof>",
            "<resume_changes> wording I could add to my resume now, only where it is already true, and what to add later " +
                "once I finish each step </resume_changes>",
            "<skip> gaps that are not worth chasing for this focus, and why </skip>",
            "<questions> anything you need to ask me before the plan is right </questions>",
            "",
            "Gaps, most wanted first (a gap is a skill the postings ask for that my resume does not show):",
        )
        rows.take(top).forEachIndexed { i, r ->
            lines += "${i + 1}. ${r.term} (${r.kind}): in ${r.jobs} postings, listed as required in ${r.required}"
            snippets(r.term, jobs, lexicon).forEach { lines += "   - $it" }
        }
        if (rows.size > top) lines += "(${rows.size - top} smaller gaps left out.)"
        val tm = topMatched(jobs)
        if (tm.isNotEmpty()) {
            lines += ""
            lines += "Skills those postings ask for that my resume already shows (with how many postings): " +
                tm.joinToString(", ") { "${it.first} (${it.second})" }
        }
        if (extras.isNotEmpty()) {
            lines += ""
            lines += "Things I told the app I have, which my resume does not yet say: " + extras.sorted().joinToString(", ")
        }
        return lines.joinToString("\n")
    }

    fun parsePlan(text: String?): List<Pair<String, String>> = Replies.sections(text, PLAN_SECTIONS)
}
