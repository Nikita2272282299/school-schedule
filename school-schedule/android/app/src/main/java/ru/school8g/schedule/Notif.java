package ru.school8g.schedule;

import android.Manifest;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Уведомления: новое/изменённое расписание и «за 5 минут до урока». */
final class Notif {
    static final String SHEET = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE";
    static final String CH_NEW = "schedule", CH_LES = "lessons";
    static final int JOB_ID = 81, ALARM_RC = 82;

    static SharedPreferences p(Context c) {
        return c.getSharedPreferences("notif", Context.MODE_PRIVATE);
    }

    static boolean onNew(Context c) { return p(c).getBoolean("on_new", true); }

    static boolean onLessons(Context c) { return p(c).getBoolean("on_lessons", true); }

    static int piFlags() {
        return PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0);
    }

    static void channels(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        NotificationChannel a = new NotificationChannel(CH_NEW, "Новое расписание", NotificationManager.IMPORTANCE_DEFAULT);
        a.setDescription("Когда в таблице появляется или меняется расписание");
        NotificationChannel b = new NotificationChannel(CH_LES, "Перед уроком", NotificationManager.IMPORTANCE_HIGH);
        b.setDescription("За 5 минут до начала урока");
        nm.createNotificationChannel(a);
        nm.createNotificationChannel(b);
    }

    static boolean canPost(Context c) {
        if (Build.VERSION.SDK_INT >= 33 && c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return false;
        if (Build.VERSION.SDK_INT >= 24) {
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            return nm == null || nm.areNotificationsEnabled();
        }
        return true;
    }

    @SuppressWarnings("deprecation")
    static void post(Context c, String ch, int id, String title, String text) {
        if (!canPost(c)) return;
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        channels(c);
        Intent open = new Intent(c, MainActivity.class);
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(c, id, open, piFlags());
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, ch) : new Notification.Builder(c);
        b.setSmallIcon(R.drawable.ic_stat)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(pi)
                .setAutoCancel(true)
                .setColor(Color.parseColor("#8B5CF6"))
                .setShowWhen(true);
        if (Build.VERSION.SDK_INT < 26) {
            b.setPriority(CH_LES.equals(ch) ? Notification.PRIORITY_HIGH : Notification.PRIORITY_DEFAULT);
            b.setDefaults(Notification.DEFAULT_ALL);
        }
        try { nm.notify(id, b.build()); } catch (Throwable ignored) { }
    }

    static void test(Context c) {
        post(c, CH_NEW, 3000, "🔔 Уведомления работают!", "Так будут приходить новости о расписании и напоминания за 5 минут до урока.");
    }

    static String fetch() {
        String base = "https://docs.google.com/spreadsheets/d/" + SHEET;
        long ts = System.currentTimeMillis();
        String[] urls = {base + "/export?format=csv&t=" + ts, base + "/gviz/tq?tqx=out:csv&headers=0&t=" + ts};
        for (String u : urls) {
            HttpURLConnection h = null;
            try {
                h = (HttpURLConnection) new URL(u).openConnection();
                h.setConnectTimeout(15000);
                h.setReadTimeout(20000);
                h.setInstanceFollowRedirects(true);
                h.setUseCaches(false);
                if (h.getResponseCode() != 200) continue;
                InputStream in = h.getInputStream();
                ByteArrayOutputStream o = new ByteArrayOutputStream();
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0) o.write(buf, 0, n);
                in.close();
                String t = o.toString("UTF-8");
                if (t.trim().startsWith("<")) continue;
                if (t.length() > 50) return t;
            } catch (Throwable ignored) {
            } finally {
                if (h != null) h.disconnect();
            }
        }
        return null;
    }

    static JSONObject readDays(SharedPreferences sp) {
        try { return new JSONObject(sp.getString("days", "{}")); } catch (Exception e) { return new JSONObject(); }
    }

    static JSONArray pack(Sheet.Day d) {
        JSONArray a = new JSONArray();
        for (Sheet.Lesson l : d.lessons) {
            JSONArray x = new JSONArray();
            x.put(l.num);
            x.put(l.start);
            x.put(l.end);
            x.put(l.raw);
            a.put(x);
        }
        return a;
    }

    static JSONObject future(JSONObject all, String today) {
        JSONObject o = new JSONObject();
        List<String> keys = new ArrayList<>();
        Iterator<String> it = all.keys();
        while (it.hasNext()) keys.add(it.next());
        for (String k : keys) {
            if (k.compareTo(today) < 0) continue;
            try { o.put(k, all.get(k)); } catch (Exception ignored) { }
        }
        return o;
    }

    /** Фоновая проверка таблицы. */
    static synchronized void check(Context c) {
        if (!onNew(c) && !onLessons(c)) return;
        SharedPreferences sp = p(c);
        String txt = fetch();
        if (txt == null) return;
        Calendar now = Calendar.getInstance();
        String cls = sp.getString("cls", "8Г");
        Map<String, Sheet.Day> days = Sheet.parse(txt, cls, now);
        if (days.isEmpty()) return;
        String today = Sheet.iso(now);
        boolean seeded = sp.getBoolean("seeded", false);
        SharedPreferences.Editor e = sp.edit();
        JSONObject all = readDays(sp);
        for (Sheet.Day d : days.values()) {
            String sig = d.sig();
            String old = sp.getString("sig_" + d.date, null);
            e.putString("sig_" + d.date, sig);
            try { all.put(d.date, pack(d)); } catch (Exception ignored) { }
            if (!seeded || sig.equals(old) || d.date.compareTo(today) < 0 || !onNew(c)) continue;
            String title = (old == null ? "📅 Вышло расписание на " : "✏️ Расписание изменилось на ") + human(d.date, now);
            post(c, CH_NEW, 1000 + (d.date.hashCode() & 0xfff), title, summary(d, cls));
        }
        e.putBoolean("seeded", true);
        e.putString("days", future(all, today).toString());
        e.commit();
        scheduleNext(c);
    }

    static String human(String iso, Calendar now) {
        Calendar t = Sheet.midnight(now);
        if (iso.equals(Sheet.iso(t))) return "сегодня";
        t.add(Calendar.DAY_OF_MONTH, 1);
        if (iso.equals(Sheet.iso(t))) return "завтра";
        try {
            String[] a = iso.split("-");
            return Integer.parseInt(a[2]) + " " + Sheet.MONTHS[Integer.parseInt(a[1]) - 1];
        } catch (Exception x) {
            return iso;
        }
    }

    static String plural(int n) {
        int m = n % 10, h = n % 100;
        if (m == 1 && h != 11) return "урок";
        if (m >= 2 && m <= 4 && (h < 12 || h > 14)) return "урока";
        return "уроков";
    }

    static String summary(Sheet.Day d, String cls) {
        StringBuilder b = new StringBuilder();
        int n = 0;
        for (Sheet.Lesson l : d.lessons) {
            if (l.raw.isEmpty()) continue;
            n++;
            if (b.length() > 0) b.append(" · ");
            b.append(l.title.isEmpty() ? l.raw : l.title);
        }
        return cls + " · " + n + " " + plural(n) + ": " + b;
    }

    static String hm(int m) {
        return String.format(Locale.US, "%d:%02d", m / 60, m % 60);
    }

    static Calendar parseIso(String s) {
        try {
            String[] a = s.split("-");
            Calendar c = Calendar.getInstance();
            c.clear();
            c.set(Integer.parseInt(a[0]), Integer.parseInt(a[1]) - 1, Integer.parseInt(a[2]));
            return c;
        } catch (Exception e) {
            return null;
        }
    }

    /** Ставит будильник на ближайший урок (за 5 минут). */
    static void scheduleNext(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        Intent i = new Intent(c, AlarmRx.class);
        try { am.cancel(PendingIntent.getBroadcast(c, ALARM_RC, i, piFlags())); } catch (Throwable ignored) { }
        if (!onLessons(c)) return;
        JSONObject all = readDays(p(c));
        long nowMs = System.currentTimeMillis();
        long best = Long.MAX_VALUE;
        String bd = null;
        int bs = -1;
        Iterator<String> it = all.keys();
        while (it.hasNext()) {
            String date = it.next();
            JSONArray ls = all.optJSONArray(date);
            Calendar base = parseIso(date);
            if (ls == null || base == null) continue;
            for (int j = 0; j < ls.length(); j++) {
                JSONArray l = ls.optJSONArray(j);
                if (l == null) continue;
                int st = l.optInt(1, -1);
                String raw = l.optString(3, "");
                if (st < 0 || raw.trim().isEmpty()) continue;
                long at = base.getTimeInMillis() + (st - 5) * 60000L;
                if (at > nowMs + 5000 && at < best) {
                    best = at;
                    bd = date;
                    bs = st;
                }
            }
        }
        if (bd == null) return;
        i.putExtra("date", bd);
        i.putExtra("start", bs);
        PendingIntent pi = PendingIntent.getBroadcast(c, ALARM_RC, i, piFlags());
        try {
            if (Build.VERSION.SDK_INT >= 31 && !am.canScheduleExactAlarms()) am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, best, pi);
            else if (Build.VERSION.SDK_INT >= 23) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, best, pi);
            else am.setExact(AlarmManager.RTC_WAKEUP, best, pi);
        } catch (Throwable t) {
            try { am.set(AlarmManager.RTC_WAKEUP, best, pi); } catch (Throwable ignored) { }
        }
    }

    static void fireLesson(Context c, String date, int start) {
        if (date == null || start < 0 || !onLessons(c)) return;
        JSONArray ls = readDays(p(c)).optJSONArray(date);
        Calendar base = parseIso(date);
        if (ls == null || base == null) return;
        long startMs = base.getTimeInMillis() + start * 60000L;
        if (System.currentTimeMillis() > startMs + 60000L) return;
        for (int j = 0; j < ls.length(); j++) {
            JSONArray a = ls.optJSONArray(j);
            if (a == null || a.optInt(1, -1) != start) continue;
            Sheet.Lesson l = new Sheet.Lesson();
            l.num = a.optString(0, "");
            l.start = start;
            l.end = a.optInt(2, -1);
            l.raw = a.optString(3, "").trim();
            if (l.raw.isEmpty()) return;
            Sheet.pretty(l);
            String text = (l.num.isEmpty() ? "" : l.num + " урок · ") + hm(l.start) + (l.end > 0 ? "–" + hm(l.end) : "") + (l.room.isEmpty() ? "" : " · каб. " + l.room);
            post(c, CH_LES, 2000, "⏰ Через 5 минут: " + (l.title.isEmpty() ? l.raw : l.title), text);
            return;
        }
    }

    /** Периодическая проверка раз в 30 минут (когда есть интернет). */
    static void scheduleJob(Context c) {
        JobScheduler js = (JobScheduler) c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (js == null) return;
        if (!onNew(c) && !onLessons(c)) {
            js.cancel(JOB_ID);
            return;
        }
        if (Build.VERSION.SDK_INT >= 24 && js.getPendingJob(JOB_ID) != null) return;
        JobInfo.Builder b = new JobInfo.Builder(JOB_ID, new ComponentName(c, CheckJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .setPeriodic(30 * 60 * 1000L);
        try { js.schedule(b.build()); } catch (Throwable ignored) { }
    }

    /** Сменили класс — начинаем с чистого листа, чтобы не спамить. */
    static void setClass(Context c, String cls) {
        SharedPreferences sp = p(c);
        if (cls == null || cls.trim().isEmpty() || cls.equals(sp.getString("cls", null))) return;
        SharedPreferences.Editor e = sp.edit();
        for (String k : sp.getAll().keySet()) if (k.startsWith("sig_")) e.remove(k);
        e.putString("cls", cls.trim());
        e.putBoolean("seeded", false);
        e.putString("days", "{}");
        e.commit();
    }
}
