package ru.school8g.schedule;

import android.app.job.JobParameters;
import android.app.job.JobService;

/** Раз в ~30 минут тихо проверяет таблицу и шлёт уведомление, если вышло новое расписание. */
public class CheckJob extends JobService {
    @Override
    public boolean onStartJob(final JobParameters params) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try { Notif.check(getApplicationContext()); } catch (Throwable ignored) { }
                jobFinished(params, false);
            }
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
