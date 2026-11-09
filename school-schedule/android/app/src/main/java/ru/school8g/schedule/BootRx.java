package ru.school8g.schedule;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** После перезагрузки / обновления приложения заново ставит напоминания. */
public class BootRx extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        try {
            Notif.scheduleJob(c);
            Notif.scheduleNext(c);
        } catch (Throwable ignored) { }
    }
}
