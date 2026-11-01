package io.github.wpearsonsvg.wildthing.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.wpearsonsvg.wildthing.data.Event
import io.github.wpearsonsvg.wildthing.data.Job
import kotlinx.coroutines.launch
import wildthing.core.Gaps
import wildthing.core.Tracking
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Screen(title: String, back: (() -> Unit)? = null, actions: @Composable () -> Unit = {}, content: @Composable (PaddingValues) -> Unit) {
    Scaffold(topBar = {
        TopAppBar(title = { Text(title) }, colors = barColors(), actions = { actions() },
            navigationIcon = { if (back != null) IconButton(onClick = back) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } })
    }, content = content)
}

@Composable
fun ScrollBody(pad: PaddingValues, content: @Composable () -> Unit) {
    Column(Modifier.padding(pad).fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp, 8.dp, 16.dp, 40.dp)) { content() }
}

// ---- Paste a posting (also where shared postings land) --------------------------------------------------------
@Composable
fun AddScreen(state: AppState, back: () -> Unit, saved: (Long) -> Unit) {
    val shared = remember { state.pendingShare.also { state.pendingShare = null } }
    val context = LocalContext.current
    var title by rememberSaveable { mutableStateOf(shared?.title ?: "") }
    var company by rememberSaveable { mutableStateOf("") }
    var location by rememberSaveable { mutableStateOf("") }
    var url by rememberSaveable { mutableStateOf(shared?.url ?: "") }
    var text by rememberSaveable { mutableStateOf(shared?.text ?: "") }
    var error by remember { mutableStateOf<String?>(null) }
    Screen("Paste a posting", back) { pad ->
        ScrollBody(pad) {
            if (shared != null) Notice(
                if (shared.text.isBlank()) "Shared link received. Open it, copy the job description, and paste it below so it can be scored."
                else "Shared posting received. Check the details, then save.")
            Muted("Paste the full posting text (from LinkedIn, Indeed, a company site...). It is scored against your master resume.",
                Modifier.padding(vertical = 8.dp))
            Field("Job title", title, { title = it })
            Field("Company", company, { company = it })
            Field("Location", location, { location = it })
            Field("Link", url, { url = it.trim() }, keyboard = androidx.compose.ui.text.input.KeyboardType.Uri)
            Row {
                if (io.github.wpearsonsvg.wildthing.data.safeUrl(url)) TextButton(onClick = { openUrl(context, url) }) { Text("Open link") }
                TextButton(onClick = { text = clipboardText(context) }) { Text("Paste from clipboard") }
            }
            Field("Posting text", text, { text = it; error = null }, lines = 10)
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Spacer(Modifier.height(8.dp))
            Button(onClick = {
                if (text.isBlank()) error = "Paste the posting text first."
                else { val id = state.store.addPasted(title, company, location, url, text.trim()); state.changed(); saved(id) }
            }) { Text("Save and score") }
        }
    }
}

// ---- Applications -------------------------------------------------------------------------------------------
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ApplicationsScreen(state: AppState, open: (Long) -> Unit) {
    val v = state.version
    val rows = remember(v) { state.store.applications() }
    val upcoming = remember(v) { state.store.upcoming(30) }
    var logging by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Screen("Applications", actions = { TextButton(onClick = { logging = true }) { Text("Log one", color = LocalExtra.current.onBar) } }) { pad ->
        LazyColumn(Modifier.padding(pad), contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 40.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Tracking.APPLIED_STAGES.forEach { s ->
                        val n = rows.count { it.status == s }
                        if (n > 0) Row(verticalAlignment = Alignment.CenterVertically) { StatusChip(s); Text(" $n", style = MaterialTheme.typography.labelLarge) }
                    }
                }
            }
            if (upcoming.isNotEmpty()) {
                item { SectionTitle("Coming up") }
                items(upcoming, key = { "e" + it.first.id }) { (e, j) -> EventRow(e, j) { j?.let { open(it.id) } } }
            }
            item { SectionTitle("Applications (${rows.size})") }
            if (rows.isEmpty()) item { Muted("Nothing applied to yet. Apply from a posting, or log one you sent somewhere else.") }
            items(rows, key = { it.id }) { j -> AppRow(j) { open(j.id) } }
        }
    }
    if (logging) LogDialog(onDismiss = { logging = false }) { t, c, l, u, s, d ->
        state.store.logApplication(t, c, l, u, s, d); state.changed()
        scope.launch { state.snackbar.showSnackbar("Logged: $t.") }
    }
}

@Composable
fun EventRow(e: Event, job: Job?, onClick: () -> Unit) {
    Panel(Modifier.clickable(onClick = onClick)) {
        Text(e.title(job), fontWeight = FontWeight.SemiBold)
        Muted(e.whenText + (if (e.place.isNotEmpty()) " · ${e.place}" else ""))
    }
}

@Composable
private fun AppRow(j: Job, onClick: () -> Unit) {
    Panel(Modifier.clickable(onClick = onClick)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(j.title, fontWeight = FontWeight.SemiBold)
                Muted(listOf(j.company, j.appliedOn?.let { "applied $it" + (j.daysSinceApplied()?.let { d -> " ($d days)" } ?: "") } ?: "").filter { it.isNotEmpty() }.joinToString(" · "))
                if (j.followUp()) Text("Time to follow up", color = LocalExtra.current.warn, style = MaterialTheme.typography.labelMedium)
            }
            StatusChip(j.status)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LogDialog(onDismiss: () -> Unit, onSave: (String, String, String, String, String, String) -> Unit) {
    var title by remember { mutableStateOf("") }
    var company by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("applied") }
    var date by remember { mutableStateOf(LocalDate.now()) }
    var pick by remember { mutableStateOf(false) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Log an application") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Muted("For a job you applied to somewhere else, that is not in the list.")
                Field("Job title", title, { title = it })
                Field("Company", company, { company = it })
                Field("Location", location, { location = it })
                Field("Link", url, { url = it })
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Tracking.APPLIED_STAGES.forEach { s -> FilterChip(status == s, { status = s }, label = { Text(Tracking.LABEL.getValue(s)) }) }
                }
                TextButton(onClick = { pick = true }) { Text("Applied on $date") }
            }
        },
        confirmButton = { TextButton(enabled = title.isNotBlank(), onClick = { onSave(title, company, location, url, status, date.toString()); onDismiss() }) { Text("Log it") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
    if (pick) DatePickerFor(date, { date = it }, { pick = false })
}

// ---- Gap plan -----------------------------------------------------------------------------------------------
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GapPlanScreen(state: AppState) {
    val store = state.store
    val scope = rememberCoroutineScope()
    val v = state.version
    var profileId by rememberSaveable { mutableStateOf<Long?>(null) }
    var minScore by rememberSaveable { mutableStateOf(0) }
    var hours by rememberSaveable { mutableStateOf(5f) }
    var weeks by rememberSaveable { mutableStateOf(12f) }
    var top by rememberSaveable { mutableStateOf(15f) }
    var paste by remember { mutableStateOf(false) }
    val profiles = remember(v) { store.profiles() }
    val (jobs, focus) = remember(v, profileId, minScore) { store.gapScope(profileId, minScore) }
    val (rows, phases) = remember(jobs) { Gaps.buildPlan(jobs.map { it.asGapJob() }) }
    val plans = remember(v) { store.gapPlans() }
    val subject = "Skills plan: $focus"
    val google = rememberGoogle(state)

    Screen("Gap plan") { pad ->
        ScrollBody(pad) {
            Muted("What your saved postings ask for that your resume does not show, most wanted first. Built from ${jobs.size} postings.")
            Row(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ChipMenu(profiles.firstOrNull { it.id == profileId }?.name ?: "All profiles", profileId != null,
                    listOf("" to "All profiles") + profiles.map { it.id.toString() to it.name }) { profileId = it.toLongOrNull() }
                ChipMenu(if (minScore == 0) "Any score" else "Score $minScore+", minScore > 0,
                    listOf(0, 25, 40, 50, 60, 70).map { it.toString() to if (it == 0) "Any score" else "$it or more" }) { minScore = it.toInt() }
            }
            if (rows.isEmpty()) Muted("No gaps yet. Save or fetch some postings first.")
            phases.forEach { ph ->
                SectionTitle(ph.label)
                ph.items.forEach { r ->
                    Panel(Modifier.padding(bottom = 6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(r.term, Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                            Text(r.kind, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Muted("In ${r.jobs} postings, required in ${r.required}.")
                        Text(r.action, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
                        TextButton(onClick = { if (store.have(r.term)) { state.changed(); scope.launch { state.snackbar.showSnackbar("Marked \"${r.term}\" as something you have. Add it to your resume only if it is true.") } } }) { Text("I have this") }
                    }
                }
            }
            if (rows.size > 10) {
                SectionTitle("Also asked for")
                Tags(rows.drop(10).map { "${it.term} (${it.jobs})" })
            }

            SectionTitle("Plan it with your assistant")
            Text("About ${hours.toInt()} hours a week", style = MaterialTheme.typography.bodyMedium)
            Slider(hours, { hours = it }, valueRange = 1f..40f, steps = 38)
            Text("For ${weeks.toInt()} weeks", style = MaterialTheme.typography.bodyMedium)
            Slider(weeks, { weeks = it }, valueRange = 1f..52f, steps = 50)
            Text("Include the top ${top.toInt()} gaps", style = MaterialTheme.typography.bodyMedium)
            Slider(top, { top = it }, valueRange = 3f..40f, steps = 36)
            HandOffButtons({ store.gapMessage(profileId, minScore, hours.toInt(), weeks.toInt(), top.toInt()) }, subject, onPaste = { paste = true },
                onQueue = if (!google.linked) null else ({
                    scope.launch {
                        val msg = store.gapMessage(profileId, minScore, hours.toInt(), weeks.toInt(), top.toInt(), wrap = false)
                        if (google.drive { it.send("gap", null, focus, focus, msg) } != null)
                            state.snackbar.showSnackbar("Added to the queue. Tell your AI: read AI_INSTRUCTIONS.md and process the pending batch.")
                    }
                }), waiting = state.queueBusy)

            SectionTitle("Saved plans")
            if (plans.isEmpty()) Muted("None yet. Paste a reply above to keep it here.")
            plans.forEach { p ->
                Panel(Modifier.padding(bottom = 8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("${p.scope}, ${p.createdAt.take(10)}", Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                        TextButton(onClick = { store.deleteGapPlan(p.id); state.changed() }) { Text("Delete") }
                    }
                    val sections = Gaps.parsePlan(p.content)
                    if (sections.isEmpty()) SelectionContainer { Text(p.content, style = MaterialTheme.typography.bodySmall) }
                    sections.forEach { (l, t) ->
                        Text(l, style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 8.dp))
                        SelectionContainer { Text(t, style = MaterialTheme.typography.bodyMedium) }
                    }
                }
            }
        }
    }
    if (paste) PasteReplyDialog("Paste the plan reply", state, onSave = { text ->
        store.saveGapPlan(focus, text); state.changed()
        scope.launch { state.snackbar.showSnackbar("Plan saved.") }
    }, onDismiss = { paste = false })
}

// ---- Weekly ------------------------------------------------------------------------------------------------
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WeeklyScreen(state: AppState, open: (Long) -> Unit) {
    val context = LocalContext.current
    var days by rememberSaveable { mutableStateOf(7) }
    val w = remember(state.version, days) { state.store.weekly(days) }
    Screen("Weekly") { pad ->
        ScrollBody(pad) {
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                listOf(7, 14, 30).forEachIndexed { i, d ->
                    SegmentedButton(days == d, { days = d }, SegmentedButtonDefaults.itemShape(i, 3)) { Text("$d days") }
                }
            }
            Spacer(Modifier.height(12.dp))
            Panel {
                SelectionContainer { Text(w.summary, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodyMedium) }
                Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { shareText(context, w.summary, "Job search, last ${w.days} days", "Share") }) { Text("Share") }
                    OutlinedButton(onClick = { copyText(context, w.summary) }) { Text("Copy") }
                }
            }
            KeyValue("Interview rate", w.rate)
            listOf("Sent" to w.applied, "Moved forward" to w.interviews, "Closed out" to w.rejected, "Due for a follow-up" to w.waiting).forEach { (label, list) ->
                if (list.isEmpty()) return@forEach
                SectionTitle("$label (${list.size})")
                list.forEach { j ->
                    Row(Modifier.fillMaxWidth().clickable { open(j.id) }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(j.title + (if (j.company.isNotEmpty()) " · ${j.company}" else ""), Modifier.weight(1f))
                        StatusChip(j.status)
                    }
                }
            }
            if (w.upcoming.isNotEmpty()) {
                SectionTitle("Next 2 weeks")
                w.upcoming.forEach { (e, j) -> EventRow(e, j) { j?.let { open(it.id) } }; Spacer(Modifier.width(6.dp)) }
            }
        }
    }
}
