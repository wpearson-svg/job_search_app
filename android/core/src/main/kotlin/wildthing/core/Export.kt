package wildthing.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.intOrNull

/**
 * The export file both versions read and write (docs/formats.md, "wildthing-export" version 1).
 * API keys are never part of it.
 */
object ExportFormat {
    const val FORMAT = "wildthing-export"
    const val VERSION = 1

    val json = Json { ignoreUnknownKeys = true; explicitNulls = true; encodeDefaults = true; prettyPrint = true; prettyPrintIndent = " " }

    /** A plain reason the file cannot be imported, or null when it can. */
    fun check(raw: String): String? {
        val obj = runCatching { json.parseToJsonElement(raw).jsonObject }.getOrNull()
            ?: return "That is not a WildThing export file."
        if (obj["format"]?.jsonPrimitive?.content != FORMAT) return "That is not a WildThing export file."
        val v = obj["version"]?.jsonPrimitive?.intOrNull ?: return "That is not a WildThing export file."
        if (v > VERSION) return "That file comes from a newer version of WildThing. Update this app first."
        return null
    }

    fun read(raw: String): ExportFile {
        check(raw)?.let { throw IllegalArgumentException(it) }
        return json.decodeFromString(ExportFile.serializer(), raw)
    }

    fun write(file: ExportFile): String = json.encodeToString(ExportFile.serializer(), file)
}

@Serializable
data class ExportFile(
    val format: String = ExportFormat.FORMAT,
    val version: Int = ExportFormat.VERSION,
    @SerialName("exported_at") val exportedAt: String = "",
    val app: String = "android",
    /** Only the keys listed in docs/formats.md; kept as JSON so a field added later on one side survives. */
    val settings: JsonObject = JsonObject(emptyMap()),
    val resume: ExportResume? = null,
    val instructions: String? = null,
    val extras: List<ExportExtra> = emptyList(),
    val profiles: List<ExportProfile> = emptyList(),
    val jobs: List<ExportJob> = emptyList(),
    val events: List<ExportEvent> = emptyList(),
    val outputs: List<ExportOutput> = emptyList(),
    @SerialName("gap_plans") val gapPlans: List<ExportGapPlan> = emptyList(),
    /** Companies you avoid. Added within version 1 (older readers ignore it). */
    val avoided: List<ExportAvoided> = emptyList(),
)

@Serializable data class ExportAvoided(val company: String, val reason: String = "")

@Serializable data class ExportResume(val filename: String, val base64: String)

@Serializable data class ExportExtra(val term: String, @SerialName("added_at") val addedAt: String = "")

@Serializable
data class ExportProfile(
    val id: Long, val name: String, val keywords: String = "", val titles: String = "", val location: String = "",
)

@Serializable
data class ExportLink(val source: String, val url: String)

@Serializable
data class ExportJob(
    val id: Long,
    val source: String,
    @SerialName("ext_id") val extId: String,
    val title: String = "",
    val company: String = "",
    val location: String = "",
    val url: String = "",
    val description: String = "",
    val posted: String = "",
    val pasted: Boolean = false,
    val status: String = "new",
    val score: Int = 0,
    val matched: List<String> = emptyList(),
    /** [term, weight] pairs, written as two-element arrays. */
    val gaps: List<List<JsonElement>> = emptyList(),
    val flags: List<String> = emptyList(),
    @SerialName("title_match") val titleMatch: Boolean = false,
    @SerialName("added_at") val addedAt: String = "",
    @SerialName("applied_on") val appliedOn: String? = null,
    val notes: String = "",
    @SerialName("status_updated") val statusUpdated: String? = null,
    @SerialName("profile_ids") val profileIds: List<Long> = emptyList(),
    val links: List<ExportLink> = emptyList(),
    /** Tag keys (Marks.TAGS, or "c:" + your own words). */
    val tags: List<String> = emptyList(),
) {
    fun gapPairs(): List<Pair<String, Int>> = gaps.mapNotNull {
        if (it.size < 2) null else it[0].jsonPrimitive.content to (it[1].jsonPrimitive.intOrNull ?: 1)
    }
}

@Serializable
data class ExportEvent(
    val id: Long,
    @SerialName("job_id") val jobId: Long,
    val kind: String,
    /** Wall-clock time where the event happens, YYYY-MM-DDTHH:MM. */
    @SerialName("starts_at") val startsAt: String,
    val minutes: Int = 60,
    val place: String = "",
    val notes: String = "",
    /** IANA zone name; null means "the zone of the device reading the file". */
    @SerialName("time_zone") val timeZone: String? = null,
)

@Serializable
data class ExportOutput(
    @SerialName("job_id") val jobId: Long,
    val kind: String,
    val content: String,
    val warnings: List<String> = emptyList(),
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class ExportGapPlan(val scope: String, val content: String, @SerialName("created_at") val createdAt: String = "")
