package wildthing.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLEncoder

/**
 * Job sources that allow programmatic use: open APIs and the public boards companies publish themselves.
 * A port of sources.py without JobSpy and the LinkedIn npm bridge, which do not belong in a phone app
 * (on Android, postings from LinkedIn or Indeed come in through the share menu instead).
 * The parse functions take already downloaded data, so they are tested against shared_tests/sources.json.
 */
data class Posting(
    val source: String, val extId: String, val title: String, val company: String, val location: String,
    val url: String, val description: String, val posted: String,
)

/** The settings a fetch needs: one profile's keywords, titles and place laid over the user's settings. */
data class FetchConfig(
    val targetTitles: List<String>,
    val searchKeywords: List<String>,
    val greenhouseBoards: List<String> = emptyList(),
    val leverCompanies: List<String> = emptyList(),
    val adzunaWhere: String = "",
    val adzunaCountry: String = "us",
    val usajobsLocation: String = "",
    val maxJobsPerSource: Int = 60,
)

data class FetchKeys(
    val adzunaAppId: String = "", val adzunaAppKey: String = "",
    val usajobsKey: String = "", val usajobsEmail: String = "",
)

data class SourceReport(val name: String, val count: Int, val error: String)

/** Fetches a URL and returns the body. Swappable so tests never touch the network. */
fun interface Http {
    fun get(url: String, headers: Map<String, String>): String
}

object Sources {
    const val UA = "WildThing-android/1.0 (personal use)"
    private const val TIMEOUT_MS = 25_000

    val defaultHttp = Http { url, headers ->
        val c = URI(url).toURL().openConnection() as HttpURLConnection
        c.connectTimeout = TIMEOUT_MS
        c.readTimeout = TIMEOUT_MS
        c.setRequestProperty("User-Agent", UA)
        headers.forEach { (k, v) -> c.setRequestProperty(k, v) }
        try {
            val code = c.responseCode
            if (code !in 200..299) throw RuntimeException("HTTP $code from ${c.url.host}")
            c.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }
        } finally {
            c.disconnect()
        }
    }

    fun titleWanted(title: String?, targetTitles: List<String>): Boolean {
        val t = (title ?: "").lowercase()
        return targetTitles.any { it.lowercase() in t }
    }

    // ---- small JSON helpers that read like Python's dict.get -------------------------------------------
    private fun JsonElement?.obj(): JsonObject? = this as? JsonObject
    private fun JsonElement?.arr(): List<JsonElement> = (this as? JsonArray) ?: emptyList()

    /** dict.get(key, "") for text fields: missing or null gives "". */
    private fun JsonObject?.s(key: String): String {
        val v = this?.get(key)
        return if (v is JsonPrimitive && v !is JsonNull) v.content else ""
    }

    /** str(dict.get(key)) for ids: Python writes "None" when the id is missing. */
    private fun JsonObject.id(key: String): String {
        val v = get(key)
        return if (v == null || v is JsonNull) "None" else if (v is JsonPrimitive) v.content else v.toString()
    }

    private fun String.or(other: String) = ifEmpty { other }

    // ---- RemoteOK (no key) ---------------------------------------------------------------------------------
    fun parseRemoteOk(data: JsonElement): List<Posting> = data.arr().mapNotNull { el ->
        val j = el.obj() ?: return@mapNotNull null
        if ("position" !in j) return@mapNotNull null          // the first element is a legal notice
        Posting("remoteok", j.id("id"), j.s("position"), j.s("company"), j.s("location").or("Remote"),
            j.s("url"), Html.strip(j.s("description")), j.s("date"))
    }

    // ---- Remotive (no key) ---------------------------------------------------------------------------------
    fun parseRemotive(data: JsonElement): List<Posting> = data.obj()?.get("jobs").arr().mapNotNull { el ->
        val j = el.obj() ?: return@mapNotNull null
        Posting("remotive", j.id("id"), j.s("title"), j.s("company_name"),
            j.s("candidate_required_location").or("Remote"), j.s("url"), Html.strip(j.s("description")),
            j.s("publication_date"))
    }

    // ---- Greenhouse boards (no key; the user lists the company board names) --------------------------------
    fun parseGreenhouse(data: JsonElement, board: String): List<Posting> = data.obj()?.get("jobs").arr().mapNotNull { el ->
        val j = el.obj() ?: return@mapNotNull null
        Posting("greenhouse:$board", j.id("id"), j.s("title"), board, j["location"].obj().s("name"),
            j.s("absolute_url"), Html.strip(j.s("content")), j.s("updated_at"))
    }

    // ---- Lever postings (no key; the user lists the company names) -----------------------------------------
    fun parseLever(data: JsonElement, company: String): List<Posting> = data.arr().mapNotNull { el ->
        val j = el.obj() ?: return@mapNotNull null
        val extra = j["lists"].arr().joinToString("\n") { x -> Html.strip(x.obj().s("text") + "\n" + x.obj().s("content")) }
        Posting("lever:$company", j.id("id"), j.s("text"), company, j["categories"].obj().s("location"),
            j.s("hostedUrl"), (j.s("descriptionPlain") + "\n" + extra).pyStrip(), j.s("createdAt"))
    }

    // ---- Adzuna (free key). The API gives a short snippet, not the full description. ----------------------
    fun parseAdzuna(data: JsonElement): List<Posting> = data.obj()?.get("results").arr().mapNotNull { el ->
        val j = el.obj() ?: return@mapNotNull null
        Posting("adzuna", j.id("id"), j.s("title"), j["company"].obj().s("display_name"),
            j["location"].obj().s("display_name"), j.s("redirect_url"), Html.strip(j.s("description")), j.s("created"))
    }

    // ---- USAJOBS (free key) --------------------------------------------------------------------------------
    fun parseUsajobs(data: JsonElement): List<Posting> =
        data.obj()?.get("SearchResult").obj()?.get("SearchResultItems").arr().mapNotNull { el ->
            val item = el.obj() ?: return@mapNotNull null
            val d = item["MatchedObjectDescriptor"].obj()
            val det = d?.get("UserArea").obj()?.get("Details").obj()
            val text = (det.s("JobSummary") + "\n" + d.s("QualificationSummary")).pyStrip()
            Posting("usajobs", item.id("MatchedObjectId"), d.s("PositionTitle"), d.s("OrganizationName"),
                d.s("PositionLocationDisplay"), d.s("PositionURI"), Html.strip(text), d.s("PublicationStartDate"))
        }

    // ---- Fetching ------------------------------------------------------------------------------------------
    private fun q(v: String) = URLEncoder.encode(v, "UTF-8")
    private fun json(http: Http, url: String, headers: Map<String, String> = emptyMap()) =
        Json.parseToJsonElement(http.get(url, headers))

    fun fetchRemoteOk(cfg: FetchConfig, http: Http) =
        parseRemoteOk(json(http, "https://remoteok.com/api")).filter { titleWanted(it.title, cfg.targetTitles) }

    fun fetchRemotive(cfg: FetchConfig, http: Http): List<Posting> {
        val found = LinkedHashMap<String, Posting>()
        for (kw in cfg.searchKeywords) {
            parseRemotive(json(http, "https://remotive.com/api/remote-jobs?search=${q(kw)}")).forEach { found[it.extId] = it }
        }
        return found.values.toList()
    }

    fun fetchGreenhouse(cfg: FetchConfig, http: Http) = cfg.greenhouseBoards.flatMap { board ->
        parseGreenhouse(json(http, "https://boards-api.greenhouse.io/v1/boards/${q(board)}/jobs?content=true"), board)
            .filter { titleWanted(it.title, cfg.targetTitles) }
    }

    fun fetchLever(cfg: FetchConfig, http: Http) = cfg.leverCompanies.flatMap { company ->
        parseLever(json(http, "https://api.lever.co/v0/postings/${q(company)}?mode=json"), company)
            .filter { titleWanted(it.title, cfg.targetTitles) }
    }

    fun fetchAdzuna(cfg: FetchConfig, keys: FetchKeys, http: Http): List<Posting> {
        if (keys.adzunaAppId.isEmpty() || keys.adzunaAppKey.isEmpty()) throw RuntimeException("no Adzuna key in Settings (skipped)")
        val found = LinkedHashMap<String, Posting>()
        for (kw in cfg.searchKeywords) {
            val url = "https://api.adzuna.com/v1/api/jobs/${q(cfg.adzunaCountry.ifEmpty { "us" })}/search/1?app_id=${q(keys.adzunaAppId)}" +
                "&app_key=${q(keys.adzunaAppKey)}&what=${q(kw)}&where=${q(cfg.adzunaWhere)}&results_per_page=30&content-type=application/json"
            parseAdzuna(json(http, url)).forEach { found[it.extId] = it }
        }
        return found.values.toList()
    }

    fun fetchUsajobs(cfg: FetchConfig, keys: FetchKeys, http: Http): List<Posting> {
        if (keys.usajobsKey.isEmpty() || keys.usajobsEmail.isEmpty()) throw RuntimeException("no USAJOBS key in Settings (skipped)")
        val found = LinkedHashMap<String, Posting>()
        for (kw in cfg.searchKeywords) {
            val url = "https://data.usajobs.gov/api/search?Keyword=${q(kw)}&LocationName=${q(cfg.usajobsLocation)}&ResultsPerPage=25"
            val headers = mapOf("Host" to "data.usajobs.gov", "User-Agent" to keys.usajobsEmail, "Authorization-Key" to keys.usajobsKey)
            parseUsajobs(json(http, url, headers)).forEach { found[it.extId] = it }
        }
        return found.values.toList()
    }

    /** Runs every source. One failing never stops the others; each one's count or error is reported. */
    fun fetchAll(cfg: FetchConfig, keys: FetchKeys, http: Http = defaultHttp): Pair<List<Posting>, List<SourceReport>> {
        val runners = listOf<Pair<String, () -> List<Posting>>>(
            "RemoteOK" to { fetchRemoteOk(cfg, http) },
            "Remotive" to { fetchRemotive(cfg, http) },
            "Greenhouse boards" to { fetchGreenhouse(cfg, http) },
            "Lever companies" to { fetchLever(cfg, http) },
            "Adzuna" to { fetchAdzuna(cfg, keys, http) },
            "USAJOBS" to { fetchUsajobs(cfg, keys, http) },
        )
        val jobs = mutableListOf<Posting>()
        val report = mutableListOf<SourceReport>()
        for ((name, run) in runners) {
            try {
                val got = run().take(cfg.maxJobsPerSource)
                jobs += got
                report += SourceReport(name, got.size, "")
            } catch (e: Exception) {
                report += SourceReport(name, 0, (e.message ?: e.javaClass.simpleName).take(160))
            }
        }
        return jobs to report
    }
}
