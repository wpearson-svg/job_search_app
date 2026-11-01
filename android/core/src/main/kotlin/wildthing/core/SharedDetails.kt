package wildthing.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import java.security.MessageDigest

/**
 * Details shared between phone and PC through WildThing/user/ (shared_details.py; docs/formats.md, section 6;
 * shared_tests/shared_details.json). Each file X has X.meta.json beside it; both changed since the last sync means ask.
 */
object SharedDetails {
    const val FORMAT_SEARCH = "wildthing-search"
    const val FORMAT_SKILLS = "wildthing-confirmed-skills"
    val FILES = listOf("resume", "search.json", "instructions.md", "confirmed_skills.json", "career.json")
    val SEARCH_KEYS = listOf("target_titles", "search_keywords", "locations")
    val RESUME_EXTS = listOf(".docx", ".md", ".txt")

    fun sha256(data: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }

    fun metaName(key: String) = if (key == "resume") "resume.meta.json" else "$key.meta.json"

    data class SharedProfile(val name: String, val keywords: String, val titles: String, val location: String)

    fun searchDoc(targetTitles: List<String>, keywords: List<String>, locations: List<String>, profiles: List<SharedProfile>): ByteArray {
        fun strs(v: List<String>) = JsonArray(v.map { JsonPrimitive(it) })
        val doc = JsonObject(mapOf(
            "format" to JsonPrimitive(FORMAT_SEARCH), "version" to JsonPrimitive(1),
            "target_titles" to strs(targetTitles), "search_keywords" to strs(keywords), "locations" to strs(locations),
            "profiles" to JsonArray(profiles.sortedBy { it.name.lowercase() }.map {
                JsonObject(mapOf("name" to JsonPrimitive(it.name), "keywords" to JsonPrimitive(it.keywords),
                    "titles" to JsonPrimitive(it.titles), "location" to JsonPrimitive(it.location)))
            }),
        ))
        return (PyJson.dumps(doc) + "\n").toByteArray(Charsets.UTF_8)
    }

    fun skillsDoc(terms: Collection<String>): ByteArray {
        val doc = JsonObject(mapOf("format" to JsonPrimitive(FORMAT_SKILLS), "version" to JsonPrimitive(1),
            "skills" to JsonArray(terms.toSortedSet().map { JsonPrimitive(it) })))
        return (PyJson.dumps(doc) + "\n").toByteArray(Charsets.UTF_8)
    }

    /** The parsed document, or throws IllegalArgumentException("not a WildThing file"). */
    fun parseDoc(data: ByteArray, format: String): JsonObject {
        val doc = runCatching { Json.parseToJsonElement(data.toString(Charsets.UTF_8)).jsonObject }.getOrNull()
        require(doc != null && (doc["format"] as? JsonPrimitive)?.content == format) { "not a WildThing file" }
        return doc
    }

    fun strings(doc: JsonObject, key: String): List<String> =
        (doc[key] as? JsonArray)?.map { it.jsonPrimitive.content } ?: emptyList()

    fun profiles(doc: JsonObject): List<SharedProfile> = (doc["profiles"] as? JsonArray)?.map { el ->
        val o = el.jsonObject
        fun s(k: String) = (o[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content ?: ""
        SharedProfile(s("name"), s("keywords"), s("titles"), s("location"))
    } ?: emptyList()

    data class Meta(val file: String, val version: Long, val changedAt: String, val device: String, val sha256: String) {
        fun toJson(): String = PyJson.dumps(JsonObject(mapOf("file" to JsonPrimitive(file), "version" to JsonPrimitive(version),
            "changed_at" to JsonPrimitive(changedAt), "device" to JsonPrimitive(device), "sha256" to JsonPrimitive(sha256))))

        companion object {
            fun parse(text: String): Meta? = runCatching {
                val o = Json.parseToJsonElement(text).jsonObject
                fun s(k: String) = (o[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content ?: ""
                Meta(s("file"), (o["version"] as? JsonPrimitive)?.longOrNull ?: 0, s("changed_at"), s("device"), s("sha256"))
            }.getOrNull()?.takeIf { it.file.isNotEmpty() && it.sha256.isNotEmpty() }
        }
    }

    /** What this device recorded at its last sync of a file: its own copy's hash and the folder copy's hash. */
    data class Base(val local: String?, val remote: String, val version: Long = 0)

    /** "none", "push", "pull", "same" or "conflict" (shared_details.decide). */
    fun decide(localSha: String?, remote: Meta?, base: Base?): String {
        if (localSha == null && remote == null) return "none"
        if (remote == null) return "push"
        if (localSha == null) return "pull"
        if (base == null) return if (localSha == remote.sha256) "same" else "conflict"
        val localChanged = localSha != base.local
        val remoteChanged = remote.sha256 != base.remote
        return when {
            localChanged && remoteChanged -> if (localSha == remote.sha256) "same" else "conflict"
            remoteChanged -> "pull"
            localChanged -> "push"
            else -> "same"
        }
    }

    fun nextVersion(remote: Meta?, base: Base?) = maxOf(remote?.version ?: 0, base?.version ?: 0) + 1
}

/** json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True), so both versions write the same bytes. */
object PyJson {
    fun dumps(e: JsonElement, depth: Int = 0): String = when (e) {
        is JsonObject -> if (e.isEmpty()) "{}" else e.keys.sorted().joinToString(",\n", "{\n", "\n" + " ".repeat(depth) + "}") {
            " ".repeat(depth + 1) + quote(it) + ": " + dumps(e.getValue(it), depth + 1)
        }
        is JsonArray -> if (e.isEmpty()) "[]" else e.joinToString(",\n", "[\n", "\n" + " ".repeat(depth) + "]") {
            " ".repeat(depth + 1) + dumps(it, depth + 1)
        }
        is JsonNull -> "null"
        is JsonPrimitive -> if (e.isString) quote(e.content) else e.content
    }

    fun quote(s: String): String = buildString {
        append('"')
        for (c in s) when (c) {
            '"' -> append("\\\""); '\\' -> append("\\\\"); '\n' -> append("\\n"); '\r' -> append("\\r")
            '\t' -> append("\\t"); '\b' -> append("\\b"); '\u000c' -> append("\\f")
            else -> if (c < ' ') append("\\u%04x".format(c.code)) else append(c)
        }
        append('"')
    }
}
