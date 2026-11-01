package io.github.wpearsonsvg.wildthing.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import io.github.wpearsonsvg.wildthing.R
import io.github.wpearsonsvg.wildthing.WildThingApp
import io.github.wpearsonsvg.wildthing.data.Event
import io.github.wpearsonsvg.wildthing.ui.MainActivity
import java.time.Duration
import java.time.Instant
import java.util.concurrent.TimeUnit

/**
 * Local reminders only (no push server): a daily check for applications waiting 14+ days, and two reminders
 * before each interview (1 day and 1 hour before). WorkManager keeps them across restarts.
 */
object Reminders {
    const val CHANNEL = "reminders"
    private val BEFORE = listOf(Duration.ofDays(1) to "tomorrow", Duration.ofHours(1) to "in 1 hour")

    fun createChannel(context: Context) {
        val ch = NotificationChannel(CHANNEL, "Reminders", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "Follow-ups due and interviews coming up"
        }
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    fun scheduleDailyCheck(context: Context) {
        val req = PeriodicWorkRequestBuilder<FollowUpWorker>(1, TimeUnit.DAYS).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork("follow-ups", ExistingPeriodicWorkPolicy.KEEP, req)
    }

    fun scheduleEvent(context: Context, e: Event) {
        val wm = WorkManager.getInstance(context)
        BEFORE.forEachIndexed { i, (lead, label) ->
            val at = e.start.toInstant().minus(lead)
            val delay = Duration.between(Instant.now(), at)
            if (delay.isNegative) return@forEachIndexed
            val req = OneTimeWorkRequestBuilder<EventReminderWorker>()
                .setInitialDelay(delay.toMillis(), TimeUnit.MILLISECONDS)
                .setInputData(workDataOf("event" to e.id, "label" to label))
                .addTag("event-${e.id}")
                .build()
            wm.enqueueUniqueWork("event-${e.id}-$i", ExistingWorkPolicy.REPLACE, req)
        }
    }

    fun cancelEvent(context: Context, eventId: Long) = WorkManager.getInstance(context).cancelAllWorkByTag("event-$eventId")

    /** After an import every event is new to this phone. */
    fun rescheduleAll(context: Context) {
        val store = (context.applicationContext as WildThingApp).store
        store.upcoming(365).forEach { (e, _) -> scheduleEvent(context, e) }
    }

    fun canNotify(context: Context) =
        context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED &&
            NotificationManagerCompat.from(context).areNotificationsEnabled()

    @Suppress("MissingPermission")
    fun notify(context: Context, id: Int, title: String, text: String, jobId: Long? = null) {
        if (!canNotify(context)) return
        val open = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            if (jobId != null) putExtra(MainActivity.EXTRA_JOB, jobId) else putExtra(MainActivity.EXTRA_TAB, "applications")
        }
        val pi = PendingIntent.getActivity(context, id, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_crown)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(id, n)
    }
}

class FollowUpWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val store = (applicationContext as WildThingApp).store
        if (!store.settings.remindersOn) return Result.success()
        val due = store.followUpsDue()
        // Only say something when a posting newly crosses 14 days, not every morning for the same ones.
        val prefs = applicationContext.getSharedPreferences("reminders", Context.MODE_PRIVATE)
        val told = prefs.getStringSet("told", emptySet())!!
        val fresh = due.filter { it.id.toString() !in told }
        if (fresh.isNotEmpty()) {
            val text = if (fresh.size == 1) "${fresh[0].title}${if (fresh[0].company.isNotEmpty()) " at ${fresh[0].company}" else ""}: " +
                "applied ${fresh[0].daysSinceApplied()} days ago with no change. Time to follow up?"
            else "${fresh.size} applications have waited 14+ days with no change. Time to follow up?"
            Reminders.notify(applicationContext, 1, "Follow-up due", text, fresh.singleOrNull()?.id)
        }
        prefs.edit().putStringSet("told", due.map { it.id.toString() }.toSet()).apply()
        return Result.success()
    }
}

class EventReminderWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val store = (applicationContext as WildThingApp).store
        if (!store.settings.remindersOn) return Result.success()
        val e = store.eventById(inputData.getLong("event", -1)) ?: return Result.success()   // removed since
        if (e.past) return Result.success()
        val job = store.job(e.jobId)
        val label = inputData.getString("label") ?: "soon"
        val where = if (e.place.isNotEmpty()) " (${e.place})" else ""
        Reminders.notify(applicationContext, 1000 + e.id.toInt(), "${e.kind} $label", "${e.title(job)}, ${e.whenText}$where", e.jobId)
        return Result.success()
    }
}
