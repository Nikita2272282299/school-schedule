package ru.school8g.schedule;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Разбор Google-таблицы (та же логика, что и на сайте). */
final class Sheet {
    static final class Lesson {
        String num = "", title = "", room = "", raw = "";
        int start = -1, end = -1;
    }

    static final class Day {
        String date;
        List<Lesson> lessons = new ArrayList<>();

        String sig() {
            StringBuilder b = new StringBuilder();
            for (Lesson l : lessons) b.append(l.num).append('|').append(l.start).append('|').append(l.raw).append('\n');
            return Integer.toHexString(b.toString().hashCode()) + ":" + b.length();
        }
    }

    static final String[] MONTHS = {"января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"};
    static final String[] WD = {"воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"};
    static final String[] BELLS = {"", "8:00-8:40", "8:50-9:30", "9:45-10:25", "10:40-11:20", "11:35-12:15", "12:25-13:05", "13:15-13:55", "14:00-14:40", "14:55-15:35", "15:50-16:30"};
    static final Pattern MON_RE = Pattern.compile("(\\d{1,2})\\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)");
    static final Pattern DOT_RE = Pattern.compile("^(\\d{1,2})\\.(\\d{1,2})(?:\\.(\\d{2,4}))?$");
    static final Pattern TIME_RE = Pattern.compile("(\\d{1,2})[.:](\\d{2})\\s*[-\u2013\u2014]\\s*(\\d{1,2})[.:](\\d{2})");
    static final Pattern CLASS_RE = Pattern.compile("^\\d{1,2}[А-ЯЁ]$");
    static final Pattern NUM_RE = Pattern.compile("^\\d{1,2}$");
    static final Pattern EMPTY_RE = Pattern.compile("^[-\u2013\u2014\\s]*$");
    static final Pattern ROOM_RE = Pattern.compile("^(.+?)\\s*(\\d{2,4})?$");
    static final Pattern DIG_RE = Pattern.compile("\\d{2,4}");
    static final Locale RU = Locale.forLanguageTag("ru");

    static String norm(String c) {
        return c == null ? "" : c.replaceAll("\\s+", "").toUpperCase(RU);
    }

    static String cell(List<String> r, int j) {
        return j >= 0 && j < r.size() && r.get(j) != null ? r.get(j) : "";
    }

    static List<List<String>> csv(String t) {
        List<List<String>> rows = new ArrayList<>();
        List<String> row = new ArrayList<>();
        StringBuilder f = new StringBuilder();
        boolean q = false;
        int n = t.length();
        for (int i = 0; i < n; i++) {
            char c = t.charAt(i);
            if (q) {
                if (c == '"') {
                    if (i + 1 < n && t.charAt(i + 1) == '"') { f.append('"'); i++; } else q = false;
                } else f.append(c);
            } else if (c == '"') q = true;
            else if (c == ',') { row.add(f.toString()); f.setLength(0); }
            else if (c == '\n' || c == '\r') {
                if (c == '\r' && i + 1 < n && t.charAt(i + 1) == '\n') i++;
                row.add(f.toString()); rows.add(row); row = new ArrayList<>(); f.setLength(0);
            } else f.append(c);
        }
        if (f.length() > 0 || !row.isEmpty()) { row.add(f.toString()); rows.add(row); }
        return rows;
    }

    static int[] time(String s) {
        if (s == null) return null;
        Matcher m = TIME_RE.matcher(s);
        if (!m.find()) return null;
        return new int[]{Integer.parseInt(m.group(1)) * 60 + Integer.parseInt(m.group(2)), Integer.parseInt(m.group(3)) * 60 + Integer.parseInt(m.group(4))};
    }

    static String iso(Calendar c) {
        return String.format(Locale.US, "%04d-%02d-%02d", c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1, c.get(Calendar.DAY_OF_MONTH));
    }

    static Calendar midnight(Calendar now) {
        Calendar c = Calendar.getInstance();
        c.clear();
        c.set(now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH));
        return c;
    }

    static String closestDate(int day, int month, Calendar now) {
        Calendar t0 = midnight(now);
        Calendar best = null;
        int y0 = now.get(Calendar.YEAR);
        for (int y = y0 - 1; y <= y0 + 1; y++) {
            Calendar x = Calendar.getInstance();
            x.clear();
            x.set(y, month, day);
            if (x.get(Calendar.MONTH) != month) continue;
            if (best == null || Math.abs(x.getTimeInMillis() - t0.getTimeInMillis()) < Math.abs(best.getTimeInMillis() - t0.getTimeInMillis())) best = x;
        }
        return best == null ? null : iso(best);
    }

    static String closestWeekday(int wd, Calendar now) {
        int[] offs = {0, 1, -1, 2, -2, 3, -3};
        for (int o : offs) {
            Calendar x = midnight(now);
            x.add(Calendar.DAY_OF_MONTH, o);
            if (x.get(Calendar.DAY_OF_WEEK) - 1 == wd) return iso(x);
        }
        return null;
    }

    static String dayHeader(List<String> r, Calendar now) {
        if (r == null) return null;
        for (int i = 0; i < Math.min(4, r.size()); i++) if (TIME_RE.matcher(cell(r, i)).find()) return null;
        String fd = null;
        int fw = -1;
        for (String c : r) {
            String low = c == null ? "" : c.toLowerCase(RU).trim();
            if (low.isEmpty() || low.length() > 40) continue;
            Matcher m = MON_RE.matcher(low);
            if (m.find() && fd == null) {
                int mi = -1;
                for (int k = 0; k < 12; k++) if (MONTHS[k].equals(m.group(2))) mi = k;
                fd = closestDate(Integer.parseInt(m.group(1)), mi, now);
            }
            m = DOT_RE.matcher(low);
            if (m.matches() && fd == null) {
                int d = Integer.parseInt(m.group(1)), mo = Integer.parseInt(m.group(2));
                if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31) fd = closestDate(d, mo - 1, now);
            }
            for (int i = 0; i < 7; i++) if (low.equals(WD[i]) || low.startsWith(WD[i] + ",")) fw = i;
        }
        if (fd != null) return fd;
        return fw >= 0 ? closestWeekday(fw, now) : null;
    }

    static boolean isHeader(List<String> r) {
        int n = 0;
        for (String c : r) if (CLASS_RE.matcher(norm(c)).matches()) n++;
        return n >= 3;
    }

    static boolean blank(List<String> r) {
        for (String c : r) if (c != null && !c.trim().isEmpty()) return false;
        return true;
    }

    static String clean(String raw) {
        String s = raw == null ? "" : raw.replaceAll("\\s+", " ").trim();
        return EMPTY_RE.matcher(s).matches() ? "" : s;
    }

    static Map<String, Day> parse(String text, String cls, Calendar now) {
        List<List<String>> rows = csv(text);
        Map<String, Day> out = new LinkedHashMap<>();
        String target = norm(cls);
        String cur = null;
        for (int i = 0; i < rows.size(); i++) {
            List<String> r = rows.get(i);
            String dh = dayHeader(r, now);
            if (dh != null) cur = dh;
            if (!isHeader(r)) continue;
            if (cur == null) cur = iso(now);
            int fc = r.size(), col = -1;
            for (int j = 0; j < r.size(); j++) {
                String n = norm(r.get(j));
                if (CLASS_RE.matcher(n).matches()) {
                    if (j < fc) fc = j;
                    if (col < 0 && n.equals(target)) col = j;
                }
            }
            Day day = new Day();
            day.date = cur;
            for (int k = i + 1; k < rows.size(); k++) {
                List<String> q = rows.get(k);
                if (isHeader(q) || dayHeader(q, now) != null) break;
                String num = "";
                int[] tm = null;
                for (int j = 0; j < Math.max(1, fc); j++) {
                    String c = cell(q, j).trim();
                    if (num.isEmpty() && NUM_RE.matcher(c).matches()) num = c;
                    if (tm == null) tm = time(c);
                }
                if (tm == null && num.isEmpty()) {
                    if (!day.lessons.isEmpty() && blank(q)) break;
                    continue;
                }
                if (tm == null) {
                    int b = Integer.parseInt(num);
                    if (b >= 1 && b < BELLS.length) tm = time(BELLS[b]);
                }
                Lesson l = new Lesson();
                l.num = num;
                if (tm != null) { l.start = tm[0]; l.end = tm[1]; }
                l.raw = col >= 0 ? clean(cell(q, col)) : "";
                pretty(l);
                day.lessons.add(l);
            }
            if (col < 0) continue;
            while (!day.lessons.isEmpty() && day.lessons.get(day.lessons.size() - 1).raw.isEmpty()) day.lessons.remove(day.lessons.size() - 1);
            while (!day.lessons.isEmpty() && day.lessons.get(0).raw.isEmpty()) day.lessons.remove(0);
            Day old = out.get(cur);
            if (!day.lessons.isEmpty() && (old == null || old.lessons.isEmpty())) out.put(cur, day);
        }
        return out;
    }

    static void pretty(Lesson l) {
        String s = l.raw;
        if (s.isEmpty()) return;
        if (s.length() > 30 || s.contains("(") || s.contains(")") || s.contains(",")) { l.title = s; return; }
        String first = s.split("/")[0].trim();
        Matcher m = ROOM_RE.matcher(first);
        String word = first;
        if (m.matches()) {
            word = m.group(1).trim();
            if (m.group(2) != null) l.room = m.group(2);
        }
        if (l.room.isEmpty()) {
            Matcher d = DIG_RE.matcher(s);
            if (d.find()) l.room = d.group();
        }
        String w = word.split(" ")[0];
        l.title = w.isEmpty() ? s : w.substring(0, 1).toUpperCase(RU) + w.substring(1);
    }
}
