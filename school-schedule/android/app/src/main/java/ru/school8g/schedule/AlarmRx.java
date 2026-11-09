package ru.school8g.schedule;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Будильник «за 5 минут до урока». */
public class AlarmRx extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        try {
            Notif.fireLesson(c, i.getStringExtra("date"), i.getIntExtra("start", -1));
        } catch (Throwable ignored) { }
        Notif.scheduleNext(c);
    }
}
