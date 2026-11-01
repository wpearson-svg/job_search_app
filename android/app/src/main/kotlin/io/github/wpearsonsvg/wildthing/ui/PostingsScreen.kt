package io.github.wpearsonsvg.wildthing.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import io.github.wpearsonsvg.wildthing.R
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.wpearsonsvg.wildthing.data.Filter
import io.github.wpearsonsvg.wildthing.data.Job
import io.github.wpearsonsvg.wildthing.data.Sort
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import wildthing.core.Marks
import wildthing.core.Tracking

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PostingsScreen(state: AppState, open: (Long) -> Unit, add: () -> Unit, settings: () -> Unit) {
    val store = state.store
    val scope = rememberCoroutineScope()
    var status by rememberSaveable { mutableStateOf("active") }
    var profileId by rememberSaveable { mutableStateOf<Long?>(null) }
    var minScore by rememberSaveable { mutableStateOf(0) }
    var sort by rememberSaveable { mutableStateOf(Sort.SCORE) }
    var tagF by rememberSaveable { mutableStateOf("") }
    var showAvoided by rememberSaveable { mutableStateOf(false) }
    var sortSheet by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var confirm by remember { mutableStateOf<String?>(null) }
    var report by remember { mutableStateOf<List<String>?>(null) }
    val list = rememberLazyListState()
    val google = rememberGoogle(state)

    val v = state.version
    val all = remember(v, status, profileId, minScore, sort, tagF) { store.jobs(Filter(status, profileId, minScore, sort, tagF)) }
    val avoided = remember(v) { store.avoided() }
    val isAvoided = { j: Job -> Marks.companyKey(j.company) in avoided }
    val hidden = remember(all, avoided) { all.count(isAvoided) }
    val jobs = remember(all, avoided, showAvoided) { if (showAvoided) all else all.filterNot(isAvoided) }
    val profiles = remember(v) { store.profiles() }
    val tags = remember(v, jobs) { jobs.associate { it.id to store.tags(it.id) } }
    val marks = remember(v) { store.postingTags() }
    val inUse = remember(marks) {
        marks.values.flatten().toSet().sortedWith(compareBy({ it !in Marks.LABEL }, { Marks.label(it).lowercase() }))
    }

    fun fetch() {
        if (state.fetching) return
        state.fetching = true
        scope.launch {
            var lines = runCatching { withContext(Dispatchers.IO) { store.fetch(profileId) } }
                .getOrElse { listOf("Fetch did not finish: ${it.message}") }
            if (google.linked) google.drive(quiet = true) { it.syncPostings() }?.let { n ->
                if (n > 0) lines = lines + "$n posting${if (n == 1) "" else "s"} arrived from your other device."
            }
            state.fetching = false
            state.changed()
            report = lines
        }
    }

    fun swipe(job: Job, to: String) {
        store.setStatus(job.id, to)
        state.changed()
        scope.launch {
            val r = state.snackbar.showSnackbar("${Tracking.LABEL[to]}: ${job.title}", "Undo", duration = SnackbarDuration.Short)
            if (r == SnackbarResult.ActionPerformed) { store.restoreStatus(job.id, job.status, job.statusUpdated); state.changed() }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Image(painterResource(R.drawable.wildthing_crown), contentDescription = null,
                            modifier = Modifier.size(30.dp).clip(RoundedCornerShape(8.dp)))
                        Spacer(Modifier.width(10.dp))
                        Text("WildThing")
                    }
                },
                colors = barColors(),
                actions = {
                    TextButton(onClick = { sortSheet = true }) { Text(sort.label, color = LocalExtra.current.onBar) }
                    IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, "More actions", tint = LocalExtra.current.onBar) }
                    DropdownMenu(menu, { menu = false }) {
                        DropdownMenuItem({ Text("Fetch now") }, onClick = { menu = false; fetch() })
                        DropdownMenuItem({ Text("Re-score all") }, onClick = {
                            menu = false; store.rescoreAll(); state.changed()
                            scope.launch { state.snackbar.showSnackbar("Re-scored every posting against the current resume.") }
                        })
                        DropdownMenuItem({ Text("Merge duplicates") }, onClick = { menu = false; confirm = "merge" })
                        DropdownMenuItem({ Text("Remove outside my areas (${store.purgeCandidates(true).size})") }, onClick = { menu = false; confirm = "outside" })
                        DropdownMenuItem({ Text("Remove all untouched (${store.purgeCandidates(false).size})") }, onClick = { menu = false; confirm = "untouched" })
                    }
                },
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = add, containerColor = MaterialTheme.colorScheme.secondary) { Icon(Icons.Filled.Add, "Paste a posting") }
        },
    ) { pad ->
        PullToRefreshBox(isRefreshing = state.fetching, onRefresh = ::fetch, modifier = Modifier.padding(pad).fillMaxSize()) {
            LazyColumn(state = list, contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 88.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                item { SetupBanner(store, v, settings) }
                item {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        item {
                            ChipMenu(
                                label = when (status) { "active" -> "Not dismissed"; "all" -> "All"; else -> Tracking.LABEL[status] ?: status },
                                selected = status != "active",
                                options = listOf("active" to "Not dismissed") + Tracking.STATUSES + listOf("all" to "All"),
                            ) { status = it }
                        }
                        item {
                            ChipMenu(
                                label = profiles.firstOrNull { it.id == profileId }?.name ?: "All profiles",
                                selected = profileId != null,
                                options = listOf("" to "All profiles") + profiles.map { it.id.toString() to it.name },
                            ) { profileId = it.toLongOrNull() }
                        }
                        item {
                            ChipMenu(
                                label = if (minScore == 0) "Any score" else "Score $minScore+",
                                selected = minScore > 0,
                                options = listOf(0, 25, 40, 50, 60, 70, 80).map { it.toString() to if (it == 0) "Any score" else "$it or more" },
                            ) { minScore = it.toInt() }
                        }
                        if (inUse.isNotEmpty() || tagF.isNotEmpty()) item {
                            ChipMenu(
                                label = if (tagF.isEmpty()) "Any tag" else Marks.label(tagF),
                                selected = tagF.isNotEmpty(),
                                options = listOf("" to "Any tag") + inUse.map { it to Marks.label(it) },
                            ) { tagF = it }
                        }
                        if (avoided.isNotEmpty()) item {
                            FilterChip(selected = showAvoided, onClick = { showAvoided = !showAvoided },
                                label = { Text(if (showAvoided || hidden == 0) "Show avoided" else "Show avoided ($hidden hidden)") })
                        }
                    }
                }
                if (jobs.isEmpty()) item {
                    Muted("No postings here yet. Pull down to fetch, tap + to paste one, or share one into WildThing from LinkedIn, Indeed or your browser.",
                        Modifier.padding(vertical = 24.dp))
                }
                items(jobs, key = { it.id }) { job ->
                    SwipeRow(job, onSave = { swipe(job, "saved") }, onDismiss = { swipe(job, "dismissed") }) {
                        PostingCard(job, tags[job.id].orEmpty(), marks[job.id].orEmpty(), isAvoided(job), allowed = store.settings.locations) { open(job.id) }
                    }
                }
                item { Muted("Swipe right to save, left to dismiss.", Modifier.padding(top = 8.dp)) }
            }
        }
    }

    if (sortSheet) ModalBottomSheet(onDismissRequest = { sortSheet = false }) {
        Column(Modifier.padding(16.dp, 0.dp, 16.dp, 32.dp)) {
            Text("Sort by", style = MaterialTheme.typography.titleMedium)
            Sort.entries.forEach { s ->
                Row(Modifier.fillMaxWidth().clickable { sort = s; sortSheet = false }.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = sort == s, onClick = { sort = s; sortSheet = false })
                    Text(s.label)
                }
            }
        }
    }

    report?.let { lines ->
        androidx.compose.material3.AlertDialog(onDismissRequest = { report = null }, title = { Text("Fetch") },
            text = { Column { lines.forEachIndexed { i, l -> Text(l, style = if (i == 0) MaterialTheme.typography.bodyMedium else MaterialTheme.typography.bodySmall, modifier = Modifier.padding(vertical = 2.dp)) } } },
            confirmButton = { TextButton(onClick = { report = null }) { Text("OK") } })
    }

    when (confirm) {
        "merge" -> Confirm("Merge duplicates", "Merge postings that are the same job listed twice? Untouched duplicates are removed and their links kept on the one that stays.", "Merge",
            onYes = { val n = store.mergeDuplicates(); state.changed(); scope.launch { state.snackbar.showSnackbar(if (n > 0) "Merged $n duplicate posting(s)." else "No duplicates found.") } },
            onDismiss = { confirm = null })
        "outside", "untouched" -> {
            val outside = confirm == "outside"
            Confirm("Clean up the list",
                "Permanently remove ${store.purgeCandidates(outside).size} " + (if (outside) "posting(s) outside your areas" else "untouched fetched posting(s)") +
                    "? Only fetched postings still at New are removed. Anything you saved, dismissed, applied to, pasted or logged is kept. Removed postings can come back on the next Fetch.",
                "Remove", onYes = { val n = store.purge(outside); state.changed(); scope.launch { state.snackbar.showSnackbar("Removed $n posting(s).") } },
                onDismiss = { confirm = null })
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun barColors() = TopAppBarDefaults.topAppBarColors(
    containerColor = LocalExtra.current.bar, titleContentColor = LocalExtra.current.barAccent,
    navigationIconContentColor = LocalExtra.current.onBar, actionIconContentColor = LocalExtra.current.onBar,
)

@Composable
fun ChipMenu(label: String, selected: Boolean, options: List<Pair<String, String>>, onPick: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        FilterChip(selected = selected, onClick = { open = true }, label = { Text(label) },
            trailingIcon = { Icon(Icons.Filled.ArrowDropDown, null) })
        DropdownMenu(open, { open = false }) {
            options.forEach { (k, l) -> DropdownMenuItem({ Text(l) }, onClick = { open = false; onPick(k) }) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SwipeRow(job: Job, onSave: () -> Unit, onDismiss: () -> Unit, content: @Composable () -> Unit) {
    val s = rememberSwipeToDismissBoxState(confirmValueChange = {
        when (it) {
            SwipeToDismissBoxValue.StartToEnd -> onSave()
            SwipeToDismissBoxValue.EndToStart -> onDismiss()
            SwipeToDismissBoxValue.Settled -> {}
        }
        false   // the row stays; the list re-reads and drops it if the filter no longer shows it
    })
    SwipeToDismissBox(s, backgroundContent = {
        val toSave = s.dismissDirection == SwipeToDismissBoxValue.StartToEnd
        Box(Modifier.fillMaxSize().background(
            if (toSave) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(12.dp))
            .padding(horizontal = 20.dp), contentAlignment = if (toSave) Alignment.CenterStart else Alignment.CenterEnd) {
            Text(if (toSave) "Save" else "Dismiss", fontWeight = FontWeight.SemiBold)
        }
    }, enableDismissFromStartToEnd = job.status != "saved", enableDismissFromEndToStart = job.status != "dismissed") { content() }
}

@Composable
private fun PostingCard(job: Job, tags: List<String>, marks: List<String>, avoided: Boolean, allowed: List<String>, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest),
        border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.Top) {
            ScorePill(job.score)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(job.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, maxLines = 2,
                        overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    if (job.flags.isNotEmpty()) Icon(Icons.Filled.Warning, job.flags.joinToString(" "), Modifier.padding(start = 4.dp).width(16.dp),
                        tint = LocalExtra.current.warn)
                }
                val sub = listOf(job.company, job.location).filter { it.isNotEmpty() }.joinToString(" · ")
                if (sub.isNotEmpty()) Muted(sub)
                Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(job.status)
                    Text(job.source, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (!wildthing.core.Matcher.locationOk(job.location, allowed)) Text("outside your areas", style = MaterialTheme.typography.labelSmall, color = LocalExtra.current.warn)
                    if (job.followUp()) Text("follow up", style = MaterialTheme.typography.labelSmall, color = LocalExtra.current.warn)
                    if (avoided) Text("avoided company", style = MaterialTheme.typography.labelSmall, color = LocalExtra.current.warn)
                }
                if (marks.isNotEmpty()) Row(Modifier.padding(top = 6.dp)) {
                    Tags(marks.map(Marks::label), MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.onSecondaryContainer)
                }
                if (tags.isNotEmpty()) Row(Modifier.padding(top = 6.dp)) { Tags(tags) }
            }
        }
    }
}
