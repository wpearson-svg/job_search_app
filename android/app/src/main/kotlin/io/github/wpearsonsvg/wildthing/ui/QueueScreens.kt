package io.github.wpearsonsvg.wildthing.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.wpearsonsvg.wildthing.data.DriveWork
import kotlinx.coroutines.launch
import wildthing.core.AiQueue

private val STATE_LABELS = mapOf("waiting" to "Waiting for a reply", "import" to "Reply found", "missing" to "Reported done, reply file not there yet",
    "skipped" to "Skipped", "failed" to "Failed")

/** The AI work queue in Google Drive: what is waiting, what came back, and why anything was skipped or failed. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QueueScreen(state: AppState, back: () -> Unit, help: () -> Unit, settings: () -> Unit) {
    val google = rememberGoogle(state)
    val scope = rememberCoroutineScope()
    var batches by remember { mutableStateOf<List<DriveWork.BatchView>?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    val done = remember(state.version) { state.store.recentImported() }

    fun importNow(showNone: Boolean) {
        if (!google.linked || refreshing) return
        refreshing = true
        scope.launch {
            val r = google.drive { it.importAll() }
            refreshing = false
            if (r != null) {
                batches = r.batches
                r.problems.forEach { p -> state.snackbar.showSnackbar(p) }
                if (r.imported > 0) state.snackbar.showSnackbar("Imported ${r.imported} repl${if (r.imported == 1) "y" else "ies"}.")
                else if (showNone && r.problems.isEmpty()) state.snackbar.showSnackbar("No new replies in the queue.")
            }
        }
    }
    LaunchedEffect(google.linked) { importNow(false) }

    Screen("Queue", back, actions = { TextButton(onClick = help) { Text("Help", color = LocalExtra.current.onBar) } }) { pad ->
        PullToRefreshBox(isRefreshing = refreshing, onRefresh = { importNow(true) }, modifier = Modifier.padding(pad).fillMaxSize()) {
            LazyColumn(contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 40.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!google.linked) item {
                    Panel {
                        Text("Link Google Drive to use the queue", fontWeight = FontWeight.SemiBold)
                        Muted("WildThing puts requests in a WildThing folder in your Google Drive; an assistant that can read and create files there answers them, and the replies come back here.")
                        Row {
                            TextButton(onClick = help) { Text("How the AI queue works") }
                            TextButton(onClick = settings) { Text("Open Settings") }
                        }
                    }
                } else item {
                    Muted("Tell your AI: \"Read AI_INSTRUCTIONS.md in the WildThing folder and process the pending batch.\" Pull down to import, or tap the button.")
                    Button(onClick = { importNow(true) }, enabled = !refreshing, modifier = Modifier.padding(top = 8.dp)) { Text("Import replies") }
                }
                val list = batches.orEmpty()
                if (google.linked && batches != null && list.isEmpty()) item { Muted("Nothing waiting.", Modifier.padding(top = 12.dp)) }
                list.forEach { b ->
                    item(key = b.batch.batch) {
                        SectionTitle("Batch ${b.batch.batch}")
                        Muted(if (b.report) "Your AI has reported on this batch." else "No report from your AI yet. New requests join this batch until it reports.")
                    }
                    items(b.rows, key = { "${b.batch.batch}-${it.item.n}" }) { r -> QueueRow(state, google, r) { batches = it } }
                }
                if (done.isNotEmpty()) {
                    item { SectionTitle("Recently imported") }
                    items(done, key = { "done-${it.id}" }) { i ->
                        Muted("${AiQueue.KINDS[i.kind]}, ${i.label.ifEmpty { i.scope }} · ${(i.importedAt ?: "").take(10)}")
                    }
                }
            }
        }
    }
}

@Composable
private fun QueueRow(state: AppState, google: Google, r: DriveWork.Row, update: (List<DriveWork.BatchView>) -> Unit) {
    val scope = rememberCoroutineScope()
    var confirm by remember { mutableStateOf(false) }
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("%02d · %s".format(r.item.n, AiQueue.KINDS[r.item.kind]), fontWeight = FontWeight.SemiBold)
                Muted(r.item.label.ifEmpty { r.item.scope })
                Text(STATE_LABELS[r.action] ?: r.action, style = MaterialTheme.typography.bodyMedium,
                    color = if (r.action in listOf("skipped", "failed", "missing")) LocalExtra.current.warn else MaterialTheme.colorScheme.onSurface)
                if (r.reason.isNotEmpty()) Muted(r.reason)
            }
            TextButton(onClick = { confirm = true }) { Text("Remove") }
        }
    }
    if (confirm) Confirm("Remove from the queue", "Remove this request? Its request file and any reply are deleted from the folder.", "Remove",
        onYes = { scope.launch { google.drive { it.remove(r.item); it.view() }?.let(update) } }, onDismiss = { confirm = false })
}

/** "How the AI queue works": plain screens so it works offline. Neutral about which assistant. */
@Composable
fun QueueHelpScreen(back: () -> Unit) {
    Screen("How the AI queue works", back) { pad ->
        ScrollBody(pad) {
            Text("The queue hands requests to an AI assistant as files in a WildThing folder in your Google Drive, and takes its replies back the same way. " +
                "It works with an assistant that can read and create files in that Drive. WildThing never calls an AI itself.",
                style = MaterialTheme.typography.bodyMedium)
            Steps("Set it up", 1, listOf(
                "Link your Google account in Settings > Google. One sign-in covers Calendar and Drive.",
                "WildThing creates the WildThing folder in your Drive, with AI_INSTRUCTIONS.md in it, the first time you send a request (or tap Check Drive access).",
                "Connect your AI to Google Drive. This differs between assistants: you need one that can read and create files in that Drive, signed in to the same Google account.",
            ))
            Steps("Use it", 4, listOf(
                "On a posting, open the You tab and tap Send to queue for a resume, cover letter or interview prep. The Gap plan screen has one too. Requests gather in one batch.",
                "Tell your AI: \"Read AI_INSTRUCTIONS.md in the WildThing folder and process the pending batch.\" It writes one reply per request and a short report: done, skipped or failed.",
                "Open WildThing: it imports the replies on its own. Or open the Queue and pull down, or tap Import replies.",
                "After each reply is saved, its reply and request files are deleted (to the Drive trash, unless you chose permanent delete in Settings). When a batch is all in, its TODO files go too.",
            ))
            SectionTitle("If something goes wrong")
            Bullet("The AI cannot see the folder: it is probably using a different Google account. Share the WildThing folder with the account your AI uses.")
            Bullet("A reply is not showing up: with the narrow Drive access, WildThing can only see files it made itself, so replies your AI creates stay invisible. Tap Check Drive access in Settings; if the replies are missing from the list, switch Drive access to full.")
            Bullet("An item came back skipped or failed: the Queue shows the reason your AI gave. Fix the cause (for example, paste the full posting text) and send it again, or remove it.")
            SectionTitle("Without Drive")
            Text("Send request to... (the share sheet) and Copy work with any assistant and no Drive. Paste the whole reply back with Paste reply.", style = MaterialTheme.typography.bodyMedium)
            SectionTitle("Privacy")
            Text("Request files contain your resume (unless your AI already holds it) and the posting text. They sit in your Google Drive until they are imported and deleted.",
                style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun Steps(title: String, first: Int, steps: List<String>) {
    SectionTitle(title)
    steps.forEachIndexed { i, s ->
        Row(Modifier.padding(vertical = 4.dp)) {
            Text("${first + i}.", Modifier.padding(end = 8.dp), fontWeight = FontWeight.SemiBold)
            Text(s, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun Bullet(s: String) {
    Row(Modifier.padding(vertical = 4.dp)) {
        Text("•", Modifier.padding(end = 8.dp))
        Text(s, style = MaterialTheme.typography.bodyMedium)
    }
}
