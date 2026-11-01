package io.github.wpearsonsvg.wildthing.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import io.github.wpearsonsvg.wildthing.data.Store
import io.github.wpearsonsvg.wildthing.data.safeUrl
import wildthing.core.Tracking
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneOffset

/** What every screen shares: the store, a counter that makes screens re-read after a change, and session memory. */
class AppState(val store: Store, val snackbar: SnackbarHostState) {
    var version by mutableIntStateOf(0)
        private set
    fun changed() { version++ }

    /** Posting screen tab, remembered for the session: 0 = Posting, 1 = You. */
    var postingTab by mutableIntStateOf(0)
    /** The posting last opened, so an AI reply shared into the app can be filed with it. */
    var lastJobId: Long? = null
    /** Text an assistant shared back into the app, waiting for Paste reply. */
    var pendingReply by mutableStateOf<String?>(null)
    /** A posting shared in from another app, waiting for the Paste a posting screen. */
    var pendingShare by mutableStateOf<SharedPosting?>(null)
    /** Set when Apply opened the posting; when the user comes back the app asks "Did you apply?". */
    var pendingApply: Long? = null
    var applyLeftApp = false
    var askApplied by mutableStateOf<Long?>(null)

    /** Apply: open the posting, then ask on return. With no web link, ask straight away. */
    fun apply(context: Context, job: io.github.wpearsonsvg.wildthing.data.Job) {
        if (safeUrl(job.url)) {
            pendingApply = job.id
            applyLeftApp = false
            if (!openUrl(context, job.url)) { pendingApply = null; askApplied = job.id }
        } else askApplied = job.id
    }
    var fetching by mutableStateOf(false)

    /** Google wants the person to sign in again (found during a quiet check on opening the app). */
    var googleNeedsSignIn by mutableStateOf(false)
    /** Work to run once Google's consent screen has given access. */
    var pendingGoogle by mutableStateOf<(suspend () -> Unit)?>(null)
    /** Shared files changed both here and on another device, waiting for the person to choose. */
    var syncConflicts by mutableStateOf<List<io.github.wpearsonsvg.wildthing.data.DriveWork.Conflict>>(emptyList())
    var queueBusy by mutableStateOf(false)
}

data class SharedPosting(val title: String, val url: String, val text: String)

// ---- hand-offs to other apps --------------------------------------------------------------------------------
fun copyText(context: Context, text: String, label: String = "WildThing") {
    context.getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText(label, text))
    // Android 13+ shows its own confirmation when something is copied.
}

fun clipboardText(context: Context): String =
    context.getSystemService(ClipboardManager::class.java).primaryClip?.takeIf { it.itemCount > 0 }
        ?.getItemAt(0)?.coerceToText(context)?.toString() ?: ""

/** The share sheet: send the text to your AI app, any assistant, email, notes... */
fun shareText(context: Context, text: String, subject: String, title: String = "Send to...") {
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, text)
        putExtra(Intent.EXTRA_SUBJECT, subject)
    }
    context.startActivity(Intent.createChooser(send, title))
}

/** Opens a web page in a Custom Tab (the browser's own engine, inside the app). Only http(s) links are opened. */
fun openUrl(context: Context, url: String): Boolean {
    if (!safeUrl(url)) {
        Toast.makeText(context, "This posting has no web link.", Toast.LENGTH_SHORT).show()
        return false
    }
    return runCatching { CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, Uri.parse(url.trim())) }
        .recoverCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url.trim()))) }
        .isSuccess
}

// ---- small pieces -------------------------------------------------------------------------------------------
@Composable
fun ScorePill(score: Int, modifier: Modifier = Modifier, big: Boolean = false) {
    val x = LocalExtra.current
    val (bg, fg) = when (score / 25) { 3, 4 -> x.scoreHi; 2 -> x.scoreMid; else -> x.scoreLo }
    Text(
        score.toString(),
        modifier = modifier.background(bg, RoundedCornerShape(12.dp)).widthIn(min = if (big) 56.dp else 40.dp)
            .padding(horizontal = 8.dp, vertical = if (big) 6.dp else 2.dp),
        color = fg, fontWeight = FontWeight.Bold,
        style = if (big) MaterialTheme.typography.titleLarge else MaterialTheme.typography.labelLarge,
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}

@Composable
fun StatusChip(status: String, modifier: Modifier = Modifier) {
    val (bg, fg) = statusColors(status, MaterialTheme.colorScheme, LocalExtra.current)
    val shape = RoundedCornerShape(10.dp)
    Text(
        Tracking.LABEL[status] ?: status,
        modifier = modifier
            .then(if (status == "saved") Modifier.border(1.dp, MaterialTheme.colorScheme.secondary, shape) else Modifier)
            .background(bg, shape).padding(horizontal = 10.dp, vertical = 2.dp),
        color = fg, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, maxLines = 1,
    )
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier = modifier.padding(top = 20.dp, bottom = 6.dp), style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
}

@Composable
fun Muted(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier = modifier, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
fun Panel(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Card(modifier = modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
        Column(Modifier.padding(14.dp)) { content() }
    }
}

@Composable
fun Notice(text: String, warn: Boolean = false) {
    val scheme = MaterialTheme.colorScheme
    Text(text, Modifier.fillMaxWidth()
        .background(if (warn) scheme.secondaryContainer else scheme.primaryContainer, RoundedCornerShape(10.dp)).padding(12.dp),
        color = if (warn) scheme.onSecondaryContainer else scheme.onPrimaryContainer, style = MaterialTheme.typography.bodyMedium)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Tags(items: List<String>, color: Color = MaterialTheme.colorScheme.tertiaryContainer, fg: Color = MaterialTheme.colorScheme.onTertiaryContainer) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items.forEach {
            Text(it, Modifier.background(color, RoundedCornerShape(8.dp)).padding(horizontal = 8.dp, vertical = 3.dp),
                color = fg, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
fun SetupBanner(store: Store, version: Int, onSettings: () -> Unit) {
    val missing = remember(version) { store.setupMissing() }       // looked at again after a sync brings a resume in
    if (missing.isEmpty()) return
    Panel(Modifier.padding(bottom = 8.dp)) {
        Text("To get started, add ${missing.joinToString(" and ")} in Settings.", style = MaterialTheme.typography.bodyMedium)
        TextButton(onClick = onSettings) { Text("Open Settings") }
    }
}

@Composable
fun Confirm(title: String, text: String, yes: String, onYes: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title) }, text = { Text(text) },
        confirmButton = { TextButton(onClick = { onDismiss(); onYes() }) { Text(yes) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}

/** Paste an AI's whole reply. Filled from text shared into the app, else from the clipboard. */
@Composable
fun PasteReplyDialog(title: String, state: AppState, onSave: (String) -> Unit, onDismiss: () -> Unit) {
    val context = LocalContext.current
    var text by remember { mutableStateOf(state.pendingReply ?: clipboardText(context)) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Muted("Paste the whole reply, tags and all. It is filed with this posting; nothing else is changed.")
                Spacer(Modifier.padding(4.dp))
                OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth().heightIn(min = 160.dp, max = 360.dp), label = { Text("Reply") })
                TextButton(onClick = { text = clipboardText(context) }) { Text("Paste from clipboard") }
            }
        },
        confirmButton = {
            TextButton(enabled = text.isNotBlank(), onClick = { state.pendingReply = null; onSave(text.trim()); onDismiss() }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/**
 * Send to queue (the WildThing folder in Google Drive, when linked) / Send request to... / Copy / Paste reply.
 * The share sheet and Copy work with any assistant and no Drive.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HandOffButtons(request: () -> String, subject: String, onPaste: () -> Unit, pasteLabel: String = "Paste reply",
                   onQueue: (() -> Unit)? = null, waiting: Boolean = false) {
    val context = LocalContext.current
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (onQueue != null) androidx.compose.material3.Button(onClick = onQueue, enabled = !waiting) {
            Text(if (waiting) "In the queue" else "Send to queue")
        }
        val share = @Composable { Text("Send request to...") }
        if (onQueue == null) androidx.compose.material3.Button(onClick = { shareText(context, request(), subject, "Send request to...") }, content = { share() })
        else OutlinedButton(onClick = { shareText(context, request(), subject, "Send request to...") }, content = { share() })
        OutlinedButton(onClick = { copyText(context, request()) }) { Text("Copy") }
        OutlinedButton(onClick = onPaste) { Text(pasteLabel) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DatePickerFor(initial: LocalDate?, onPick: (LocalDate) -> Unit, onDismiss: () -> Unit) {
    val s = rememberDatePickerState(initialSelectedDateMillis = (initial ?: LocalDate.now()).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli())
    DatePickerDialog(onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                s.selectedDateMillis?.let { onPick(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()) }
                onDismiss()
            }) { Text("OK") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }) { DatePicker(s) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TimePickerFor(initial: LocalTime, onPick: (LocalTime) -> Unit, onDismiss: () -> Unit) {
    val s = rememberTimePickerState(initial.hour, initial.minute, is24Hour = false)
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Time") }, text = { TimePicker(s) },
        confirmButton = { TextButton(onClick = { onPick(LocalTime.of(s.hour, s.minute)); onDismiss() }) { Text("OK") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}

@Composable
fun Field(label: String, value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier, lines: Int = 1,
          keyboard: KeyboardType = KeyboardType.Text, help: String? = null) {
    Column(modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        OutlinedTextField(value, onChange, Modifier.fillMaxWidth(), label = { Text(label) }, singleLine = lines == 1,
            minLines = lines, keyboardOptions = KeyboardOptions(keyboardType = keyboard))
        if (help != null) Muted(help, Modifier.padding(start = 4.dp, top = 2.dp))
    }
}

@Composable
fun KeyValue(k: String, v: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.Top) {
        Text(k, Modifier.width(110.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
        Text(v, style = MaterialTheme.typography.bodyMedium)
    }
}
