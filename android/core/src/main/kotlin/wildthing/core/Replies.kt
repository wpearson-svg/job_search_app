package wildthing.core

import java.time.LocalDate
import java.util.regex.Pattern

/**
 * Requests to an AI and the tagged replies that come back. A port of the parts of writer.py that both versions
 * share; the formats are in docs/formats.md and the exact text in shared_tests/replies.json.
 */

/** What a request needs from a posting. */
data class RequestJob(
    val title: String = "",
    val company: String = "",
    val location: String = "",
    val description: String = "",
    val gaps: List<Pair<String, Int>> = emptyList(),
)

data class ResumeParts(val resume: String?, val coverLetter: String?, val reviewNotes: String?)

object Replies {
    val PREP_SECTIONS = listOf(
        "likely_questions" to "Questions they may ask you", "questions_to_ask" to "Questions to ask them",
        "gap_prep" to "Gaps to be ready for", "research" to "Research before the interview",
    )

    /** The trimmed text of the first <tag>...</tag>, or null when it is missing. */
    fun block(text: String?, tag: String): String? {
        val m = Pattern.compile("<$tag>(.*?)</$tag>", Pattern.DOTALL).matcher(text ?: "")
        return if (m.find()) m.group(1).pyStrip() else null
    }

    /** Each (label, text) whose tag is present and not empty, in the given order. */
    fun sections(text: String?, tags: List<Pair<String, String>>): List<Pair<String, String>> =
        tags.mapNotNull { (tag, label) -> block(text, tag)?.takeIf { it.isNotEmpty() }?.let { label to it } }

    fun parseBlocks(text: String?) = ResumeParts(block(text, "resume"), block(text, "cover_letter"), block(text, "review_notes"))

    fun parsePrep(text: String?) = sections(text, PREP_SECTIONS)

    private val BRACKETS = Regex("\\[[^\\]]*\\]")
    private val WORD = Regex("[A-Za-z0-9'&+#/.-]+")
    private val MARKUP = Regex("[*#\\\\]")

    /** The resume's hard rules; an empty list means no problems found. rules: (lower-case phrase, warning). */
    fun checkResume(resume: String?, rules: List<Pair<String, String>> = emptyList()): List<String> {
        if (resume.isNullOrEmpty()) return listOf("No <resume> block came back.")
        val warnings = mutableListOf<String>()
        BRACKETS.findAll(resume).forEach { warnings += "Bracket marker left in the resume: ${it.value}" }
        val low = resume.lowercase()
        for ((needle, msg) in rules) if (needle in low) warnings += msg
        val words = WORD.findAll(MARKUP.replace(resume, " ")).count()
        if (words > 600) warnings += "About $words words; the one-page target is 450 to 550."
        return warnings
    }

    fun slug(text: String?): String =
        Regex("[^a-z0-9]+").replace((text ?: "").lowercase(), "-").trim('-').take(40).ifEmpty { "posting" }

    /** Puts the instructions and master resume in front of a request, so it works in any AI chat. */
    fun withContext(message: String, instructions: String?, resumeText: String?): String {
        val r = (resumeText ?: "").pyStrip()
        return "<instructions>\n" + (instructions ?: "").pyStrip() + "\n</instructions>\n\n" +
            (if (r.isNotEmpty()) "<master_resume>\n$r\n</master_resume>\n\n" else "") + message
    }

    private fun listing(job: RequestJob): String {
        val head = listOf("Title" to job.title, "Company" to job.company, "Location" to job.location)
            .filter { it.second.isNotEmpty() }.map { "${it.first}: ${it.second}" }
        return (if (head.isNotEmpty()) head.joinToString("\n") + "\n\n" else "") + job.description
    }

    fun buildUserMessage(job: RequestJob, wantCover: Boolean): String {
        val ask = if (wantCover) "Build a resume and a cover letter for this listing." else "Build a resume for this listing."
        return "$ask\n\n<job_listing>\n${listing(job)}\n</job_listing>"
    }

    fun buildPrepMessage(job: RequestJob): String {
        val gaps = job.gaps.joinToString(", ") { it.first }.ifEmpty { "none found" }
        return "Prepare me for an interview for this listing. Use only facts from my master resume; " +
            "do not invent experience.\n\n" +
            "Reply using exactly these tags:\n" +
            "<likely_questions> 8 to 12 questions I am likely to be asked (behavioral, technical, role-specific), each with a " +
            "short answer outline built from my real experience </likely_questions>\n" +
            "<questions_to_ask> 10 strong questions I should ask them: the team, what success looks like, how they work, " +
            "the hiring process, and what worries them </questions_to_ask>\n" +
            "<gap_prep> for each gap below, an honest way to address it </gap_prep>\n" +
            "<research> what to look up about the company and role before the interview </research>\n\n" +
            "Gaps the app found between my resume and this listing: $gaps\n\n" +
            "<job_listing>\n${listing(job)}\n</job_listing>"
    }
}

/** Rules about where an application stands (tracking.py; shared_tests/tracking.json). */
object Tracking {
    const val FOLLOW_UP_DAYS = 14

    val STATUSES = listOf(
        "new" to "New", "saved" to "Saved", "applied" to "Applied", "phone_screen" to "Phone screen",
        "interview" to "Interview", "offer" to "Offer", "rejected" to "Rejected", "no_response" to "No response",
        "withdrawn" to "Withdrawn", "dismissed" to "Dismissed",
    )
    val APPLIED_STAGES = listOf("applied", "phone_screen", "interview", "offer", "rejected", "no_response", "withdrawn")
    val LABEL = STATUSES.toMap()
    /** Applications page order. */
    val STAGE_ORDER = listOf("offer", "interview", "phone_screen", "applied", "no_response", "rejected", "withdrawn")

    fun daysSince(isoDay: String?, today: LocalDate): Int? =
        runCatching { (today.toEpochDay() - LocalDate.parse(isoDay!!).toEpochDay()).toInt() }.getOrNull()

    fun needsFollowUp(status: String, appliedOn: String?, today: LocalDate): Boolean {
        val d = if (status == "applied") daysSince(appliedOn, today) else null
        return d != null && d >= FOLLOW_UP_DAYS
    }

    fun weeklySummary(days: Int, applied: Int, interviews: Int, rejected: Int, upcoming: Int, waiting: Int): String {
        val lines = mutableListOf("Job search, last $days days:", "- $applied application(s) sent")
        if (interviews > 0) lines += "- $interviews moved to a phone screen or interview"
        if (rejected > 0) lines += "- $rejected closed out"
        if (upcoming > 0) lines += "- $upcoming interview or follow-up coming up in the next 2 weeks"
        if (waiting > 0) lines += "- $waiting application(s) waiting 14+ days with no word, due for a follow-up"
        return lines.joinToString("\n")
    }

    fun interviewRate(applied: Int, interviews: Int): String =
        if (applied > 0) "${Math.rint(100.0 * interviews / applied).toInt()}%" else "n/a"
}
