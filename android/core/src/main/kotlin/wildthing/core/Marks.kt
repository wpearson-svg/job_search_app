package wildthing.core

/**
 * Tags say something about a posting that its status does not (db.TAGS on the desktop). The keys are fixed so that,
 * one day, the same tag from many people can be counted together; a tag you type yourself is kept as "c:" + your words.
 */
object Marks {
    data class TagDef(val key: String, val label: String, val about: String)

    val TAGS = listOf(
        TagDef("ai_interview", "AI interview", "Uses AI to screen or interview applicants"),
        TagDef("scam", "Possible scam", "Signs of a fake job or a scam"),
        TagDef("ghost", "Ghost posting", "Reposted again and again, never seems to be filled"),
        TagDef("no_pay", "No pay listed", "The posting gives no pay or pay range"),
        TagDef("agency", "Agency or recruiter", "Posted by a staffing agency or outside recruiter"),
        TagDef("unpaid_test", "Unpaid test task", "Asks for unpaid work as part of applying"),
    )
    val LABEL = TAGS.associate { it.key to it.label }
    const val CUSTOM = "c:"

    fun label(tag: String) = LABEL[tag] ?: if (tag.startsWith(CUSTOM)) tag.removePrefix(CUSTOM) else tag

    /** The key for a tag you type yourself ("" when there is nothing to keep); typing a built-in tag's name gives that tag. */
    fun customTag(text: String): String {
        val t = text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ").take(40)
        if (t.isEmpty()) return ""
        return TAGS.firstOrNull { it.label.equals(t, ignoreCase = true) }?.key ?: (CUSTOM + t)
    }

    /** The key an avoided company is kept under: its name without Inc, LLC and the like. */
    fun companyKey(company: String?) = Dedupe.norm(company)
}
