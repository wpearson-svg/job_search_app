package wildthing.core

import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * The AI work queue format, shared with the desktop's aiqueue.py (docs/formats.md, section 5; shared_tests/queue.json).
 * The assistant only reads and creates files; WildThing imports, confirms, then deletes.
 */
object AiQueue {
    val KINDS = linkedMapOf("resume" to "Resume", "resume_cover" to "Resume and cover letter", "prep" to "Interview prep", "gap" to "Gap plan")
    val REPLY_TAGS = linkedMapOf(
        "resume" to "<resume>, <review_notes>",
        "resume_cover" to "<resume>, <cover_letter>, <review_notes>",
        "prep" to "<likely_questions>, <questions_to_ask>, <gap_prep>, <research>",
        "gap" to "<priorities>, <plan>, <proof>, <resume_changes>, <skip>, <questions>",
    )
    val STATUSES = listOf("done", "skipped", "failed")
    const val INSTRUCTIONS_FILE = "AI_INSTRUCTIONS.md"

    private val ITEM = Regex("^(\\d{8}-\\d{4}-[a-z0-9]{4})_(\\d{2,3})_(resume_cover|resume|prep|gap)_[a-z0-9-]*\\.md$")
    private val TODO = Regex("^TODO_(\\d{8}-\\d{4}-[a-z0-9]{4})\\.md$")
    private val REPLY_TODO = Regex("^TODO_(\\d{8}-\\d{4}-[a-z0-9]{4})\\.reply\\.md$")

    /** suffix: 4 lower-case letters or digits that make the id unique (Drive allows duplicate names). */
    fun batchId(now: LocalDateTime, suffix: String) = now.format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmm")) + "-" + suffix

    fun itemName(batch: String, n: Int, kind: String, label: String) = "${batch}_${"%02d".format(n)}_${kind}_${Replies.slug(label)}.md"
    fun todoName(batch: String) = "TODO_$batch.md"
    fun replyTodoName(batch: String) = "TODO_$batch.reply.md"

    data class ItemName(val batch: String, val n: Int, val kind: String)

    fun parseItemName(name: String?): ItemName? =
        ITEM.matchEntire(name ?: "")?.let { ItemName(it.groupValues[1], it.groupValues[2].toInt(), it.groupValues[3]) }

    fun batchOfTodo(name: String?) = TODO.matchEntire(name ?: "")?.groupValues?.get(1)
    fun batchOfReplyTodo(name: String?) = REPLY_TODO.matchEntire(name ?: "")?.groupValues?.get(1)

    fun renderRequest(batch: String, n: Int, kind: String, label: String, body: String): String {
        val name = itemName(batch, n, kind, label)
        return "# Request ${"%02d".format(n)} of batch $batch: ${KINDS.getValue(kind)}, $label\n\n" +
            "Write your answer to `replies/$name`. Reply with the tagged parts only (${REPLY_TAGS.getValue(kind)}); " +
            "use only facts from the master resume and do not invent experience.\n\n---\n\n" + body + "\n"
    }

    data class TodoItem(val n: Int, val kind: String, val label: String)

    fun renderTodo(batch: String, origin: String, created: String, items: List<TodoItem>, carriesContext: Boolean): String {
        val context = if (carriesContext) "Each request file contains the resume-writing instructions and the master resume."
        else "Use the resume-writing instructions and master resume you already hold for this person."
        val lines = mutableListOf(
            "# WildThing batch $batch", "", "- From: $origin", "- Created: $created", "- Items: ${items.size}", "",
            "Follow AI_INSTRUCTIONS.md in the WildThing folder. In short: do each item below, write each reply to " +
                "`replies/` under the reply file name shown, then write `replies/" + replyTodoName(batch) + "` with one row " +
                "per item. Skip any item whose reply file already exists. Use only facts from the master resume; do not " +
                "invent experience.",
            "", context, "",
            "| Item | Type | Request file | Reply file | Reply tags |",
            "|---|---|---|---|---|",
        )
        for (it in items) {
            val name = itemName(batch, it.n, it.kind, it.label)
            lines += "| ${"%02d".format(it.n)} | ${KINDS.getValue(it.kind)} | $name | $name | ${REPLY_TAGS.getValue(it.kind)} |"
        }
        return lines.joinToString("\n") + "\n"
    }

    data class Report(val status: String, val reply: String, val reason: String)

    private val NUMBER = Regex("\\d{1,3}")
    private val LIST_ROW = Regex("^\\s*[-*]?\\s*(\\d{1,3})\\s*[:.)-]?\\s*(done|skipped|failed)\\b(.*)$", RegexOption.IGNORE_CASE)

    /** The assistant's report: the table it is asked for, or plain lines like "02: skipped - reason". Later rows win. */
    fun parseReplyTodo(text: String?): Map<Int, Report> {
        val out = LinkedHashMap<Int, Report>()
        for (line in (text ?: "").lines()) {
            if ('|' in line) {
                val cells = line.trim().trim('|').split("|").map { it.pyStrip() }
                val n = cells.firstOrNull { NUMBER.matches(it) } ?: continue
                val status = cells.firstOrNull { it.lowercase() in STATUSES }?.lowercase() ?: continue
                val reply = cells.firstOrNull { it.trim('`').lowercase().endsWith(".md") }?.trim('`') ?: ""
                val rest = cells.filter { it.isNotEmpty() && it != n && it.lowercase() != status && it.trim('`') != reply }
                out.remove(n.toInt())
                out[n.toInt()] = Report(status, reply, rest.lastOrNull() ?: "")
                continue
            }
            val m = LIST_ROW.find(line.removeSuffix("\r")) ?: continue
            val rest = m.groupValues[3]
            val reply = rest.split(Regex("\\s+")).map { it.trim('`', ',', '.', ';', '(', ')') }
                .firstOrNull { it.lowercase().endsWith(".md") } ?: ""
            val reason = rest.replace(reply, "").trim { it in " -:;,.`()" }
            out.remove(m.groupValues[1].toInt())
            out[m.groupValues[1].toInt()] = Report(m.groupValues[2].lowercase(), reply, reason)
        }
        return out
    }

    data class Item(val n: Int, val name: String)
    data class ReplyFile(val name: String, val modified: String?)
    data class Decision(val n: Int, val action: String, val reply: Int?, val delete: List<Int>, val reason: String)
    data class Plan(val items: List<Decision>, val complete: Boolean)

    /** What to do with one batch (aiqueue.plan_import). Indexes in reply/delete point into [replies]. */
    fun planImport(items: List<Item>, requestsPresent: Set<String>, replies: List<ReplyFile>, replyTodo: String?): Plan {
        val report = if (replyTodo != null) parseReplyTodo(replyTodo) else emptyMap()
        val out = items.map { (n, name) ->
            if (name !in requestsPresent) return@map Decision(n, "gone", null, emptyList(), "")
            val entry = report[n]
            val names = setOf(name) + (if (entry != null && entry.reply.isNotEmpty()) setOf(entry.reply) else emptySet())
            val found = replies.indices.filter { replies[it].name in names }
                .sortedWith(compareByDescending<Int> { replies[it].modified ?: "" }.thenByDescending { it })
            when {
                entry != null && entry.status in listOf("skipped", "failed") ->
                    Decision(n, entry.status, null, emptyList(), entry.reason.ifEmpty { "No reason given." })
                found.isNotEmpty() -> Decision(n, "import", found[0], found.sorted(), "")
                entry != null && entry.status == "done" ->
                    Decision(n, "missing", null, emptyList(), "The report says done, but the reply file is not in replies/ yet.")
                else -> Decision(n, "waiting", null, emptyList(), "")
            }
        }
        return Plan(out, out.all { it.action == "import" || it.action == "gone" })
    }

    /** The reply report an assistant writes; used in tests and help text. */
    fun renderReplyTodo(batch: String, rows: List<Report>, numbers: List<Int>): String {
        val lines = mutableListOf("# Replies for batch $batch", "", "| Item | Status | Reply file | Reason |", "|---|---|---|---|")
        rows.zip(numbers).forEach { (r, n) -> lines += "| ${"%02d".format(n)} | ${r.status} | ${r.reply} | ${r.reason} |" }
        return lines.joinToString("\n") + "\n"
    }
}
