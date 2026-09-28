import threading, urllib.request, csv, io, time, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

SPREADSHEET_ID = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SELF_URL = "https://school-schedule-4ldw.onrender.com/"
PERM_TZ = timezone(timedelta(hours=5))
CLASS_CODE = "8г"

TIME_TO_NUM = {
    "8:00-8:40": 1, "8:50-9:30": 2, "9:45-10:25": 3, "10:40-11:20": 4,
    "11:35-12:15": 5, "12:25-13:05": 6, "13:15-13:55": 7, "14:00-14:40": 8
}
DAY_SHORT = {"Понедельник": "Пн", "Вторник": "Вт", "Среда": "Ср",
             "Четверг": "Чт", "Пятница": "Пт", "Суббота": "Сб"}
DAY_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]

cache = {"sched": {}, "err": "", "ts": 0}
CACHE_TTL = 300

MANIFEST = '{"name":"Расписание 8Г","short_name":"8Г","start_url":"/","display":"standalone","background_color":"#0a0620","theme_color":"#6366f1","icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a78bfa"/><stop offset="0.5" stop-color="#818cf8"/><stop offset="1" stop-color="#38bdf8"/></linearGradient><linearGradient id="page" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e0e7ff"/></linearGradient></defs><rect width="512" height="512" rx="118" fill="url(#bg)"/><rect x="100" y="150" width="312" height="272" rx="44" fill="url(#page)"/><path d="M100 194 Q100 150 144 150 L368 150 Q412 150 412 194 L412 226 L100 226 Z" fill="#1e1b4b"/><rect x="160" y="100" width="26" height="90" rx="13" fill="#1e1b4b"/><rect x="326" y="100" width="26" height="90" rx="13" fill="#1e1b4b"/><circle cx="173" cy="108" r="6" fill="#a78bfa"/><circle cx="339" cy="108" r="6" fill="#38bdf8"/><circle cx="200" cy="188" r="11" fill="#ffffff"/><circle cx="312" cy="188" r="11" fill="#ffffff"/><text x="256" y="398" font-family="Arial,sans-serif" font-size="196" font-weight="900" fill="#1e1b4b" text-anchor="middle" letter-spacing="-8">8Г</text></svg>'''

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>{self.registration.unregister();caches.keys().then(k=>k.forEach(x=>caches.delete(x)));self.clients.claim();});"


def get_schedule():
    now = time.time()
    if cache["sched"] and now - cache["ts"] < CACHE_TTL:
        return cache["sched"], cache["err"]
    days = {}; err = ""
    try:
        req = urllib.request.urlopen(CSV_URL, timeout=6)
        data = req.read().decode('utf-8')
        reader = list(csv.reader(io.StringIO(data)))
        col = -1
        for row in reader:
            for i, c in enumerate(row):
                if c.replace(" ", "").lower() == CLASS_CODE:
                    col = i; break
            if col != -1: break
        if col != -1:
            cur_day = ""
            days_list = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
            for row in reader:
                if not row: continue
                text = " ".join(row).lower()
                found = None
                for d in days_list:
                    if d in text: found = d.capitalize(); break
                if found:
                    cur_day = found; days.setdefault(cur_day, []); continue
                if not cur_day: continue
                tv = ""
                for c in row:
                    cc = c.strip()
                    if cc in TIME_TO_NUM: tv = cc; break
                if not tv: continue
                if len(row) > col:
                    lv = row[col].strip()
                    if not lv or len(lv) < 2 or ":" in lv: continue
                    if lv.lower() in ["урок", "-", "—", ""]: continue
                    n = TIME_TO_NUM[tv]
                    if n not in [x[1] for x in days[cur_day]]:
                        days[cur_day].append((tv, n, lv))
            for d in days: days[d].sort(key=lambda x: x[1])
            cache["sched"] = days; cache["err"] = ""; cache["ts"] = now
        else:
            err = f"Класс {CLASS_CODE.upper()} не найден"; cache["err"] = err
    except Exception:
        if cache["sched"]: return cache["sched"], ""
        cache["err"] = "Офлайн-режим"
    return cache["sched"], cache["err"]


def live_status(lessons):
    if not lessons: return None
    now = datetime.now(PERM_TZ)
    cur = now.hour * 60 + now.minute
    sec = now.second
    for tv, num, lesson in lessons:
        try:
            s, e = tv.split("-")
            sh, sm = map(int, s.split(":")); eh, em = map(int, e.split(":"))
        except Exception: continue
        ss = sh * 60 + sm; ee = eh * 60 + em
        if ss <= cur < ee:
            total = (ee - ss) * 60
            elapsed = (cur - ss) * 60 + sec
            prog = int(elapsed / max(total, 1) * 100)
            left_sec = total - elapsed
            return {"type": "now", "num": num, "lesson": lesson, "progress": prog,
                    "left_min": left_sec // 60, "left_sec": left_sec % 60, "until": e}
        if cur < ss:
            return {"type": "before", "num": num, "lesson": lesson,
                    "wait": ss - cur, "start": s}
    return None


PAGE = """<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#eef2f7" id="tcMeta">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="8Г">
{refresh_tag}
<title>Расписание 8Г</title>
<style>
:root, [data-theme="light"] {
    --bg: #eef2f7; --card: #ffffff; --text: #0f172a; --muted: #64748b;
    --accent: #6366f1; --accent2: #a855f7;
    --a-soft: rgba(99,102,241,0.10);
    --border: rgba(15,23,42,0.06);
    --green: #10b981; --green-soft: rgba(16,185,129,0.12);
    --orange: #f59e0b; --orange-soft: rgba(245,158,11,0.12);
    --badge-bg: rgba(99,102,241,0.10);
    --badge-color: #6366f1;
}
[data-theme="dark"] {
    --bg: #0b0d12; --card: #1a1f2b; --text: #e8ecf3; --muted: #8b95a8;
    --accent: #818cf8; --accent2: #c084fc;
    --a-soft: rgba(129,140,248,0.14);
    --border: rgba(255,255,255,0.06);
    --green: #34d399; --green-soft: rgba(52,211,153,0.14);
    --orange: #fbbf24; --orange-soft: rgba(251,191,36,0.14);
    --badge-bg: rgba(129,140,248,0.14);
    --badge-color: #c7d2fe;
    color-scheme: dark;
}
[data-theme="cosmic"] {
    --bg: #0a0620; --card: #18103a; --text: #ece6ff; --muted: #a89cc7;
    --accent: #b794f6; --accent2: #7cf5c0;
    --a-soft: rgba(183,148,246,0.14);
    --border: rgba(183,148,246,0.14);
    --green: #7cf5c0; --green-soft: rgba(124,245,192,0.12);
    --orange: #fbbf77; --orange-soft: rgba(251,191,119,0.12);
    --badge-bg: rgba(183,148,246,0.16);
    --badge-color: #d9c8ff;
    color-scheme: dark;
}
[data-theme="forest"] {
    --bg: #e5f2dd; --card: #ffffff; --text: #0f2e1b; --muted: #5f7c68;
    --accent: #059669; --accent2: #84cc16;
    --a-soft: rgba(5,150,105,0.10);
    --border: rgba(5,150,105,0.12);
    --green: #16a34a; --green-soft: rgba(22,163,74,0.12);
    --orange: #ca8a04; --orange-soft: rgba(202,138,4,0.12);
    --badge-bg: rgba(5,150,105,0.12);
    --badge-color: #059669;
}

html { min-height: 100vh; }
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--text); margin: 0;
    padding: 16px 14px 24px;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    -webkit-overflow-scrolling: touch;
    transition: background-color 0.3s, color 0.3s;
}

/* === ФОНЫ (статичные, простые градиенты без декораций) === */
body {
    background-color: var(--bg);
    background-attachment: scroll;
}
[data-theme="light"] body {
    background-image: linear-gradient(180deg, #f1f5fa 0%, #e4ebf3 100%);
}
[data-theme="dark"] body {
    background-image: linear-gradient(180deg, #10131a 0%, #0b0d12 100%);
}
[data-theme="cosmic"] body {
    background-image:
        radial-gradient(1.5px 1.5px at 15% 12%, #ffffff, transparent 55%),
        radial-gradient(1px 1px at 32% 22%, #b794f6, transparent 55%),
        radial-gradient(1.5px 1.5px at 48% 8%, #ffffff, transparent 55%),
        radial-gradient(1.2px 1.2px at 65% 18%, #7cf5c0, transparent 55%),
        radial-gradient(1px 1px at 82% 15%, #ffffff, transparent 55%),
        radial-gradient(1.5px 1.5px at 12% 38%, #b794f6, transparent 55%),
        radial-gradient(1px 1px at 42% 45%, #ffffff, transparent 55%),
        radial-gradient(1.3px 1.3px at 72% 42%, #ffffff, transparent 55%),
        radial-gradient(1px 1px at 25% 62%, #7cf5c0, transparent 55%),
        radial-gradient(1.5px 1.5px at 55% 68%, #ffffff, transparent 55%),
        radial-gradient(1.2px 1.2px at 88% 62%, #b794f6, transparent 55%),
        radial-gradient(1px 1px at 18% 85%, #ffffff, transparent 55%),
        radial-gradient(1.5px 1.5px at 62% 88%, #ffffff, transparent 55%),
        radial-gradient(1px 1px at 85% 92%, #7cf5c0, transparent 55%),
        linear-gradient(180deg, #0a0424 0%, #05021a 55%, #01000a 100%);
}
[data-theme="forest"] body {
    background-image:
        radial-gradient(ellipse 80% 30% at 50% 0%, rgba(255,255,255,0.4), transparent 60%),
        linear-gradient(180deg, #dff0d0 0%, #b8dfa8 35%, #8ec57f 70%, #6ba85c 100%);
}

.container { width: 100%; max-width: 520px; margin: 0 auto; }

/* HEADER */
.header {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 20px; padding: 14px 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    margin-bottom: 12px;
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px;
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-logo {
    width: 46px; height: 46px; border-radius: 14px; flex-shrink: 0;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
}
.brand-title { font-size: 1.05rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }
.brand-sub { font-size: 0.75rem; color: var(--muted); font-weight: 600; margin-top: 2px; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.badge-class {
    background: var(--badge-bg); color: var(--badge-color);
    padding: 8px 14px; border-radius: 12px;
    font-weight: 800; font-size: 0.95rem;
    border: 1px solid var(--border);
}
.icon-btn {
    background: var(--card); color: var(--muted);
    border: 1px solid var(--border);
    width: 42px; height: 42px; border-radius: 13px;
    font-size: 1.1rem; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-family: inherit;
    transition: background 0.15s, color 0.15s;
}
.icon-btn:active { background: var(--a-soft); color: var(--accent); }

/* SETTINGS */
.settings {
    display: grid; grid-template-rows: 0fr;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px; margin-bottom: 0;
    transition: grid-template-rows 0.3s cubic-bezier(0.4,0,0.2,1),
                margin-bottom 0.3s cubic-bezier(0.4,0,0.2,1);
}
.settings.open { grid-template-rows: 1fr; margin-bottom: 12px; }
.settings-inner {
    overflow: hidden; min-height: 0; padding: 0 16px;
    transition: padding 0.3s cubic-bezier(0.4,0,0.2,1);
}
.settings.open .settings-inner { padding: 16px; }
.settings-title {
    font-weight: 800; font-size: 0.74rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em;
    margin-bottom: 10px;
}
.settings-title:not(:first-child) { margin-top: 16px; }
.theme-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.theme-btn {
    padding: 10px 2px; border-radius: 12px;
    border: 2px solid transparent;
    background: var(--bg); color: var(--text);
    font-weight: 700; font-size: 0.62rem;
    cursor: pointer; display: flex; flex-direction: column;
    align-items: center; gap: 4px;
    font-family: inherit;
    transition: background 0.15s, border-color 0.15s;
}
.theme-btn .emoji { font-size: 1.25rem; line-height: 1; }
.theme-btn.active { border-color: var(--accent); background: var(--a-soft); }
.size-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.size-btn {
    padding: 11px; border-radius: 12px;
    border: 2px solid var(--border);
    background: var(--bg); color: var(--text);
    font-weight: 800; cursor: pointer; font-family: inherit;
    transition: background 0.15s, border-color 0.15s;
}
.size-btn[data-size-btn="small"] { font-size: 0.85rem; }
.size-btn[data-size-btn="normal"] { font-size: 1.05rem; }
.size-btn[data-size-btn="large"] { font-size: 1.25rem; }
.size-btn.active { border-color: var(--accent); background: var(--a-soft); }
.toggle-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid var(--border);
}
.toggle-row:last-child { border-bottom: none; }
.toggle-label { font-weight: 700; font-size: 0.88rem; }
.toggle {
    position: relative; width: 46px; height: 26px;
    background: rgba(120,120,120,0.25);
    border-radius: 13px; cursor: pointer;
    transition: background 0.2s;
}
.toggle::after {
    content: ""; position: absolute; top: 2px; left: 2px;
    width: 22px; height: 22px; background: #fff; border-radius: 50%;
    transition: transform 0.2s;
    box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}
.toggle.on { background: var(--accent); }
.toggle.on::after { transform: translateX(20px); }
.install-btn {
    display: flex; align-items: center; gap: 12px;
    width: 100%; padding: 13px 16px; border-radius: 14px;
    border: none;
    background: var(--accent); color: #fff;
    font-weight: 800; cursor: pointer;
    font-family: inherit; text-align: left;
}
.install-btn .ib-emoji { font-size: 1.5rem; }
.install-btn .ib-text { display: block; font-size: 0.95rem; font-weight: 800; }
.install-btn .ib-sub { display: block; font-size: 0.7rem; font-weight: 600; opacity: 0.8; margin-top: 2px; }
.install-tip {
    max-height: 0; overflow: hidden; opacity: 0;
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 12px; padding: 0 14px;
    font-size: 0.83rem; line-height: 1.5;
    color: var(--muted); font-weight: 600;
    transition: max-height 0.3s, opacity 0.2s, padding 0.3s, margin-top 0.3s;
}
.install-tip.show { max-height: 200px; opacity: 1; padding: 12px 14px; margin-top: 8px; }
.installed-badge { color: var(--green); font-weight: 700; font-size: 0.9rem; padding: 8px 0; }

/* LIVE */
.live-banner {
    border-radius: 18px; padding: 14px 16px; margin-bottom: 12px;
    display: flex; align-items: center; gap: 12px;
    border: 1px solid var(--border);
    background: var(--card);
}
.live-banner.now { border-left: 4px solid var(--green); }
.live-banner.before { border-left: 4px solid var(--orange); }
.live-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--green); flex-shrink: 0; }
.live-banner.before .live-dot { background: var(--orange); }
.live-info { flex: 1; min-width: 0; }
.live-label {
    font-size: 0.7rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--green); margin-bottom: 2px;
}
.live-banner.before .live-label { color: var(--orange); }
.live-lesson { font-size: 1.02rem; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.live-time { font-size: 0.76rem; color: var(--muted); font-weight: 700; margin-top: 2px; }
.live-timer { font-weight: 800; color: var(--green); }
.live-banner.before .live-timer { color: var(--orange); }
.progress-bar { height: 4px; border-radius: 2px; background: var(--border); overflow: hidden; margin-top: 7px; }
.progress-fill { height: 100%; background: var(--accent); }

/* TABS */
.tabs {
    display: flex; gap: 5px; margin-bottom: 12px;
    overflow-x: auto; padding: 4px;
    scrollbar-width: none; -ms-overflow-style: none;
    background: var(--card); border-radius: 16px;
    border: 1px solid var(--border);
}
.tabs::-webkit-scrollbar { display: none; }
.tab {
    flex: 1; min-width: 48px; padding: 9px 8px;
    border-radius: 12px; border: none;
    background: transparent; color: var(--muted);
    font-weight: 800; font-size: 0.85rem;
    cursor: pointer; font-family: inherit;
    display: flex; flex-direction: column;
    align-items: center; gap: 2px;
    position: relative;
    transition: background 0.15s, color 0.15s;
}
.tab .tab-day { font-size: 0.62rem; font-weight: 700; opacity: 0.7; }
.tab.active { background: var(--accent); color: white; }
.tab.active .tab-day { opacity: 0.9; }
.tab.today:not(.active)::after {
    content: ""; position: absolute; bottom: 3px; left: 50%;
    transform: translateX(-50%);
    width: 4px; height: 4px; border-radius: 50%;
    background: var(--accent);
}

/* CARDS */
.day-block { display: none; }
.day-block.active { display: block; }
.day-title {
    font-size: 1.08rem; font-weight: 800;
    margin: 4px 4px 10px;
    display: flex; justify-content: space-between; align-items: center;
}
.today-pill {
    font-size: 0.64rem;
    background: var(--a-soft); color: var(--accent);
    padding: 4px 10px; border-radius: 20px;
    font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em;
    border: 1px solid var(--border);
}
.card {
    background: var(--card);
    padding: 13px 15px; margin-bottom: 8px;
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    display: flex; align-items: center; gap: 12px;
    border: 1px solid var(--border);
}
.card.now { background: var(--green-soft); border-color: var(--green); }
.card.next-up { background: var(--orange-soft); border-color: var(--orange); }
.num {
    min-width: 40px; height: 40px;
    border-radius: 12px;
    background: var(--badge-bg); color: var(--badge-color);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 1rem;
    flex-shrink: 0;
    border: 1px solid var(--border);
}
.card.now .num { background: var(--green); color: white; border-color: transparent; }
.left-side { display: flex; flex-direction: column; gap: 2px; flex-grow: 1; min-width: 0; }
.time { font-size: 0.75rem; color: var(--muted); font-weight: 700; }
.lesson { font-size: 0.98rem; font-weight: 800; word-wrap: break-word; }
.now-pill {
    font-size: 0.6rem; background: var(--green); color: #fff;
    padding: 3px 8px; border-radius: 20px;
    font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;
    margin-left: auto; flex-shrink: 0;
}

/* INFO */
.info-box {
    background: var(--card); padding: 28px 20px; border-radius: 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    text-align: center; font-size: 1rem; font-weight: 700;
    color: var(--muted); border: 1px solid var(--border);
    line-height: 1.5;
}
.info-box .big { font-size: 2.1rem; display: block; margin-bottom: 8px; }
.error {
    background: rgba(239,68,68,0.08); color: #ef4444;
    padding: 18px; border-radius: 16px; font-weight: 700;
    text-align: center; border: 1px solid var(--border);
}

/* SIZE */
html.font-small .lesson { font-size: 0.88rem; }
html.font-small .live-lesson { font-size: 0.92rem; }
html.font-large .lesson { font-size: 1.14rem; }
html.font-large .live-lesson { font-size: 1.18rem; }
html.font-large .day-title { font-size: 1.22rem; }
html.compact .card { padding: 9px 13px; margin-bottom: 6px; }
html.compact .num { min-width: 34px; height: 34px; font-size: 0.9rem; }
html.hide-time .time { display: none; }

/* FOOTER */
.sheet-link {
    display: flex; align-items: center; justify-content: center;
    gap: 6px; margin-top: 16px; padding: 12px;
    color: var(--muted); text-decoration: none;
    font-size: 0.82rem; font-weight: 700;
    border-radius: 14px;
    border: 1px dashed var(--border);
    background: var(--card);
}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <div class="brand">
        <div class="brand-logo">📅</div>
        <div class="brand-text">
            <div class="brand-title">Расписание</div>
            <div class="brand-sub">{header_date}</div>
        </div>
    </div>
    <div class="header-right">
        <div class="badge-class">8Г</div>
        <button class="icon-btn" onclick="toggleSettings()">⚙️</button>
    </div>
</div>

<div class="settings" id="settingsPanel">
    <div class="settings-inner">
        <div class="settings-title">🎨 Тема</div>
        <div class="theme-grid">
            <button class="theme-btn" data-theme-btn="light" onclick="setTheme('light')"><span class="emoji">☀️</span>Светлая</button>
            <button class="theme-btn" data-theme-btn="dark" onclick="setTheme('dark')"><span class="emoji">🌙</span>Тёмная</button>
            <button class="theme-btn" data-theme-btn="cosmic" onclick="setTheme('cosmic')"><span class="emoji">🌌</span>Космос</button>
            <button class="theme-btn" data-theme-btn="forest" onclick="setTheme('forest')"><span class="emoji">🌿</span>Лес</button>
        </div>

        <div class="settings-title">🔤 Размер текста</div>
        <div class="size-grid">
            <button class="size-btn" data-size-btn="small" onclick="setSize('small')">A</button>
            <button class="size-btn" data-size-btn="normal" onclick="setSize('normal')">A</button>
            <button class="size-btn" data-size-btn="large" onclick="setSize('large')">A</button>
        </div>

        <div class="settings-title">🔧 Дополнительно</div>
        <div class="toggle-row">
            <div class="toggle-label">Компактный режим</div>
            <div class="toggle" id="tCompact" onclick="toggleCompact()"></div>
        </div>
        <div class="toggle-row">
            <div class="toggle-label">Скрыть время уроков</div>
            <div class="toggle" id="tHideTime" onclick="toggleHideTime()"></div>
        </div>

        <div class="settings-title">📱 Приложение</div>
        <div id="installSection"></div>
    </div>
</div>

{live_banner}
{tabs}
{content}

<a class="sheet-link" href="{sheet_url}" target="_blank" rel="noopener">
    <span>📊</span> Открыть таблицу в Google Sheets
</a>

</div>

<script>
var THEME_COLORS = {light:'#eef2f7', dark:'#0b0d12', cosmic:'#0a0620', forest:'#e5f2dd'};

(function init() {
    var saved = localStorage.getItem('rs_theme') || 'light';
    if (['light','dark','cosmic','forest'].indexOf(saved) === -1) {
        saved = 'light';
        localStorage.setItem('rs_theme', 'light');
    }
    document.documentElement.setAttribute('data-theme', saved);
    var meta = document.getElementById('tcMeta');
    if (meta) meta.setAttribute('content', THEME_COLORS[saved] || '#eef2f7');
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-theme-btn') === saved);
    });
    var size = localStorage.getItem('rs_size') || 'normal';
    if (size === 'small') document.documentElement.classList.add('font-small');
    if (size === 'large') document.documentElement.classList.add('font-large');
    document.querySelectorAll('[data-size-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-size-btn') === size);
    });
    if (localStorage.getItem('rs_compact') === '1') document.documentElement.classList.add('compact');
    if (localStorage.getItem('rs_hide_time') === '1') document.documentElement.classList.add('hide-time');
    document.getElementById('tCompact').classList.toggle('on', localStorage.getItem('rs_compact') === '1');
    document.getElementById('tHideTime').classList.toggle('on', localStorage.getItem('rs_hide_time') === '1');
})();

function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('rs_theme', t);
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-theme-btn') === t);
    });
    var meta = document.getElementById('tcMeta');
    if (meta) meta.setAttribute('content', THEME_COLORS[t] || '#eef2f7');
}
function setSize(s) {
    document.documentElement.classList.remove('font-small','font-large');
    if (s === 'small') document.documentElement.classList.add('font-small');
    if (s === 'large') document.documentElement.classList.add('font-large');
    localStorage.setItem('rs_size', s);
    document.querySelectorAll('[data-size-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-size-btn') === s);
    });
}
function toggleCompact() {
    var on = document.documentElement.classList.toggle('compact');
    localStorage.setItem('rs_compact', on ? '1' : '0');
    document.getElementById('tCompact').classList.toggle('on', on);
}
function toggleHideTime() {
    var on = document.documentElement.classList.toggle('hide-time');
    localStorage.setItem('rs_hide_time', on ? '1' : '0');
    document.getElementById('tHideTime').classList.toggle('on', on);
}
function toggleSettings() {
    document.getElementById('settingsPanel').classList.toggle('open');
}
function showDay(day) {
    document.querySelectorAll('.day-block').forEach(function(el) { el.classList.remove('active'); });
    var t = document.getElementById('day-' + day);
    if (t) t.classList.add('active');
    document.querySelectorAll('.tab').forEach(function(x) {
        x.classList.toggle('active', x.getAttribute('data-day') === day);
    });
}

var deferredPrompt = null;
var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e) { e.preventDefault(); deferredPrompt = e; renderInstall(); });
window.addEventListener('appinstalled', function() { deferredPrompt = null; localStorage.setItem('rs_installed','1'); renderInstall(); });
function renderInstall() {
    var el = document.getElementById('installSection');
    if (!el) return;
    if (isStandalone || localStorage.getItem('rs_installed') === '1') {
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>';
        return;
    }
    el.innerHTML =
        '<button class="install-btn" onclick="doInstall()">' +
            '<span class="ib-emoji">📲</span>' +
            '<span><span class="ib-text">Установить приложение</span>' +
            '<span class="ib-sub">Открыть как нативное</span></span>' +
        '</button>' +
        '<div class="install-tip" id="installTip"></div>';
}
function doInstall() {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function(c) {
            if (c.outcome === 'accepted') localStorage.setItem('rs_installed', '1');
            deferredPrompt = null; renderInstall();
        });
        return;
    }
    var tip = document.getElementById('installTip');
    if (!tip) return;
    if (tip.classList.contains('show')) { tip.classList.remove('show'); return; }
    var ua = navigator.userAgent, text;
    if (/iPhone|iPad|iPod/i.test(ua)) text = '📱 Открой меню «Поделиться» → «На экран Домой»';
    else if (/Android/i.test(ua)) text = '📱 Меню <b>⋮</b> → «Установить приложение»';
    else text = '💻 В Chrome — иконка ⊕ справа в адресной строке';
    tip.innerHTML = text; tip.classList.add('show');
}
renderInstall();
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(function(r) { r.forEach(function(x) { x.unregister(); }); });
}
</script>
</body>
</html>"""


def build_tabs(active, days):
    today_idx = datetime.now(PERM_TZ).weekday()
    h = '<div class="tabs">'
    for i, full in enumerate(DAY_FULL):
        short = DAY_SHORT[full]
        has = full in days and days[full]
        cls = "tab"
        if full == active: cls += " active"
        if i == today_idx: cls += " today"
        h += f'<button class="{cls}" data-day="{full}" onclick="showDay(\'{full}\')">'
        h += f'{short}<span class="tab-day">{"•" if has else "—"}</span></button>'
    h += '</div>'
    return h


def build_live(st):
    if not st: return ""
    if st["type"] == "now":
        return ('<div class="live-banner now"><div class="live-dot"></div>'
            '<div class="live-info"><div class="live-label">Сейчас идёт</div>'
            f'<div class="live-lesson">{st["lesson"]}</div>'
            f'<div class="live-time">Осталось <span class="live-timer">{st["left_min"]}:{st["left_sec"]:02d}</span> · до {st["until"]}</div>'
            f'<div class="progress-bar"><div class="progress-fill" style="width:{st["progress"]}%"></div></div>'
            '</div></div>')
    if st["type"] == "before":
        return ('<div class="live-banner before"><div class="live-dot"></div>'
            '<div class="live-info"><div class="live-label">Скоро урок</div>'
            f'<div class="live-lesson">{st["lesson"]}</div>'
            f'<div class="live-time">Через <span class="live-timer">{st["wait"]} мин</span> · в {st["start"]}</div>'
            '</div></div>')
    return ""


def build_content(days, active, err, st):
    if err and not days:
        return f"<div class='error'>{err}</div>"
    today_full = DAY_FULL[datetime.now(PERM_TZ).weekday()] if datetime.now(PERM_TZ).weekday() < 6 else ""
    h = ""
    for full in DAY_FULL:
        lessons = days.get(full, [])
        cls = " active" if full == active else ""
        h += f'<div class="day-block{cls}" id="day-{full}">'
        if full == today_full:
            h += f'<div class="day-title">{full}<span class="today-pill">✨ Сегодня</span></div>'
        else:
            h += f'<div class="day-title">{full}</div>'
        if not lessons:
            h += '<div class="info-box"><span class="big">📭</span>Нет уроков на этот день</div>'
        else:
            for tv, num, lesson in lessons:
                cc = "card"; pill = ""
                if full == today_full and st and st["type"] == "now" and num == st["num"]:
                    cc += " now"; pill = '<span class="now-pill">сейчас</span>'
                elif full == today_full and st and st["type"] == "before" and num == st["num"]:
                    cc += " next-up"
                h += f'<div class="{cc}"><div class="num">{num}</div>'
                h += f'<div class="left-side"><div class="time">{tv}</div>'
                h += f'<div class="lesson">{lesson}</div></div>'
                h += pill + '</div>'
        h += '</div>'
    return h


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, ct, body):
        self.send_response(200)
        self.send_header("Content-type", ct)
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            path = self.path.split("?")[0]
            if path == "/manifest.json":
                self._send("application/manifest+json; charset=utf-8", MANIFEST.encode()); return
            if path == "/sw.js":
                self._send("application/javascript; charset=utf-8", SW_JS.encode()); return
            if path == "/icon.svg":
                self._send("image/svg+xml; charset=utf-8", ICON_SVG.encode()); return

            now = datetime.now(PERM_TZ)
            hour, minute = now.hour, now.minute
            wi = now.weekday()
            cur_day = DAY_FULL[wi] if wi < 6 else "Суббота"
            is_weekend = wi >= 5
            refresh = "<meta http-equiv='refresh' content='900'>" if not (1 <= hour < 5) else ""

            days, err = get_schedule()
            months = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"]
            header_date = f"{cur_day}, {now.day} {months[now.month-1]}"

            today_lessons = days.get(cur_day, [])
            school_over = (hour > 14 or (hour == 14 and minute >= 40) or is_weekend or not today_lessons)
            if school_over and wi < 5:
                ni = wi + 1
                if ni < 6:
                    tmr = DAY_FULL[ni]
                    active = tmr if days.get(tmr) else cur_day
                else:
                    active = cur_day
            else:
                active = cur_day
            if active not in DAY_FULL: active = cur_day
            if not days.get(active) and days.get(cur_day): active = cur_day

            st = live_status(today_lessons) if not is_weekend else None
            live_html = build_live(st)
            tabs_html = build_tabs(active, days)
            content = build_content(days, active, err, st)

            html = PAGE
            html = html.replace("{refresh_tag}", refresh)
            html = html.replace("{header_date}", header_date)
            html = html.replace("{live_banner}", live_html)
            html = html.replace("{tabs}", tabs_html)
            html = html.replace("{content}", content)
            html = html.replace("{sheet_url}", SHEET_URL)

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        except Exception as e:
            try:
                self.send_response(500); self.end_headers()
                self.wfile.write(f"Error: {e}".encode())
            except Exception: pass


def keep_alive():
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(SELF_URL, timeout=30)
            print(f"[keep-alive] {datetime.now(PERM_TZ).strftime('%H:%M')}")
        except Exception: pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Сервер запущен на порту {port}")
    threading.Thread(target=keep_alive, daemon=True).start()
    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()
