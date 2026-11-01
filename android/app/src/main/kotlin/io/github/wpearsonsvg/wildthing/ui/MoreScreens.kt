package io.github.wpearsonsvg.wildthing.ui

import android.Manifest
import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.toMutableStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import io.github.wpearsonsvg.wildthing.BuildConfig
import io.github.wpearsonsvg.wildthing.R
import io.github.wpearsonsvg.wildthing.data.Profile
import io.github.wpearsonsvg.wildthing.data.SecretKeys
import io.github.wpearsonsvg.wildthing.data.UserSettings
import io.github.wpearsonsvg.wildthing.work.Reminders
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import wildthing.core.Matcher

const val SOURCE_URL = "https://github.com/wpearson-svg/job_search_app"

@Composable
fun MoreScreen(go: (String) -> Unit) {
    Screen("More") { pad ->
        Column(Modifier.padding(pad)) {
            listOf(
                "queue" to ("Queue" to "Requests waiting for your AI in Google Drive, and the replies that came back"),
                "profiles" to ("Profiles" to "Saved search focuses; Fetch runs each one"),
                "resume" to ("My resume" to "What the app finds on your resume, and skills you marked"),
                "career" to ("Career file" to "Everything true about you, built by your AI from your documents"),
                "add" to ("Paste a posting" to "Add one by hand, or share one in from another app"),
                "settings" to ("Settings" to "Resume, search, sources, AI instructions, keys, data"),
                "about" to ("About" to "Version, license and source code"),
            ).forEach { (route, t) ->
                ListItem(headlineContent = { Text(t.first) }, supportingContent = { Text(t.second) }, modifier = Modifier.clickable { go(route) })
                HorizontalDivider()
            }
        }
    }
}

// ---- Profiles -----------------------------------------------------------------------------------------------
@Composable
fun ProfilesScreen(state: AppState, back: () -> Unit) {
    val profiles = remember(state.version) { state.store.profiles() }
    var editing by remember { mutableStateOf<Profile?>(null) }
    var deleting by remember { mutableStateOf<Profile?>(null) }
    Screen("Profiles", back, actions = {
        TextButton(onClick = { editing = Profile(0, "", "", "", "") }) { Text("New", color = LocalExtra.current.onBar) }
    }) { pad ->
        ScrollBody(pad) {
            Muted("A profile is one search: its keywords decide what Fetch looks for, its titles decide what is kept, and what it finds is tagged with its name. Leave titles blank to use the keywords.")
            profiles.forEach { p ->
                Panel(Modifier.padding(top = 10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(p.name, Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                        Muted("${p.count} postings")
                    }
                    if (p.keywords.isNotBlank()) KeyValue("Keywords", p.keywords.lines().filter { it.isNotBlank() }.joinToString(", "))
                    if (p.titles.isNotBlank()) KeyValue("Titles", p.titles.lines().filter { it.isNotBlank() }.joinToString(", "))
                    if (p.location.isNotBlank()) KeyValue("Place", p.location)
                    Row {
                        TextButton(onClick = { editing = p }) { Text("Edit") }
                        TextButton(onClick = { deleting = p }) { Text("Remove") }
                    }
                }
            }
        }
    }
    editing?.let { p ->
        var name by remember(p) { mutableStateOf(p.name) }
        var kw by remember(p) { mutableStateOf(p.keywords) }
        var titles by remember(p) { mutableStateOf(p.titles) }
        var place by remember(p) { mutableStateOf(p.location) }
        var err by remember(p) { mutableStateOf<String?>(null) }
        AlertDialog(onDismissRequest = { editing = null }, title = { Text(if (p.id == 0L) "New profile" else "Edit profile") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Field("Name", name, { name = it })
                    Field("Keywords, one per line", kw, { kw = it }, lines = 3)
                    Field("Titles to keep, one per line", titles, { titles = it }, lines = 3)
                    Field("Place (for USAJOBS)", place, { place = it })
                    err?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                }
            },
            confirmButton = { TextButton(onClick = {
                err = state.store.saveProfile(p.id.takeIf { it != 0L }, name, kw, titles, place)
                if (err == null) { editing = null; state.changed() }
            }) { Text("Save") } },
            dismissButton = { TextButton(onClick = { editing = null }) { Text("Cancel") } })
    }
    deleting?.let { p ->
        Confirm("Remove profile", "Remove \"${p.name}\"? Its postings stay in the list; only the tag goes.", "Remove",
            onYes = { state.store.deleteProfile(p.id); state.changed() }, onDismiss = { deleting = null })
    }
}

// ---- My resume ----------------------------------------------------------------------------------------------
@Composable
fun ResumeScreen(state: AppState, back: () -> Unit, settings: () -> Unit) {
    val store = state.store
    val v = state.version
    val text = remember(v) { store.resumeText() }
    val found = remember(text) { Matcher.findTerms(text).sorted() }
    val extras = remember(v) { store.confirmedSkills().sorted() }
    Screen("My resume", back) { pad ->
        ScrollBody(pad) {
            KeyValue("File", store.resumeFile()?.name ?: "none yet")
            KeyValue("Length", "${text.length} characters")
            TextButton(onClick = settings) { Text("Upload a different resume in Settings") }
            if (store.scoresFromCareer()) Muted("Postings are scored against your career file, not this resume. The resume is still the example of format and tone.")
            SectionTitle("Skills found on your resume (${found.size})")
            if (found.isEmpty()) Muted("None yet.") else Tags(found)
            SectionTitle("Marked \"I have this\" (${extras.size})")
            Muted("These count as matches when scoring." + (if (store.scoresFromCareer()) " They are kept in your career file as confirmed skills." else "") +
                " Your resume is not changed; add them to it only if they are true.")
            extras.forEach { t ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(t, Modifier.weight(1f))
                    TextButton(onClick = { store.unhave(t); state.changed() }) { Text("Remove") }
                }
            }
        }
    }
}

// ---- Settings -----------------------------------------------------------------------------------------------
private fun displayName(context: Context, uri: Uri): String =
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
        if (c.moveToFirst()) c.getString(0) else null
    } ?: uri.lastPathSegment.orEmpty()

private fun lines(text: String) = text.replace(",", "\n").lines().map { it.trim().lowercase() }.filter { it.isNotEmpty() }

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SettingsScreen(state: AppState, back: () -> Unit, help: () -> Unit) {
    val store = state.store
    val s = store.settings
    val context = LocalContext.current
    val activity = context as? android.app.Activity
    val scope = rememberCoroutineScope()
    val v = state.version
    fun say(msg: String) = scope.launch { state.snackbar.showSnackbar(msg) }

    var name by remember(v) { mutableStateOf(s.yourName) }
    var titles by remember(v) { mutableStateOf(s.targetTitles.joinToString("\n")) }
    var keywords by remember(v) { mutableStateOf(s.searchKeywords.joinToString("\n")) }
    var places by remember(v) { mutableStateOf(s.locations.joinToString("\n")) }
    var place by remember(v) { mutableStateOf(s.place) }
    var boards by remember(v) { mutableStateOf(s.greenhouseBoards.joinToString("\n")) }
    var lever by remember(v) { mutableStateOf(s.leverCompanies.joinToString("\n")) }
    val sourcesOn = remember(v) { wildthing.core.Sources.enabled(s.sourceChoices).toMutableStateList() }
    var hasResume by remember(v) { mutableStateOf(!s.sendResumeInRequests) }
    var instructions by remember(v) { mutableStateOf(store.instructions()) }
    var showInstructions by remember { mutableStateOf(false) }       // long, so it starts folded away
    val keyInputs = remember(v) { SecretKeys.FIELDS.associate { it.first to mutableStateOf("") } }
    var confirmImport by remember { mutableStateOf<Uri?>(null) }
    var clearKeys by remember { mutableStateOf(false) }

    val pickResume = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri ?: return@rememberLauncherForActivityResult
        scope.launch {
            val (ok, msg) = withContext(Dispatchers.IO) {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: ByteArray(0)
                store.saveResume(displayName(context, uri), bytes)
            }
            if (ok) state.changed()
            say(msg)
        }
    }
    val exportTo = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        uri ?: return@rememberLauncherForActivityResult
        scope.launch {
            val r = runCatching { withContext(Dispatchers.IO) {
                context.contentResolver.openOutputStream(uri, "wt")!!.use { it.write(store.export().toByteArray()) }
            } }
            say(r.fold({ "Exported. Keys were not included." }, { "Could not export: ${it.message}" }))
        }
    }
    val importFrom = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> confirmImport = uri }
    val askNotify = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) say("Notifications are off for WildThing. You can turn them on in Android settings.")
    }
    val google = rememberGoogle(state)
    var check by remember { mutableStateOf<List<Pair<String, List<String>>>?>(null) }
    fun link() = scope.launch {
        val ok = suspend { s.googleLinked = true; state.changed(); say("Google account linked for Calendar and Drive.") }
        if (google.token(retry = { ok() }) != null) ok()
    }

    Screen("Settings", back) { pad ->
        ScrollBody(pad) {
            Muted("Everything here stays on this phone, in the app's private storage. Nothing is uploaded anywhere.")

            SectionTitle("Resume")
            Text(store.resumeFile()?.let { "Current file: ${it.name}" } ?: "No resume yet.", style = MaterialTheme.typography.bodyMedium)
            Muted("Every posting is scored against it, and every AI request says to use only facts from it.")
            OutlinedButton(onClick = { pickResume.launch(arrayOf(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/markdown", "text/plain", "text/x-markdown", "application/octet-stream",
            )) }) { Text("Choose resume file") }
            Muted("Word (.docx), Markdown (.md) or text (.txt), 3 MB at most. Choosing one replaces the old one and re-scores everything.")

            SectionTitle("Search")
            Field("Your name", name, { name = it })
            Field("Job titles you want", titles, { titles = it }, lines = 3, help = "One per line. A posting whose title contains one gets a boost.")
            Field("Search keywords", keywords, { keywords = it }, lines = 3, help = "One per line. What Fetch searches for (profiles can override).")
            Field("Places that count as yours", places, { places = it }, lines = 3,
                help = "One per line, e.g. your city, state, \"remote\". Postings elsewhere are skipped. \"Worldwide\" and \"anywhere\" never count.")
            Field("Main search place", place, { place = it }, help = "Used by USAJOBS.")

            SectionTitle("Sources")
            Muted("Fetch runs the sources switched on here (this phone only). On the phone, LinkedIn and Indeed postings come in through the share menu: tap Share on a posting there and pick WildThing.")
            wildthing.core.Sources.PHONE.forEach { src ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(src.label)
                        val missing = src.key == "usajobs" && !(store.keys.has("usajobs_key") && store.keys.has("usajobs_email"))
                        Muted(src.about + if (missing) " Not set up yet." else "")
                    }
                    Switch(src.key in sourcesOn, { on -> if (on) sourcesOn.add(src.key) else sourcesOn.remove(src.key) })
                }
            }
            Field("Greenhouse boards", boards, { boards = it }, lines = 2, help = "Company board names, one per line (from boards.greenhouse.io/<name>).")
            Field("Lever companies", lever, { lever = it }, lines = 2, help = "Company names, one per line (from jobs.lever.co/<name>).")

            SectionTitle("AI instructions")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("My assistant already has my resume and instructions", Modifier.weight(1f))
                Switch(hasResume, { hasResume = it })
            }
            Muted(if (hasResume) "Requests leave them out and tell the assistant to use the ones it holds." else "Every request carries your instructions and master resume, so it works in any chat.")
            Text("How to write your resume (${"%,d".format(instructions.length)} characters)", Modifier.padding(top = 8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { showInstructions = !showInstructions }) { Text(if (showInstructions) "Hide" else "Show and edit") }
                OutlinedButton(onClick = { copyText(context, instructions, "Resume instructions"); say("Instructions copied.") }) { Text("Copy") }
                TextButton(onClick = { store.saveInstructions(""); state.changed(); say("Instructions reset to the app's default.") }) { Text("Reset to default") }
            }
            if (showInstructions) {
                OutlinedTextField(instructions, { instructions = it }, Modifier.fillMaxWidth().padding(top = 4.dp), label = { Text("How to write your resume") }, minLines = 6)
                TextButton(onClick = { showInstructions = false }) { Text("Hide") }
            }

            Spacer(Modifier.height(8.dp))
            Button(onClick = {
                s.save(mapOf(
                    "your_name" to JsonPrimitive(name.trim()),
                    "target_titles" to UserSettings.strings(lines(titles)),
                    "search_keywords" to UserSettings.strings(lines(keywords)),
                    "locations" to UserSettings.strings(lines(places)),
                    "greenhouse_boards" to UserSettings.strings(boards.lines().map { it.trim() }.filter { it.isNotEmpty() }),
                    "lever_companies" to UserSettings.strings(lever.lines().map { it.trim() }.filter { it.isNotEmpty() }),
                    "send_resume_in_requests" to JsonPrimitive(!hasResume),
                    "usajobs" to JsonObject(mapOf("location" to JsonPrimitive(place.trim()))),
                    "sources" to JsonObject(wildthing.core.Sources.PHONE.associate { it.key to JsonPrimitive(it.key in sourcesOn) }),
                ))
                if (instructions.trim() != store.instructions().trim()) store.saveInstructions(instructions)
                store.rescoreAll()
                state.changed()
                say("Settings saved. Postings re-scored.")
            }) { Text("Save settings") }

            SectionTitle("Keys (optional)")
            Muted("Stored encrypted on this phone and never shown again. Leave a field blank to keep what is saved. Never put in an export file.")
            SecretKeys.FIELDS.forEach { (k, label) ->
                val st = keyInputs.getValue(k)
                OutlinedTextField(st.value, { st.value = it }, Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    label = { Text(label + if (store.keys.has(k)) " (saved)" else "") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false))
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = {
                    var n = 0
                    keyInputs.forEach { (k, st) -> if (st.value.isNotBlank()) { store.keys.set(k, st.value.trim()); st.value = ""; n++ } }
                    state.changed(); say(if (n > 0) "Saved $n key(s)." else "No new keys entered.")
                }) { Text("Save keys") }
                TextButton(onClick = { clearKeys = true }) { Text("Delete all saved keys") }
            }

            SectionTitle("Google (Calendar and Drive)")
            Muted("One Google sign-in covers Google Calendar (interviews) and Google Drive (the AI queue and your shared details). " +
                "Interviews can always go to the phone's calendar app with no sign-in.")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(if (s.googleLinked) "Google account linked." else "No Google account linked.", Modifier.weight(1f))
                if (s.googleLinked) TextButton(onClick = { s.googleLinked = false; state.changed() }) { Text("Unlink") }
                else TextButton(onClick = { link() }) { Text("Link") }
            }
            Text("Drive access", style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 8.dp))
            listOf(false to "Only files WildThing creates (drive.file). Your AI's replies are probably not visible this way.",
                true to "All of my Drive (drive). Needed so WildThing can see the replies your AI creates. Google shows an " +
                    "\"unverified app\" warning and, while the app is in testing mode, asks you to allow it again about every 7 days.").forEach { (full, label) ->
                Row(Modifier.fillMaxWidth().clickable { if (s.driveFull != full) { s.driveFull = full; state.changed(); if (s.googleLinked) link() } }
                    .padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    androidx.compose.material3.RadioButton(selected = s.driveFull == full, onClick = null)
                    Text(label, Modifier.padding(start = 8.dp), style = MaterialTheme.typography.bodyMedium)
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(enabled = s.googleLinked, onClick = { scope.launch { check = google.drive { it.check() } } }) { Text("Check Drive access") }
                OutlinedButton(enabled = s.googleLinked, onClick = {
                    scope.launch {
                        val r = google.drive { it.sync() } ?: return@launch
                        state.syncConflicts = r.conflicts
                        r.errors.forEach { say(it) }
                        if (r.conflicts.isEmpty() && r.errors.isEmpty()) say("In step with Drive (${r.pulled.size} received, ${r.pushed.size} sent" +
                            (if (r.arrived > 0) ", ${r.arrived} posting${if (r.arrived == 1) "" else "s"} arrived" else "") + ").")
                    }
                }) { Text("Sync now") }
            }
            Muted("Shared with your PC through WildThing/user/: master resume, search settings and profiles, AI instructions, career file, \"I have this\" skills, " +
                "and your postings with their status, notes, interviews, tags, saved AI work and gap plans, plus the companies you avoid (wildthing.db). Keys, sources and reminders stay on this phone.")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Delete imported files permanently")
                    Muted("Off: they go to the Drive trash, where you can still get them back for a while.")
                }
                Switch(s.drivePermanentDelete, { s.drivePermanentDelete = it; state.changed() })
            }
            TextButton(onClick = { help() }) { Text("How the AI queue works") }

            SectionTitle("Reminders")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Follow-ups and interviews")
                    Muted("A note when an application has waited 14 days, and 1 day and 1 hour before each interview.")
                }
                Switch(s.remindersOn, { s.remindersOn = it; state.changed(); if (it && !Reminders.canNotify(context)) askNotify.launch(Manifest.permission.POST_NOTIFICATIONS) })
            }

            SectionTitle("Opening")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Sound when WildThing opens")
                    Muted("The bite in the opening animation. Never played when the phone is on silent or vibrate.")
                }
                Switch(s.openingSound, { s.openingSound = it; state.changed() })
            }

            AvoidedSection(state)

            SectionTitle("Data")
            Muted("There is no cloud backup. Export everything (settings, resume, instructions, postings, applications, interviews, AI work, gap plans) as one file to keep it safe or to open it in the desktop WildThing. Keys are never included.")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { exportTo.launch("wildthing-export-${java.time.LocalDate.now()}.json") }) { Text("Export data") }
                OutlinedButton(onClick = { importFrom.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }) { Text("Import data") }
            }
        }
    }

    confirmImport?.let { uri ->
        Confirm("Import data", "Importing replaces everything in this app with the file's contents. Your keys stay as they are. Continue?", "Import",
            onYes = {
                scope.launch {
                    val r = runCatching { withContext(Dispatchers.IO) {
                        val raw = context.contentResolver.openInputStream(uri)!!.use { it.readBytes().toString(Charsets.UTF_8) }
                        store.import(raw)
                        Reminders.rescheduleAll(context)
                    } }
                    state.changed()
                    say(r.fold({ "Imported. Everything from the file is here now, and every posting was re-scored." }, { "Could not import that file: ${it.message}" }))
                }
            }, onDismiss = { confirmImport = null })
    }
    check?.let { listing ->
        AlertDialog(onDismissRequest = { check = null }, title = { Text("What WildThing can see in Drive") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Muted("If a file your AI or your PC created is missing here, WildThing cannot see it: switch Drive access to all of my Drive.")
                    listing.forEach { (folder, names) ->
                        Text(folder, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
                        if (names.isEmpty()) Muted("(empty)") else names.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }, confirmButton = { TextButton(onClick = { check = null }) { Text("OK") } })
    }
    if (clearKeys) Confirm("Delete keys", "Delete every saved key from this phone?", "Delete",
        onYes = { store.keys.clear(); state.changed(); say("Keys deleted.") }, onDismiss = { clearKeys = false })
}

// ---- About --------------------------------------------------------------------------------------------------
@Composable
fun AboutScreen(back: () -> Unit) {
    val context = LocalContext.current
    Screen("About", back) { pad ->
        ScrollBody(pad) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(painterResource(R.drawable.wildthing_crown), null, Modifier.size(56.dp).clip(RoundedCornerShape(12.dp)))
                Column(Modifier.padding(start = 14.dp)) {
                    Text("WildThing", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Muted("Version ${BuildConfig.VERSION_NAME}")
                }
            }
            Spacer(Modifier.height(16.dp))
            Text("A job search helper that runs on your phone. It scores postings against your own master resume, tracks your applications, and builds requests for whichever AI assistant you use. Your data stays on this phone.",
                style = MaterialTheme.typography.bodyMedium)
            SectionTitle("License")
            Text("WildThing is free software under the GNU Affero General Public License, version 3 (AGPL-3.0). You can use, study, share and change it. The complete source code is available at the link below.",
                style = MaterialTheme.typography.bodyMedium)
            TextButton(onClick = { openUrl(context, SOURCE_URL) }) { Text("Source code") }
            TextButton(onClick = { openUrl(context, "https://www.gnu.org/licenses/agpl-3.0.html") }) { Text("AGPL-3.0 license text") }
            SectionTitle("Credits")
            Text("Bite sound: \u201cChomp!\u201d by CryptologyMedia, from Pixabay, used under the Pixabay Content License. The sound keeps its own license; it is not covered by WildThing's AGPL-3.0.",
                style = MaterialTheme.typography.bodyMedium)
            TextButton(onClick = { openUrl(context, "https://pixabay.com/sound-effects/film-special-effects-chomp-155392/") }) { Text("The sound on Pixabay") }
            SectionTitle("What it does not do")
            Muted("No WildThing account, no telemetry, no WildThing servers. It only goes online when you fetch postings, open one, or use the Google Calendar and Drive features after you link a Google account. If you use the AI queue, request files sit in your own Google Drive until they are imported.")
        }
    }
}
