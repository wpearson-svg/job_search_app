package wildthing.core

/**
 * The shared postings database, WildThing/user/wildthing.db in Google Drive (shared_db.py; docs/formats.md section 7).
 * This is the merge rule, the same as the desktop's; shared_tests/shared_db.json holds the cases both run.
 * Reading and writing the SQLite files is the app's part (it needs Android's SQLite).
 */
object SharedDb {
    const val FILE = "wildthing.db"
    const val FORMAT = "wildthing-shared-db"
    const val VERSION = 2                 // 2 added avoided companies and tags; a version 1 file reads as having none
    const val COMBINE = "\n\n--- Also written on another device ---\n"

    /** The shared file's tables, exactly as the desktop writes them. */
    val SCHEMA = listOf(
        "CREATE TABLE info(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "CREATE TABLE postings(uid TEXT PRIMARY KEY, source TEXT NOT NULL, ext_id TEXT NOT NULL, title TEXT NOT NULL, " +
            "company TEXT NOT NULL, location TEXT NOT NULL, url TEXT NOT NULL, description TEXT NOT NULL, posted TEXT NOT NULL, " +
            "pasted INTEGER NOT NULL, added_at TEXT NOT NULL, status TEXT NOT NULL, status_at TEXT NOT NULL, " +
            "applied_on TEXT NOT NULL, notes TEXT NOT NULL)",
        "CREATE TABLE links(posting TEXT NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL, PRIMARY KEY(posting, url))",
        "CREATE TABLE events(uid TEXT PRIMARY KEY, posting TEXT NOT NULL, kind TEXT NOT NULL, starts_at TEXT NOT NULL, " +
            "minutes INTEGER NOT NULL, place TEXT NOT NULL, notes TEXT NOT NULL, time_zone TEXT NOT NULL, changed_at TEXT NOT NULL)",
        "CREATE TABLE outputs(posting TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, warnings_json TEXT NOT NULL, " +
            "created_at TEXT NOT NULL, PRIMARY KEY(posting, kind))",
        "CREATE TABLE gap_plans(uid TEXT PRIMARY KEY, scope TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)",
        "CREATE TABLE tombstones(uid TEXT PRIMARY KEY, kind TEXT NOT NULL, at TEXT NOT NULL)",
        "CREATE TABLE avoided(key TEXT PRIMARY KEY, company TEXT NOT NULL, reason TEXT NOT NULL, active INTEGER NOT NULL, " +
            "changed_at TEXT NOT NULL)",
        "CREATE TABLE tags(posting TEXT NOT NULL, tag TEXT NOT NULL, active INTEGER NOT NULL, changed_at TEXT NOT NULL, " +
            "PRIMARY KEY(posting, tag))",
    )

    data class Link(val source: String, val url: String)
    data class Posting(
        val source: String, val extId: String, val title: String, val company: String, val location: String, val url: String,
        val description: String, val posted: String, val pasted: Int, val addedAt: String, val status: String,
        val statusAt: String, val appliedOn: String, val notes: String, val links: List<Link>,
    )
    data class Event(val posting: String, val kind: String, val startsAt: String, val minutes: Int, val place: String,
                     val notes: String, val timeZone: String, val changedAt: String)
    data class Output(val posting: String, val kind: String, val content: String, val warningsJson: String, val createdAt: String) {
        val key get() = "$posting|$kind"
    }
    data class GapPlan(val scope: String, val content: String, val createdAt: String)
    data class Tomb(val kind: String, val at: String)
    /** A company you avoid, keyed by Dedupe.norm(company). A removal keeps the row with active 0, so it syncs too. */
    data class Avoid(val company: String, val reason: String, val active: Int, val changedAt: String)
    data class Tag(val posting: String, val tag: String, val active: Int, val changedAt: String) {
        val key get() = "$posting|$tag"
    }
    data class Snapshot(
        val postings: Map<String, Posting> = emptyMap(), val events: Map<String, Event> = emptyMap(),
        val outputs: Map<String, Output> = emptyMap(), val gapPlans: Map<String, GapPlan> = emptyMap(),
        val tombstones: Map<String, Tomb> = emptyMap(), val avoided: Map<String, Avoid> = emptyMap(),
        val tags: Map<String, Tag> = emptyMap(),
    )
    data class Result(val merged: Snapshot, val rename: Map<String, String>)

    /** The local posting (uid) that is the same job as remote posting p: same source and id, else a shared link,
     *  else the same title and company in the same place. */
    private fun match(p: Posting, candidates: Map<String, Posting>): String? {
        val uids = candidates.keys.sorted()
        uids.firstOrNull { candidates.getValue(it).let { c -> c.source == p.source && c.extId == p.extId } }?.let { return it }
        val urls = (listOf(p.url) + p.links.map { it.url }).filter { it.isNotEmpty() }.toSet()
        uids.firstOrNull { u -> candidates.getValue(u).let { c -> (listOf(c.url) + c.links.map { it.url }).any { it.isNotEmpty() && it in urls } } }
            ?.let { return it }
        val key = Dedupe.dupKey(p.title, p.company)
        return uids.firstOrNull { u ->
            candidates.getValue(u).let { c -> key.isNotEmpty() && Dedupe.dupKey(c.title, c.company) == key && Dedupe.samePlace(c.location, p.location) }
        }
    }

    fun mergeNotes(here: String, there: String, base: String?): String = when {
        here == there -> here
        base != null && here == base -> there
        base != null && there == base -> here
        here.isBlank() -> there
        there.isBlank() -> here
        else -> here.trimEnd() + COMBINE + there.trim()
    }

    private fun mergePosting(h: Posting, t: Posting, baseNotes: String?): Posting {
        val newer = if (compareValuesBy(t, h, { it.statusAt }, { it.status }) > 0) t else h
        val links = (t.links.associateBy { it.url } + h.links.associateBy { it.url }).toSortedMap().values.toList()
        val added = listOf(h.addedAt, t.addedAt).filter { it.isNotEmpty() }.minOrNull() ?: ""
        return h.copy(
            source = h.source.ifEmpty { t.source }, extId = h.extId.ifEmpty { t.extId },
            title = h.title.ifEmpty { t.title }, company = h.company.ifEmpty { t.company },
            location = h.location.ifEmpty { t.location }, url = h.url.ifEmpty { t.url },
            description = h.description.ifEmpty { t.description }, posted = h.posted.ifEmpty { t.posted },
            pasted = maxOf(h.pasted, t.pasted), addedAt = added,
            status = newer.status, statusAt = newer.statusAt, appliedOn = newer.appliedOn,
            notes = mergeNotes(h.notes, t.notes, baseNotes), links = links,
        )
    }

    /** Of two copies, the one changed last; at the same moment, on beats off (shared_db._newer). */
    private fun newer(h: Avoid, t: Avoid) =
        if (compareValuesBy(t, h, { it.changedAt }, { it.active }, { it.reason }, { it.company }) > 0) t else h
    private fun newer(h: Tag, t: Tag) = if (compareValuesBy(t, h, { it.changedAt }, { it.active }) > 0) t else h

    private fun renamed(s: Snapshot, rename: Map<String, String>): Snapshot {
        if (rename.isEmpty()) return s
        fun r(u: String) = rename[u] ?: u
        val tags = linkedMapOf<String, Tag>()
        for (g in s.tags.values.map { it.copy(posting = r(it.posting)) }) tags[g.key] = tags[g.key]?.let { newer(it, g) } ?: g
        return s.copy(
            postings = s.postings.mapKeys { r(it.key) },
            events = s.events.mapValues { it.value.copy(posting = r(it.value.posting)) },
            outputs = s.outputs.values.map { it.copy(posting = r(it.posting)) }.associateBy { it.key },
            tags = tags,
        )
    }

    /** Merges this device's snapshot with the shared file's. base: each posting's notes at this device's last sync. */
    fun merge(hereIn: Snapshot, there: Snapshot, base: Map<String, String>): Result {
        val candidates = hereIn.postings.filterKeys { it !in there.postings }.toMutableMap()
        val rename = linkedMapOf<String, String>()
        for (uid in there.postings.keys.filter { it !in hereIn.postings }.sorted()) {
            val found = match(there.postings.getValue(uid), candidates) ?: continue
            rename[found] = uid
            candidates.remove(found)
        }
        val here = renamed(hereIn, rename)

        val tomb = there.tombstones.toMutableMap()
        for ((u, t) in here.tombstones) if (u !in tomb || t.at > tomb.getValue(u).at) tomb[u] = t

        val postings = linkedMapOf<String, Posting>()
        for (u in (here.postings.keys + there.postings.keys).sorted()) {
            if (u in tomb) continue
            val h = here.postings[u]; val t = there.postings[u]
            postings[u] = if (h != null && t != null) mergePosting(h, t, base[u]) else (h ?: t)!!
        }
        val events = linkedMapOf<String, Event>()
        for (u in (here.events.keys + there.events.keys).sorted()) {
            val h = here.events[u]; val t = there.events[u]
            val e = if (h != null && t != null) (if (t.changedAt > h.changedAt) t else h) else (h ?: t)!!
            if (u !in tomb && e.posting in postings) events[u] = e
        }
        val outputs = linkedMapOf<String, Output>()
        for (k in (here.outputs.keys + there.outputs.keys).sorted()) {
            val h = here.outputs[k]; val t = there.outputs[k]
            val o = if (h != null && t != null) (if (t.createdAt > h.createdAt) t else h) else (h ?: t)!!
            if (o.posting in postings) outputs[k] = o
        }
        val plans = linkedMapOf<String, GapPlan>()
        for (u in (here.gapPlans.keys + there.gapPlans.keys).sorted()) if (u !in tomb) plans[u] = here.gapPlans[u] ?: there.gapPlans.getValue(u)
        val avoided = linkedMapOf<String, Avoid>()
        for (k in (here.avoided.keys + there.avoided.keys).sorted()) {
            val h = here.avoided[k]; val t = there.avoided[k]
            avoided[k] = if (h != null && t != null) newer(h, t) else (h ?: t)!!
        }
        val tags = linkedMapOf<String, Tag>()
        for (k in (here.tags.keys + there.tags.keys).sorted()) {
            val h = here.tags[k]; val t = there.tags[k]
            val g = if (h != null && t != null) newer(h, t) else (h ?: t)!!
            if (g.posting in postings) tags[k] = g
        }
        return Result(Snapshot(postings, events, outputs, plans, tomb, avoided, tags), rename)
    }
}
