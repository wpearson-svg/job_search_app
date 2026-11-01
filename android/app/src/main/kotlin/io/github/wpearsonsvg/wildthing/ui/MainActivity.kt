package io.github.wpearsonsvg.wildthing.ui

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import io.github.wpearsonsvg.wildthing.WildThingApp
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    /** Intents that arrive while the app is open (share-in, a notification tap). */
    private val incoming = MutableStateFlow<Intent?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val store = (application as WildThingApp).store
        if (savedInstanceState == null) incoming.value = intent
        val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}
        val prefs = getSharedPreferences("app", MODE_PRIVATE)
        if (!prefs.getBoolean("asked_notifications", false)) {
            prefs.edit().putBoolean("asked_notifications", true).apply()
            askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        // The opening animation plays on a cold start from the launcher, not when the app is brought back, rebuilt
        // after a rotation, or opened to receive a shared posting.
        val intro = savedInstanceState == null && intent?.action == Intent.ACTION_MAIN
        setContent {
            WildThingTheme {
                val snackbar = remember { SnackbarHostState() }
                val state = remember { AppState(store, snackbar) }
                OpeningAnimation(play = intro, sound = store.settings.openingSound) { App(state, incoming) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        incoming.value = intent
    }

    companion object {
        const val EXTRA_JOB = "job"
        const val EXTRA_TAB = "tab"
    }
}

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val TABS = listOf(
    Tab("postings", "Postings", Icons.Filled.Home),
    Tab("applications", "Applications", Icons.Filled.List),
    Tab("gaps", "Gap plan", Icons.Filled.Star),
    Tab("weekly", "Weekly", Icons.Filled.DateRange),
    Tab("more", "More", Icons.Filled.Menu),
)

private val REPLY_TAGS = listOf("<resume>", "<cover_letter>", "<likely_questions>", "<questions_to_ask>", "<research>",
    "<priorities>", "<plan>", "<resume_changes>")

@Composable
private fun App(state: AppState, incoming: MutableStateFlow<Intent?>) {
    val nav = rememberNavController()
    val intent by incoming.collectAsState()

    LaunchedEffect(intent) {
        val i = intent ?: return@LaunchedEffect
        incoming.value = null
        handleIntent(i, state, nav)
    }

    // Apply opened the posting outside the app; when the user comes back, ask before marking it Applied.
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { if (state.pendingApply != null) state.applyLeftApp = true }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        if (state.applyLeftApp && state.pendingApply != null) {
            state.askApplied = state.pendingApply
            state.pendingApply = null
            state.applyLeftApp = false
        }
    }
    val asking = state.askApplied
    if (asking != null) {
        val job = remember(asking) { state.store.job(asking) }
        AlertDialog(
            onDismissRequest = { state.askApplied = null },
            title = { Text("Did you apply?") },
            text = { Text("Mark \"${job?.title ?: "this posting"}\" as Applied with today's date?") },
            confirmButton = { TextButton(onClick = { state.store.markApplied(asking); state.askApplied = null; state.changed() }) { Text("Yes, I applied") } },
            dismissButton = { TextButton(onClick = { state.askApplied = null }) { Text("Not yet") } },
        )
    }

    // Opening the app: bring in replies from the Drive queue and catch up on shared details, without asking for
    // anything. If Google wants a fresh sign-in, say so once instead.
    val google = rememberGoogle(state)
    LaunchedEffect(Unit) {
        if (!google.linked) return@LaunchedEffect
        val r = google.drive(quiet = true) { d -> d.importAll() to d.sync() } ?: run {
            if (state.googleNeedsSignIn) state.snackbar.showSnackbar("Google needs you to sign in again: Settings > Google > Link.")
            return@LaunchedEffect
        }
        val (imp, sync) = r
        state.syncConflicts = sync.conflicts
        if (imp.imported > 0) state.snackbar.showSnackbar("Imported ${imp.imported} repl${if (imp.imported == 1) "y" else "ies"} from the AI queue.")
        else if (imp.problems.isNotEmpty()) state.snackbar.showSnackbar(imp.problems.first())
        if (sync.arrived > 0) state.snackbar.showSnackbar("${sync.arrived} posting${if (sync.arrived == 1) "" else "s"} arrived from your other device.")
        if (sync.pulled.isNotEmpty()) state.snackbar.showSnackbar("Updated from your other device: " +
            sync.pulled.joinToString(", ") { io.github.wpearsonsvg.wildthing.data.DriveWork.LABELS[it] ?: it } + ".")
    }
    // Work waiting for Google's consent screen runs once access is given.
    val pending = state.pendingGoogle
    LaunchedEffect(pending) {
        if (pending != null) { state.pendingGoogle = null; pending() }
    }
    state.syncConflicts.firstOrNull()?.let { c ->
        val label = io.github.wpearsonsvg.wildthing.data.DriveWork.LABELS[c.key] ?: c.key
        val scope = androidx.compose.runtime.rememberCoroutineScope()
        fun keep(which: String) {
            state.syncConflicts = state.syncConflicts.drop(1)
            scope.launch {
                val r = google.drive { it.sync(mapOf(c.key to which)) }
                if (r != null) state.snackbar.showSnackbar(if (which == "here") "Kept this phone's $label." else "Took the shared $label.")
            }
        }
        AlertDialog(
            onDismissRequest = { state.syncConflicts = state.syncConflicts.drop(1) },
            title = { Text("$label changed in both places") },
            text = { Text("Since the last sync, this was changed on this phone and on another device.\n\nThis phone: ${c.here}\nShared folder: ${c.folder}\n\nWhich one should both keep?") },
            confirmButton = { TextButton(onClick = { keep("here") }) { Text("Keep this phone's") } },
            dismissButton = { TextButton(onClick = { keep("folder") }) { Text("Keep the shared one") } },
        )
    }

    val back by nav.currentBackStackEntryAsState()
    val route = back?.destination?.route
    val tabRoute = TABS.firstOrNull { it.route == route }?.route
    Scaffold(
        snackbarHost = { SnackbarHost(state.snackbar) },
        bottomBar = {
            if (tabRoute != null) NavigationBar {
                TABS.forEach { t ->
                    NavigationBarItem(
                        selected = t.route == tabRoute,
                        onClick = { nav.goTab(t.route) },
                        icon = { Icon(t.icon, contentDescription = null) },
                        label = { Text(t.label, maxLines = 1) },
                    )
                }
            }
        },
    ) { pad ->
        // Only the bottom bar's space is taken here; each screen's own Scaffold handles the status bar.
        val bottom = if (tabRoute != null) pad.calculateBottomPadding() else 0.dp
        NavHost(nav, startDestination = "postings",
            modifier = Modifier.padding(bottom = bottom).consumeWindowInsets(PaddingValues(bottom = bottom))) {
            composable("postings") { PostingsScreen(state, open = { nav.navigate("posting/$it") }, add = { nav.navigate("add") }, settings = { nav.navigate("settings") }) }
            composable("applications") { ApplicationsScreen(state, open = { nav.navigate("posting/$it") }) }
            composable("gaps") { GapPlanScreen(state) }
            composable("weekly") { WeeklyScreen(state, open = { nav.navigate("posting/$it") }) }
            composable("more") { MoreScreen(go = { nav.navigate(it) }) }
            composable("posting/{id}", arguments = listOf(navArgument("id") { type = NavType.LongType })) { e ->
                PostingScreen(state, e.arguments!!.getLong("id"), back = { nav.popBackStack() })
            }
            composable("add") { AddScreen(state, back = { nav.popBackStack() }, saved = { id -> nav.popBackStack(); nav.navigate("posting/$id") }) }
            composable("profiles") { ProfilesScreen(state, back = { nav.popBackStack() }) }
            composable("resume") { ResumeScreen(state, back = { nav.popBackStack() }, settings = { nav.navigate("settings") }) }
            composable("settings") { SettingsScreen(state, back = { nav.popBackStack() }, help = { nav.navigate("queuehelp") }) }
            composable("queue") { QueueScreen(state, back = { nav.popBackStack() }, help = { nav.navigate("queuehelp") }, settings = { nav.navigate("settings") }) }
            composable("queuehelp") { QueueHelpScreen(back = { nav.popBackStack() }) }
            composable("about") { AboutScreen(back = { nav.popBackStack() }) }
            composable("career") { CareerScreen(state, back = { nav.popBackStack() }) }
        }
    }
}

private fun NavHostController.goTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}

private suspend fun handleIntent(i: Intent, state: AppState, nav: NavHostController) {
    when {
        i.action == Intent.ACTION_SEND && i.type?.startsWith("text/") == true -> {
            val text = i.getStringExtra(Intent.EXTRA_TEXT).orEmpty()
            val subject = i.getStringExtra(Intent.EXTRA_SUBJECT).orEmpty()
            if (REPLY_TAGS.any { it in text }) {
                // An assistant's reply coming back: file it with the posting it belongs to.
                state.pendingReply = text
                val last = state.lastJobId
                val gap = listOf("<priorities>", "<plan>", "<resume_changes>").any { it in text } && "<resume>" !in text
                when {
                    gap -> { nav.goTab("gaps"); state.snackbar.showSnackbar("Reply received. Tap Paste reply to save the plan.") }
                    last != null -> { state.postingTab = 1; nav.navigate("posting/$last"); state.snackbar.showSnackbar("Reply received. Tap Paste reply under AI work to file it here.") }
                    else -> state.snackbar.showSnackbar("Reply received. Open its posting and tap Paste reply.")
                }
            } else {
                state.pendingShare = parseShare(subject, text)
                nav.navigate("add")
            }
        }
        i.hasExtra(MainActivity.EXTRA_JOB) -> { state.postingTab = 1; nav.navigate("posting/${i.getLongExtra(MainActivity.EXTRA_JOB, 0)}") }
        i.getStringExtra(MainActivity.EXTRA_TAB) == "applications" -> nav.goTab("applications")
    }
}

private val URL = Regex("""https?://[^\s<>"']+""")

/** A share from LinkedIn, Indeed or a browser: usually a title or a sentence, plus a link. */
fun parseShare(subject: String, text: String): SharedPosting {
    val url = URL.find(text)?.value?.trimEnd('.', ',', ')') ?: ""
    val rest = text.replace(url, "").trim()
    val title = subject.ifEmpty { if (rest.length in 1..120 && '\n' !in rest) rest else "" }
    val body = if (rest.length > 120 || '\n' in rest) rest else ""
    return SharedPosting(title, url, body)
}
