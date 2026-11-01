package io.github.wpearsonsvg.wildthing.ui

import android.app.Activity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import io.github.wpearsonsvg.wildthing.data.DriveWork
import io.github.wpearsonsvg.wildthing.data.GoogleAuth
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Gets a Google token for Calendar and Drive. When Google needs the person to choose an account or allow access,
 * it shows Google's own screen; the action then runs again once access is given.
 */
class Google(private val activity: Activity?, private val state: AppState, private val launcher: ActivityResultLauncher<IntentSenderRequest>) {
    /** What to run once the person has allowed access. */
    var afterConsent: (suspend (String) -> Unit)? = null

    val linked get() = state.store.settings.googleLinked

    /** A token, or null after saying why (or after showing Google's consent screen, which retries on its own). */
    suspend fun token(quiet: Boolean = false, retry: (suspend (String) -> Unit)? = null): String? {
        val a = activity ?: return null
        return when (val r = GoogleAuth.token(a, state.store.settings)) {
            is GoogleAuth.Result.Token -> r.token
            is GoogleAuth.Result.NeedsConsent -> {
                if (!quiet) {
                    afterConsent = retry
                    launcher.launch(IntentSenderRequest.Builder(r.intent.intentSender).build())
                } else state.googleNeedsSignIn = true
                null
            }
            is GoogleAuth.Result.Failed -> { if (!quiet) state.snackbar.showSnackbar(r.message); null }
        }
    }

    /** Runs Drive work off the main thread. Errors are shown, not thrown. */
    suspend fun <T> drive(quiet: Boolean = false, block: (DriveWork) -> T): T? {
        val retry: suspend (String) -> Unit = { t -> runDrive(t, quiet, block) }
        val t = token(quiet, retry) ?: return null
        return runDrive(t, quiet, block)
    }

    private suspend fun <T> runDrive(token: String, quiet: Boolean, block: (DriveWork) -> T): T? {
        val r = runCatching { withContext(Dispatchers.IO) { block(DriveWork(activity!!, state.store, token)) } }
        r.exceptionOrNull()?.let { e -> if (!quiet) state.snackbar.showSnackbar("Google Drive: ${e.message ?: e.javaClass.simpleName}") }
        state.changed()
        return r.getOrNull()
    }
}

@Composable
fun rememberGoogle(state: AppState): Google {
    val activity = LocalContext.current as? Activity
    lateinit var google: Google
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { res ->
        val token = activity?.let { GoogleAuth.tokenFromResult(it, res.data) }
        if (token != null) {
            state.store.settings.googleLinked = true
            state.googleNeedsSignIn = false
            state.pendingGoogle = google.afterConsent?.let { run -> suspend { run(token) } }
        }
        google.afterConsent = null
        state.changed()
    }
    google = remember(activity, launcher) { Google(activity, state, launcher) }
    return google
}
