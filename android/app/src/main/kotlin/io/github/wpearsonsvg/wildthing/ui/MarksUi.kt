package io.github.wpearsonsvg.wildthing.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.unit.dp
import io.github.wpearsonsvg.wildthing.data.Job
import kotlinx.coroutines.launch
import wildthing.core.Marks

/** Tags on one posting, and the button that avoids its company (the desktop's _tags.html). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TagEditor(state: AppState, job: Job) {
    val store = state.store
    val scope = rememberCoroutineScope()
    val v = state.version
    val have = remember(v, job.id) { store.postingTags(job.id) }
    val avoid = remember(v, job.company) { store.avoided()[Marks.companyKey(job.company)] }
    var custom by remember { mutableStateOf("") }
    var asking by remember { mutableStateOf(false) }
    fun toggle(tag: String, on: Boolean) { store.setTag(job.id, tag, on); state.changed() }

    SectionTitle("Tags")
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Marks.TAGS.forEach { t -> FilterChip(selected = t.key in have, onClick = { toggle(t.key, t.key !in have) }, label = { Text(t.label) }) }
        have.filter { it !in Marks.LABEL }.forEach { t -> FilterChip(selected = true, onClick = { toggle(t, false) }, label = { Text(Marks.label(t)) }) }
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(custom, { custom = it.take(40) }, Modifier.weight(1f), label = { Text("Your own tag") }, singleLine = true)
        TextButton(onClick = {
            val t = Marks.customTag(custom)
            if (t.isNotEmpty()) { toggle(t, true); custom = "" }
        }) { Text("Add") }
    }
    if (job.company.isNotBlank()) {
        if (avoid != null) {
            Notice("You avoid ${avoid.company}" + (if (avoid.reason.isNotEmpty()) ": ${avoid.reason}" else "") + ".", warn = true)
            TextButton(onClick = { store.setAvoided(job.company, "", false); state.changed() }) { Text("Stop avoiding ${job.company}") }
        } else OutlinedButton(onClick = { asking = true }, Modifier.padding(top = 4.dp)) { Text("Avoid ${job.company}") }
    }

    if (asking) AvoidDialog(job.company, onDismiss = { asking = false }) { reason ->
        store.setAvoided(job.company, reason, true)
        state.changed()
        scope.launch { state.snackbar.showSnackbar("Avoiding ${job.company}. Its postings are hidden; use \"Show avoided\" to see them.") }
    }
}

@Composable
private fun AvoidDialog(company: String, onDismiss: () -> Unit, onAvoid: (String) -> Unit) {
    var reason by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Avoid $company?") },
        text = {
            Column {
                Muted("Its postings are hidden from the list. Names match without Inc, LLC and the like.")
                OutlinedTextField(reason, { reason = it.take(200) }, Modifier.fillMaxWidth().padding(top = 8.dp),
                    label = { Text("Why (optional, only you see it)") })
            }
        },
        confirmButton = { TextButton(onClick = { onAvoid(reason); onDismiss() }) { Text("Avoid") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}

/** The Settings list of companies you avoid. */
@Composable
fun AvoidedSection(state: AppState) {
    val store = state.store
    val v = state.version
    val list = remember(v) { store.avoided().values.toList() }
    var company by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }

    SectionTitle("Companies you avoid")
    Muted("Their postings are hidden from the list (use \"Show avoided\" there to see them). With Google linked, this list is shared with the desktop.")
    if (list.isEmpty()) Muted("None yet. Use Avoid on a posting, or add one here.")
    list.forEach { a ->
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(a.company, style = MaterialTheme.typography.bodyLarge)
                if (a.reason.isNotEmpty()) Muted(a.reason)
            }
            TextButton(onClick = { store.setAvoided(a.company, "", false); state.changed() }) { Text("Stop avoiding") }
        }
    }
    OutlinedTextField(company, { company = it }, Modifier.fillMaxWidth(), label = { Text("Company") }, singleLine = true)
    OutlinedTextField(reason, { reason = it.take(200) }, Modifier.fillMaxWidth(), label = { Text("Why (optional)") }, singleLine = true)
    OutlinedButton(onClick = {
        if (store.setAvoided(company, reason, true)) { company = ""; reason = ""; state.changed() }
    }, enabled = company.isNotBlank()) { Text("Avoid") }
}
