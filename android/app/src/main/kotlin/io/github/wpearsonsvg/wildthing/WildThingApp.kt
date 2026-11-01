package io.github.wpearsonsvg.wildthing

import android.app.Application
import io.github.wpearsonsvg.wildthing.data.Store
import io.github.wpearsonsvg.wildthing.work.Reminders

class WildThingApp : Application() {
    val store: Store by lazy { Store(this) }

    override fun onCreate() {
        super.onCreate()
        Reminders.createChannel(this)
        Reminders.scheduleDailyCheck(this)
    }
}
