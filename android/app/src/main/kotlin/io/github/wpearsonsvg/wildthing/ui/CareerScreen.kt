package io.github.wpearsonsvg.wildthing.ui

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import wildthing.core.Career
import wildthing.core.Docx
import wildthing.core.Matcher

/** The career file (the desktop's Career page): see it, build or rebuild it with your AI, review a new one. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CareerScreen(state: AppState, back: () -> Unit) {
    val store = state.store
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val google = rememberGoogle(state)
    val v = state.version
    val cur = remember(v) { store.career() }
    val pending = remember(v) { store.careerPending() }
    var draft by remember(v) { mutableStateOf(store.careerRequest()) }
    var sources by remember { mutableStateOf(listOf<Pair<String, String>>()) }
    var typed by remember { mutableStateOf("") }
    var includeCurrent by remember { mutableStateOf(true) }
    var pasted by remember { mutableStateOf("") }
    var problems by remember { mutableStateOf<List<String>>(emptyList()) }
    fun say(msg: String) = scope.launch { state.snackbar.showSnackbar(msg) }

    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        scope.launch {
            val read = withContext(Dispatchers.IO) { uris.map { readSource(context, it) } }
            read.filter { it.second == null }.forEach { (name, _) -> say("$name was left out: use a Word, Markdown or text file under 3 MB.") }
            sources = sources + read.mapNotNull { (name, text) -> text?.let { name to it } }
        }
    }
    fun take(text: String, reply: String?) {
        problems = store.takeCareerReply(text, reply)
        if (problems.isEmpty()) { pasted = ""; state.changed() }
    }

    Screen("Career file", back) { pad ->
        ScrollBody(pad) {
            Muted("Everything true about you in one file. Your AI builds it from your own documents; after that only WildThing changes it. Your master resume stays the example of format and tone.")

            if (pending != null) {
                val next = remember(pending, cur) { Career.replace(cur, pending.file, pending.at) }
                SectionTitle(if (cur == null) "Review your new career file" else "Review your rebuilt career file")
                Muted("Check it is all true. Nothing is kept until you accept it.")
                if (cur != null) {
                    val ch = remember(next) { Career.changes(cur, next) }
                    if (ch.isEmpty()) Muted("No roles, skills, certifications, education or projects were added or removed.")
                    ch.forEach { (section, c) ->
                        Text(section.replaceFirstChar { it.uppercase() }, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
                        if (c.added.isNotEmpty()) Tags(c.added.map { "+ $it" })
                        if (c.removed.isNotEmpty()) Tags(c.removed.map { "- $it" }, MaterialTheme.colorScheme.errorContainer, MaterialTheme.colorScheme.onErrorContainer)
                    }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
                    Button(onClick = {
                        val p = runCatching { store.acceptCareer() }.getOrElse { say("That career file was not used: ${it.message}"); null }
                        if (p != null) {
                            state.changed()
                            scope.launch {
                                if (p.reply != null && google.linked) google.drive(quiet = true) { it.removeCareer(p.reply) }
                                if (google.linked) google.drive(quiet = true) { it.sync() }
                                state.snackbar.showSnackbar("Career file saved. Every posting was re-scored against it.")
                            }
                        }
                    }) { Text("Accept and save") }
                    OutlinedButton(onClick = { store.discardCareer(); state.changed(); say("Discarded. Your current file is unchanged.") }) { Text("Discard") }
                }
                CareerView(next)
                return@ScrollBody
            }

            if (cur != null) {
                Muted("Last changed ${cur.str("updated_at").ifEmpty { "unknown" }}.")
                if (store.scoresFromCareer()) {
                    val found = remember(cur) { Matcher.findTerms(Career.text(cur)).sorted() }
                    SectionTitle("Skills scoring finds in it (${found.size})")
                    Muted("Postings are scored against this file, not your master resume. Only skills on WildThing's skill list count, and only certifications you have earned.")
                    if (found.isNotEmpty()) Tags(found)
                }
                CareerView(cur)
            } else Notice("No career file yet. Build one below.")

            SectionTitle(if (cur != null) "Rebuild it" else "Build it")
            Muted("Choose your documents: old resumes, a career knowledge base, skills lists, reviews. WildThing reads their text and makes a request your AI can answer.")
            OutlinedButton(onClick = { pick.launch(arrayOf("application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/markdown", "text/plain", "text/x-markdown", "application/octet-stream")) }) { Text("Choose documents") }
            sources.forEach { (name, _) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(name, Modifier.weight(1f))
                    TextButton(onClick = { sources = sources.filterNot { it.first == name } }) { Text("Remove") }
                }
            }
            OutlinedTextField(typed, { typed = it }, Modifier.fillMaxWidth(), label = { Text("Anything else to know (optional)") }, minLines = 3)
            if (cur != null) Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(includeCurrent, { includeCurrent = it })
                Text("Include the current file, so the skills you confirmed here are kept")
            }
            Button(onClick = {
                val all = sources + (if (typed.isNotBlank()) listOf("typed in WildThing" to typed.trim()) else emptyList())
                if (all.isEmpty()) say("Add at least one document, or type something about your work.")
                else { draft = store.makeCareerRequest(all, includeCurrent && cur != null); say("Request ready, from ${all.size} source(s).") }
            }) { Text("Make the request") }

            draft?.let { d ->
                SectionTitle("The request")
                Muted("${"%,d".format(d.length)} characters.")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { copyText(context, d) }) { Text("Copy") }
                    OutlinedButton(onClick = { shareText(context, d, "Build my career file") }) { Text("Share to your AI") }
                    if (google.linked) OutlinedButton(onClick = {
                        scope.launch {
                            google.drive { it.sendCareer(d) }?.let { name ->
                                state.snackbar.showSnackbar("Sent as requests/$name. Tell your AI: read AI_INSTRUCTIONS.md in the WildThing folder and build the career file requested there.")
                            }
                        }
                    }) { Text("Send to Google Drive") }
                }
            }

            SectionTitle("Bring the reply in")
            Muted("WildThing checks the file and shows it to you before anything is kept.")
            if (google.linked) OutlinedButton(onClick = {
                scope.launch {
                    val found = google.drive { it.careerReply() }
                    if (found == null) state.snackbar.showSnackbar("No career file reply in Google Drive yet (it would be replies/career_<time>.reply.md).")
                    else take(found.second, found.first)
                }
            }) { Text("Look in Google Drive") }
            OutlinedTextField(pasted, { pasted = it }, Modifier.fillMaxWidth(), label = { Text("Or paste the whole reply") }, minLines = 4)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = { pasted = clipboardText(context) }) { Text("Paste from clipboard") }
                Button(onClick = { take(pasted, null) }, enabled = pasted.isNotBlank()) { Text("Check it") }
            }
            if (problems.isNotEmpty()) Notice("That career file was not used. " + problems.take(5).joinToString(" ") +
                (if (problems.size > 5) " (and ${problems.size - 5} more)" else ""), warn = true)
        }
    }
}

/** A career file, shown readably (the desktop's _career_view.html). */
@Composable
private fun CareerView(c: JsonObject) {
    val person = c.obj("person")
    val contact = person?.obj("contact")
    Text(person?.str("name") ?: "", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
    person?.str("headline")?.takeIf { it.isNotEmpty() }?.let { Muted(it) }
    listOf("email", "phone", "location").mapNotNull { contact?.str(it)?.takeIf { s -> s.isNotEmpty() } }.takeIf { it.isNotEmpty() }
        ?.let { Muted(it.joinToString(" · ")) }
    c.str("summary").takeIf { it.isNotEmpty() }?.let { Text(it, Modifier.padding(top = 6.dp)) }

    val flags = c.items("flags")
    if (flags.isNotEmpty()) {
        SectionTitle("To settle")
        flags.forEach { Notice(it.str("text"), warn = true) }
    }
    val roles = c.items("roles")
    SectionTitle("Work (${roles.size})")
    roles.forEach { r ->
        Text("${r.str("title")}, ${r.str("employer")}", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
        Muted("${r.str("start")} to ${r.str("end").ifEmpty { "now" }}" + listOf(r.str("location"), r.str("type")).filter { it.isNotEmpty() }.joinToString("") { " · $it" })
        r.str("show_as").takeIf { it.isNotEmpty() }?.let { Muted("On documents: \"$it\"") }
        r.str("scope").takeIf { it.isNotEmpty() }?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        r.items("achievements").forEach { a -> Text("• " + a.str("text"), style = MaterialTheme.typography.bodyMedium) }
    }
    val skills = c.items("skills")
    SectionTitle("Skills (${skills.size})")
    Tags(skills.filter { it.str("source") != "confirmed" }.map { it.str("name") })
    skills.filter { it.str("source") == "confirmed" }.takeIf { it.isNotEmpty() }?.let { conf ->
        Muted("Confirmed here with \"I have this\":", Modifier.padding(top = 6.dp))
        Tags(conf.map { it.str("name") }, MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.onSecondaryContainer)
    }
    for ((title, key) in listOf("Certifications" to "certifications", "Education" to "education", "Projects" to "projects")) {
        val items = c.items(key)
        if (items.isEmpty()) continue
        SectionTitle(title)
        items.forEach { x ->
            Text("• " + when (key) {
                "certifications" -> x.str("name") + listOf(x.str("issuer"), x.str("date")).filter { it.isNotEmpty() }.joinToString("") { ", $it" } +
                    (if (x.str("status") != "earned") " (${x.str("status").replace('_', ' ')})" else "")
                "education" -> listOf(listOf(x.str("credential"), x.str("field")).filter { it.isNotEmpty() }.joinToString(" "), x.str("school"))
                    .filter { it.isNotEmpty() }.joinToString(", ")
                else -> x.str("name") + x.str("description").takeIf { it.isNotEmpty() }?.let { ": $it" }.orEmpty()
            }, style = MaterialTheme.typography.bodyMedium)
        }
    }
    val never = c.obj("privacy")?.strings("never_name").orEmpty()
    val quiet = c.obj("privacy")?.strings("never_mention").orEmpty()
    val avoid = c.obj("wording")?.let { (it["avoid"] as? JsonArray)?.mapNotNull { a -> (a as? JsonObject)?.str("phrase") } }.orEmpty()
    if (never.isNotEmpty() || quiet.isNotEmpty() || avoid.isNotEmpty()) {
        SectionTitle("Rules for every document")
        if (never.isNotEmpty()) Text("Never name: " + never.joinToString(", "))
        if (quiet.isNotEmpty()) Text("Never mention: " + quiet.joinToString(", "))
        avoid.forEach { Text("Do not say \"$it\"") }
    }
}

private fun JsonObject.str(k: String) = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: ""
private fun JsonObject.obj(k: String) = this[k] as? JsonObject
private fun JsonObject.items(k: String) = (this[k] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
private fun JsonObject.strings(k: String) = (this[k] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content }.orEmpty()

/** (file name, its text), or text null when it is not a Word, Markdown or text file of 3 MB or less. */
private fun readSource(context: Context, uri: Uri): Pair<String, String?> {
    val name = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
        if (c.moveToFirst()) c.getString(0) else null
    } ?: "document"
    val ext = name.substringAfterLast('.', "").lowercase()
    val bytes = runCatching { context.contentResolver.openInputStream(uri)?.use { it.readBytes() } }.getOrNull()
    if (bytes == null || bytes.size > 3 * 1024 * 1024 || ext !in listOf("docx", "md", "txt")) return name to null
    val text = if (ext == "docx") runCatching { Docx.text(bytes) }.getOrNull() else bytes.toString(Charsets.UTF_8)
    return name to text?.takeIf { it.isNotBlank() }
}
