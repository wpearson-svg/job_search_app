package io.github.wpearsonsvg.wildthing.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import io.github.wpearsonsvg.wildthing.data.Event
import io.github.wpearsonsvg.wildthing.data.GoogleCalendar
import io.github.wpearsonsvg.wildthing.data.Job
import io.github.wpearsonsvg.wildthing.data.PhoneCalendar
import io.github.wpearsonsvg.wildthing.data.Store
import io.github.wpearsonsvg.wildthing.work.Reminders
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import wildthing.core.Replies
import wildthing.core.Tracking
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PostingScreen(state: AppState, id: Long, back: () -> Unit) {
    val v = state.version
    val job = remember(v, id) { state.store.job(id) }
    LaunchedEffect(id) { state.lastJobId = id }
    Scaffold(topBar = {
        TopAppBar(title = { Text(job?.company?.ifEmpty { "Posting" } ?: "Posting", maxLines = 1) }, colors = barColors(),
            navigationIcon = { IconButton(onClick = back) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } })
    }) { pad ->
        if (job == null) {
            Muted("That posting is no longer here.", Modifier.padding(pad).padding(16.dp)); return@Scaffold
        }
        Column(Modifier.padding(pad).fillMaxSize()) {
            // Stays above both tabs: what the posting is, its score and where you stand.
            Column(Modifier.padding(16.dp, 12.dp, 16.dp, 8.dp)) {
                Text(job.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                Muted(listOf(job.company, job.location, job.source).filter { it.isNotEmpty() }.joinToString(" · "))
                Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    ScorePill(job.score, big = true)
                    Text("match", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    StatusChip(job.status)
                }
            }
            TabRow(selectedTabIndex = state.postingTab) {
                Tab(state.postingTab == 0, { state.postingTab = 0 }, text = { Text("Posting") })
                Tab(state.postingTab == 1, { state.postingTab = 1 }, text = { Text("You") })
            }
            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp, 4.dp, 16.dp, 32.dp)) {
                if (state.postingTab == 0) PostingTab(state, job) else YouTab(state, job)
            }
        }
    }
}

/** About the posting: tags, why this score, other boards, the text itself. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PostingTab(state: AppState, job: Job) {
    val store = state.store
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val v = state.version
    val tags = remember(v, job.id) { store.tags(job.id) }
    val links = remember(v, job.id) { store.links(job.id) }

    TagEditor(state, job)

    if (tags.isNotEmpty()) { SectionTitle("Profiles"); Tags(tags) }

    SectionTitle("Why this score")
    if (job.flags.isNotEmpty()) job.flags.forEach { Text("• $it", color = LocalExtra.current.warn, style = MaterialTheme.typography.bodyMedium) }
    Text("Matched", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 8.dp, bottom = 4.dp))
    if (job.matched.isEmpty()) Muted("None of the skills in this posting show on your resume yet.") else Tags(job.matched)
    for ((label, terms) in listOf("Required, not on your resume" to job.required, "Preferred, not on your resume" to job.preferred)) {
        if (terms.isEmpty()) continue
        Text(label, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(top = 12.dp, bottom = 2.dp))
        terms.forEach { t ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(t, Modifier.weight(1f))
                TextButton(onClick = {
                    if (store.have(t)) {
                        state.changed()
                        scope.launch { state.snackbar.showSnackbar("Marked \"$t\" as something you have. Postings re-scored. Add it to your resume only if it is true.") }
                    }
                }) { Text("I have this") }
            }
        }
    }

    if (links.isNotEmpty()) {
        SectionTitle("Also listed at")
        links.forEach { l -> TextButton(onClick = { openUrl(context, l.url) }) { Text(l.source + ": " + l.url.take(60), maxLines = 1) } }
    }

    SectionTitle("Posting")
    if (job.description.isBlank()) Muted("No description yet. Open the posting, copy its text, and paste it with Paste a posting to score it.")
    else SelectionContainer { Text(job.description, style = MaterialTheme.typography.bodyMedium) }
    Spacer(Modifier.height(12.dp))
    if (io.github.wpearsonsvg.wildthing.data.safeUrl(job.url)) Button(onClick = { openUrl(context, job.url) }) { Text("Open posting") }
}

/** About you, for this posting: status, application, interviews, AI work. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun YouTab(state: AppState, job: Job) {
    val store = state.store
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val v = state.version

    SectionTitle("Status")
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        StatusPicker(job.status) { store.setStatus(job.id, it); state.changed() }
        if (job.status !in Tracking.APPLIED_STAGES) Button(onClick = { state.apply(context, job) }) { Text("Apply") }
    }
    if (job.status !in Tracking.APPLIED_STAGES) Muted("Apply opens the posting; when you come back, WildThing asks whether you applied.", Modifier.padding(top = 4.dp))

    if (job.followUp()) Column(Modifier.padding(top = 12.dp)) {
        Notice("Applied ${job.daysSinceApplied()} days ago with no change. Time to follow up?", warn = true)
    }

    SectionTitle("Application")
    var pickDate by remember { mutableStateOf(false) }
    var notes by remember(job.id, v) { mutableStateOf(job.notes) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Applied on: " + (job.appliedOn ?: "not yet"), Modifier.weight(1f))
        TextButton(onClick = { pickDate = true }) { Text(if (job.appliedOn == null) "Set date" else "Change") }
        if (job.appliedOn != null) TextButton(onClick = { store.setApplication(job.id, null, notes); state.changed() }) { Text("Clear") }
    }
    OutlinedTextField(notes, { notes = it }, Modifier.fillMaxWidth(), label = { Text("Notes") }, minLines = 3)
    if (notes != job.notes) TextButton(onClick = { store.setApplication(job.id, job.appliedOn, notes); state.changed() }) { Text("Save notes") }
    if (pickDate) DatePickerFor(job.appliedOn?.let { runCatching { LocalDate.parse(it) }.getOrNull() },
        onPick = { store.setApplication(job.id, it.toString(), notes); state.changed() }, onDismiss = { pickDate = false })

    Interviews(state, job)
    AiWork(state, job)
}

@Composable
fun StatusPicker(status: String, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column {
        OutlinedButton(onClick = { open = true }) { Text(Tracking.LABEL[status] ?: status) }
        DropdownMenu(open, { open = false }) {
            Tracking.STATUSES.forEach { (k, l) -> DropdownMenuItem({ Text(l) }, onClick = { open = false; onPick(k) }) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Interviews(state: AppState, job: Job) {
    val store = state.store
    val context = LocalContext.current
    val activity = context as? android.app.Activity
    val scope = rememberCoroutineScope()
    val events = remember(state.version, job.id) { store.events(job.id) }
    var adding by remember { mutableStateOf(false) }

    val google = rememberGoogle(state)
    suspend fun sendToGoogle(token: String, e: Event) {
        val r = runCatching { withContext(Dispatchers.IO) { GoogleCalendar.insert(token, e, job) } }
        state.snackbar.showSnackbar(r.fold({ "Added to Google Calendar." }, { it.message ?: "Could not add it to Google Calendar." }))
    }

    SectionTitle("Interviews and follow-ups")
    if (events.isEmpty()) Muted("Nothing scheduled.")
    events.forEach { e ->
        Panel(Modifier.padding(vertical = 4.dp)) {
            Text(e.kind + (if (e.past) " (past)" else ""), fontWeight = FontWeight.SemiBold)
            Text(e.whenText + " · ${e.minutes} min" + (if (e.zone.id != java.time.ZoneId.systemDefault().id) " (${e.zone.id})" else ""))
            if (e.place.isNotEmpty()) Muted(e.place)
            if (e.notes.isNotEmpty()) Muted(e.notes)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TextButton(onClick = {
                    runCatching { context.startActivity(PhoneCalendar.insertIntent(e, job)) }
                        .onFailure { scope.launch { state.snackbar.showSnackbar("No calendar app found on this phone.") } }
                }) { Text("Add to phone calendar") }
                if (google.linked) TextButton(onClick = {
                    scope.launch { google.token(retry = { t -> sendToGoogle(t, e) })?.let { sendToGoogle(it, e) } }
                }) { Text("Add to Google Calendar") }
                TextButton(onClick = { store.deleteEvent(e.id); Reminders.cancelEvent(context, e.id); state.changed() }) { Text("Remove") }
            }
        }
    }
    TextButton(onClick = { adding = true }) { Text("+ Add an interview or follow-up") }
    if (adding) AddEventDialog(onDismiss = { adding = false }) { kind, start, minutes, place, notes ->
        val id = store.addEvent(job.id, kind, start, minutes, place, notes)
        store.eventById(id)?.let { Reminders.scheduleEvent(context, it) }
        state.changed()
        scope.launch { state.snackbar.showSnackbar("$kind added. Use the buttons beside it to put it in your calendar.") }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AddEventDialog(onDismiss: () -> Unit, onSave: (String, LocalDateTime, Int, String, String) -> Unit) {
    var kind by remember { mutableStateOf("Interview") }
    var date by remember { mutableStateOf(LocalDate.now().plusDays(1)) }
    var time by remember { mutableStateOf(LocalTime.of(10, 0)) }
    var minutes by remember { mutableStateOf("60") }
    var place by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var pickDate by remember { mutableStateOf(false) }
    var pickTime by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Add to this posting") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Store.EVENT_KINDS.forEach { k ->
                        androidx.compose.material3.FilterChip(kind == k, { kind = k }, label = { Text(k) })
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { pickDate = true }) { Text(date.format(java.time.format.DateTimeFormatter.ofPattern("EEE MMM d, yyyy"))) }
                    TextButton(onClick = { pickTime = true }) { Text(time.format(java.time.format.DateTimeFormatter.ofPattern("h:mm a"))) }
                }
                Field("Minutes", minutes, { minutes = it.filter(Char::isDigit).take(3) }, keyboard = androidx.compose.ui.text.input.KeyboardType.Number)
                Field("Place or link", place, { place = it })
                Field("Notes", notes, { notes = it }, lines = 2)
                Muted("Saved in this phone's time zone (${java.time.ZoneId.systemDefault().id}).")
            }
        },
        confirmButton = { TextButton(onClick = { onSave(kind, date.atTime(time), minutes.toIntOrNull() ?: 60, place, notes); onDismiss() }) { Text("Add") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
    if (pickDate) DatePickerFor(date, { date = it }, { pickDate = false })
    if (pickTime) TimePickerFor(time, { time = it }, { pickTime = false })
}

@Composable
private fun AiWork(state: AppState, job: Job) {
    val store = state.store
    val scope = rememberCoroutineScope()
    val outs = remember(state.version, job.id) { store.outputs(job.id) }
    var paste by remember { mutableStateOf<String?>(null) }   // "resume" or "prep"
    val google = rememberGoogle(state)
    val waiting = remember(state.version, job.id) { store.waitingFor(job.id) }
    fun queue(kind: String, message: () -> String): (() -> Unit)? = if (!google.linked) null else ({
        scope.launch {
            state.queueBusy = true
            val name = google.drive { it.send(kind, job.id, "", job.company.ifEmpty { job.title }, message()) }
            state.queueBusy = false
            if (name != null) state.snackbar.showSnackbar("Added to the queue. Tell your AI: read AI_INSTRUCTIONS.md and process the pending batch.")
        }
    })
    val subject = "${job.title}${if (job.company.isNotEmpty()) " at ${job.company}" else ""}"

    SectionTitle("AI work")
    Muted(if (google.linked) "Send to queue puts the request in the WildThing folder in your Google Drive for your AI to answer; " +
        "the reply comes back on its own. Or send it to any assistant and paste its whole reply back here. " +
        "Every request says to use only facts from your master resume."
    else "Send a request to your AI app or any assistant, then paste its whole reply back here. " +
        "Every request says to use only facts from your master resume. Link Google Drive in Settings to use the queue instead.")
    if (state.pendingReply != null) Column(Modifier.padding(top = 8.dp)) { Notice("A reply was shared into WildThing. Tap Paste reply to file it with this posting.") }

    for ((kind, label, wantCover) in listOf(Triple("resume", "Resume", false), Triple("cover_letter", "Resume and cover letter", true))) {
        Text(label, style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 14.dp, bottom = 4.dp))
        val saved = outs[kind]
        Muted(if (saved != null) "Saved ${saved.createdAt.take(10)}." else "Not yet.")
        val qkind = if (wantCover) "resume_cover" else "resume"
        HandOffButtons({ store.withContext(Replies.buildUserMessage(job.asRequest(), wantCover)) }, "Resume request: $subject",
            onPaste = { paste = "resume" }, onQueue = queue(qkind) { Replies.buildUserMessage(job.asRequest(), wantCover) },
            waiting = qkind in waiting || state.queueBusy)
    }
    listOf("resume" to "Resume", "cover_letter" to "Cover letter", "review_notes" to "Review notes").forEach { (k, l) ->
        outs[k]?.let { o -> SavedText(l, o.content, o.warnings, "$l: $subject") }
    }

    Text("Interview prep", style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 18.dp, bottom = 4.dp))
    val prep = outs["prep"]
    Muted(if (prep != null) "Saved ${prep.createdAt.take(10)}." else "Not yet.")
    HandOffButtons({ store.withContext(Replies.buildPrepMessage(job.asRequest())) }, "Interview prep: $subject", onPaste = { paste = "prep" },
        onQueue = queue("prep") { Replies.buildPrepMessage(job.asRequest()) }, waiting = "prep" in waiting || state.queueBusy)
    prep?.let { p ->
        val sections = Replies.parsePrep(p.content)
        if (sections.isEmpty()) SavedText("Interview prep", p.content, emptyList(), "Interview prep: $subject")
        else sections.forEach { (l, t) -> SavedText(l, t, emptyList(), "$l: $subject") }
    }

    when (paste) {
        "resume" -> PasteReplyDialog("Paste the resume reply", state, onSave = { text ->
            val note = store.saveResumeReply(job.id, text); state.changed()
            scope.launch { state.snackbar.showSnackbar(note ?: "Saved with this posting.") }
        }, onDismiss = { paste = null })
        "prep" -> PasteReplyDialog("Paste the interview prep reply", state, onSave = { text ->
            store.savePrepReply(job.id, text); state.changed()
            scope.launch { state.snackbar.showSnackbar("Interview prep saved.") }
        }, onDismiss = { paste = null })
    }
}

@Composable
private fun SavedText(label: String, text: String, warnings: List<String>, subject: String) {
    val context = LocalContext.current
    var open by remember { mutableStateOf(false) }
    Panel(Modifier.padding(top = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
            TextButton(onClick = { open = !open }) { Text(if (open) "Hide" else "Show") }
        }
        warnings.forEach { Text("• $it", color = LocalExtra.current.warn, style = MaterialTheme.typography.bodySmall) }
        if (open) {
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            SelectionContainer { Text(text, style = MaterialTheme.typography.bodyMedium) }
            Row {
                TextButton(onClick = { copyText(context, text) }) { Text("Copy") }
                TextButton(onClick = { shareText(context, text, subject, "Share") }) { Text("Share") }
            }
        }
    }
    Spacer(Modifier.width(0.dp))
}
