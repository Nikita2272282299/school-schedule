import threading, urllib.request, csv, io, time, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

SPREADSHEET_ID = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SELF_URL = "https://school-schedule-4ldw.onrender.com/"
PERM_TZ = timezone(timedelta(hours=5))

TIME_TO_NUM = {
    "8:00-8:40": 1, "8:50-9:30": 2, "9:45-10:25": 3, "10:40-11:20": 4,
    "11:35-12:15": 5, "12:25-13:05": 6, "13:15-13:55": 7, "14:00-14:40": 8
}
DAY_SHORT = {"Понедельник": "Пн", "Вторник": "Вт", "Среда": "Ср",
             "Четверг": "Чт", "Пятница": "Пт", "Суббота": "Сб"}
DAY_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]

cache = {"days_schedule": {}, "error_msg": "", "last_update": 0}
CACHE_TTL = 300

MANIFEST = '{"name":"Расписание 8Г","short_name":"8Г","start_url":"/","display":"standalone","background_color":"#0a0620","theme_color":"#6366f1","icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6366f1"/><stop offset="0.5" stop-color="#8b5cf6"/><stop offset="1" stop-color="#a855f7"/></linearGradient><linearGradient id="glow" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity="0.35"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient></defs><rect width="512" height="512" rx="118" fill="url(#bg)"/><rect width="512" height="512" rx="118" fill="url(#glow)"/><rect x="98" y="128" width="316" height="288" rx="36" fill="#ffffff"/><rect x="98" y="128" width="316" height="76" rx="36" fill="#1e1b4b"/><rect x="98" y="176" width="316" height="28" fill="#1e1b4b"/><circle cx="168" cy="166" r="12" fill="#ffffff"/><circle cx="344" cy="166" r="12" fill="#ffffff"/><rect x="152" y="86" width="22" height="72" rx="11" fill="#1e1b4b"/><rect x="338" y="86" width="22" height="72" rx="11" fill="#1e1b4b"/><text x="256" y="358" font-family="Arial,Helvetica,sans-serif" font-size="180" font-weight="900" fill="#1e1b4b" text-anchor="middle" letter-spacing="-8">8Г</text></svg>'''

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>{self.registration.unregister();caches.keys().then(k=>k.forEach(x=>caches.delete(x)));self.clients.claim();});"


def get_schedule():
    current_time = time.time()
    if cache["days_schedule"] and (current_time - cache["last_update"] < CACHE_TTL):
        return cache["days_schedule"], cache["error_msg"]
    days_schedule = {}
    error_msg = ""
    try:
        req = urllib.request.urlopen(CSV_URL, timeout=4)
        data = req.read().decode('utf-8')
        reader = list(csv.reader(io.StringIO(data)))
        col_index = -1
        for row in reader:
            for c_idx, cell in enumerate(row):
                if cell.replace(" ", "").lower() == "8г":
                    col_index = c_idx
                    break
            if col_index != -1:
                break
        if col_index != -1:
            current_day = ""
            days_list = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
            for row in reader:
                if not row:
                    continue
                row_text = " ".join(row).lower()
                found_day = None
                for d in days_list:
                    if d in row_text:
                        found_day = d.capitalize()
                        break
                if found_day:
                    current_day = found_day
                    if current_day not in days_schedule:
                        days_schedule[current_day] = []
                    continue
                if not current_day:
                    continue
                time_val = ""
                for cell in row:
                    cell_clean = cell.strip()
                    if cell_clean in TIME_TO_NUM:
                        time_val = cell_clean
                        break
                if not time_val:
                    continue
                if len(row) > col_index:
                    lesson_val = row[col_index].strip()
                    if not lesson_val or len(lesson_val) < 2 or ":" in lesson_val:
                        continue
                    if lesson_val.lower() in ["урок", "-", "—", ""]:
                        continue
                    lesson_num = TIME_TO_NUM[time_val]
                    existing_nums = [n for t, n, l in days_schedule[current_day]]
                    if lesson_num not in existing_nums:
                        days_schedule[current_day].append((time_val, lesson_num, lesson_val))
            for d in days_schedule:
                days_schedule[d].sort(key=lambda x: x[1])
            cache["days_schedule"] = days_schedule
            cache["error_msg"] = ""
            cache["last_update"] = current_time
        else:
            error_msg = "Класс 8Г не найден в таблице."
            cache["error_msg"] = error_msg
    except Exception:
        if cache["days_schedule"]:
            return cache["days_schedule"], ""
        cache["error_msg"] = "Офлайн-режим (нет сети)"
    return cache["days_schedule"], cache["error_msg"]


def get_live_status(today_lessons):
    """Определяет текущий урок / перемену / до первого урока."""
    if not today_lessons:
        return None
    now = datetime.now(PERM_TZ)
    cur = now.hour * 60 + now.minute
    for i, (time_str, num, lesson) in enumerate(today_lessons):
        try:
            start, end = time_str.split("-")
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
        except Exception:
            continue
        s = sh * 60 + sm
        e = eh * 60 + em
        if s <= cur < e:
            prog = int((cur - s) / max(e - s, 1) * 100)
            left = e - cur
            return {"type": "now", "num": num, "lesson": lesson,
                    "progress": prog, "left": left, "until": end}
        if cur < s:
            return {"type": "before", "num": num, "lesson": lesson,
                    "wait": s - cur, "start": start}
    return None


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f0f4f8" id="themeColorMeta">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="8Г">
{refresh_tag}
<title>Расписание 8Г</title>
<style>
:root, [data-theme="light"] {
    --bg: #eef2f7; --bg2: #e0e7f0; --card: #ffffff; --card-hover: #fafbff;
    --text: #0f172a; --muted: #64748b; --accent: #6366f1; --accent2: #a855f7;
    --accent-soft: rgba(99,102,241,0.10); --accent-soft2: rgba(168,85,247,0.10);
    --border: rgba(15,23,42,0.06); --shadow: 0 4px 20px rgba(15,23,42,0.06);
    --shadow-hover: 0 8px 32px rgba(99,102,241,0.15);
    --green: #10b981; --green-soft: rgba(16,185,129,0.12);
    --orange: #f59e0b; --orange-soft: rgba(245,158,11,0.12);
    --danger: #ef4444;
}
[data-theme="dark"] {
    --bg: #0b0d12; --bg2: #131720; --card: #1a1f2b; --card-hover: #202633;
    --text: #e8ecf3; --muted: #8b95a8; --accent: #818cf8; --accent2: #c084fc;
    --accent-soft: rgba(129,140,248,0.14); --accent-soft2: rgba(192,132,252,0.14);
    --border: rgba(255,255,255,0.06); --shadow: 0 4px 20px rgba(0,0,0,0.4);
    --shadow-hover: 0 8px 32px rgba(129,140,248,0.25);
    --green: #34d399; --green-soft: rgba(52,211,153,0.14);
    --orange: #fbbf24; --orange-soft: rgba(251,191,36,0.14);
    --danger: #f87171;
    color-scheme: dark;
}
[data-theme="cosmic"] {
    --bg: #06021a; --bg2: #0f0730; --card: rgba(30,20,65,0.72); --card-hover: rgba(40,28,80,0.85);
    --text: #ece6ff; --muted: #a89cc7; --accent: #b794f6; --accent2: #7cf5c0;
    --accent-soft: rgba(183,148,246,0.16); --accent-soft2: rgba(124,245,192,0.12);
    --border: rgba(183,148,246,0.14); --shadow: 0 8px 32px rgba(120,60,220,0.25);
    --shadow-hover: 0 12px 40px rgba(183,148,246,0.4);
    --green: #7cf5c0; --green-soft: rgba(124,245,192,0.14);
    --orange: #fbbf77; --orange-soft: rgba(251,191,119,0.14);
    --danger: #ff8ab5;
    color-scheme: dark;
}
html { min-height: 100%; background: var(--bg); }
[data-theme="cosmic"] html, html[data-theme="cosmic"] { background: #06021a; }
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); margin: 0;
    padding: 20px 14px 40px; display: flex; justify-content: center;
    min-height: 100vh; -webkit-font-smoothing: antialiased;
    transition: background 0.4s ease, color 0.3s ease;
    position: relative; overflow-x: hidden;
}
[data-theme="cosmic"] body::before {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background:
        radial-gradient(2px 2px at 20% 30%, #fff, transparent 60%),
        radial-gradient(1px 1px at 60% 70%, #b794f6, transparent 60%),
        radial-gradient(1.5px 1.5px at 80% 20%, #7cf5c0, transparent 60%),
        radial-gradient(1px 1px at 35% 85%, #fff, transparent 60%),
        radial-gradient(2px 2px at 90% 50%, #fff, transparent 60%),
        radial-gradient(1px 1px at 10% 60%, #b794f6, transparent 60%),
        radial-gradient(circle at 30% 15%, rgba(140,60,240,0.25), transparent 55%),
        radial-gradient(circle at 75% 85%, rgba(60,180,240,0.15), transparent 55%);
    opacity: 0.9; animation: stars 8s ease-in-out infinite alternate;
}
@keyframes stars { from { opacity: 0.6; } to { opacity: 1; } }
.container { width: 100%; max-width: 520px; position: relative; z-index: 1; }

/* === HEADER === */
.header {
    background: var(--card); border: 1px solid var(--border); border-radius: 24px;
    padding: 16px 20px; box-shadow: var(--shadow); margin-bottom: 14px;
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-logo {
    width: 46px; height: 46px; border-radius: 14px; flex-shrink: 0;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 6px 20px var(--accent-soft), inset 0 1px 0 rgba(255,255,255,0.25);
    font-size: 1.5rem;
}
.brand-text { min-width: 0; }
.brand-title { font-size: 1.05rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }
.brand-sub { font-size: 0.75rem; color: var(--muted); font-weight: 600; margin-top: 2px; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.badge-class {
    background: linear-gradient(135deg, var(--accent-soft), var(--accent-soft2));
    color: var(--accent); padding: 7px 13px; border-radius: 12px;
    font-weight: 800; font-size: 0.95rem; letter-spacing: 0.02em;
    border: 1px solid var(--border);
}
.icon-btn {
    background: var(--card); color: var(--muted); border: 1px solid var(--border);
    width: 42px; height: 42px; border-radius: 13px; font-size: 1.15rem;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    transition: transform 0.15s, color 0.2s, background 0.2s;
}
.icon-btn:hover, .icon-btn:active { color: var(--accent); background: var(--accent-soft); transform: scale(0.94); }
.icon-btn.spin { animation: spin 0.5s ease; }
@keyframes spin { to { transform: rotate(360deg) scale(0.94); } }

/* === SETTINGS === */
.settings {
    background: var(--card); border: 1px solid var(--border); border-radius: 20px;
    padding: 0 18px; margin-bottom: 14px; box-shadow: var(--shadow);
    max-height: 0; overflow: hidden; opacity: 0;
    transition: max-height 0.4s ease, opacity 0.3s ease, padding 0.3s ease;
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
}
.settings.open { max-height: 400px; opacity: 1; padding: 18px; }
.settings-title { font-weight: 800; font-size: 0.85rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 12px; }
.theme-options { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
.theme-btn {
    padding: 14px 6px; border-radius: 14px; border: 2px solid transparent;
    background: var(--bg2); color: var(--text); font-weight: 700; font-size: 0.75rem;
    cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 6px;
    transition: all 0.25s; font-family: inherit;
}
.theme-btn .emoji { font-size: 1.5rem; line-height: 1; }
.theme-btn.active { border-color: var(--accent); background: var(--accent-soft); box-shadow: 0 0 0 4px var(--accent-soft); }
.theme-btn:active { transform: scale(0.95); }
.install-btn {
    width: 100%; padding: 13px; border-radius: 14px; border: none;
    background: linear-gradient(135deg, var(--accent), var(--accent2)); color: white;
    font-weight: 800; font-size: 0.9rem; cursor: pointer; font-family: inherit;
    transition: transform 0.15s, box-shadow 0.2s; box-shadow: 0 6px 20px var(--accent-soft);
}
.install-btn:hover { box-shadow: 0 8px 28px var(--accent-soft2); }
.install-btn:active { transform: scale(0.97); }
.link-btn {
    background: none; border: none; color: var(--muted); font-weight: 600;
    font-size: 0.82rem; cursor: pointer; padding: 8px 4px; text-decoration: underline;
    font-family: inherit; display: inline-block;
}
.installed-badge { color: var(--green); font-weight: 700; font-size: 0.9rem;
    padding: 10px 0; display: flex; align-items: center; gap: 6px; }
.hint-text { color: var(--muted); font-size: 0.82rem; line-height: 1.5; margin-bottom: 6px; }

/* === LIVE BANNER === */
.live-banner {
    border-radius: 20px; padding: 16px 18px; margin-bottom: 14px;
    display: flex; align-items: center; gap: 14px; box-shadow: var(--shadow);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--border); animation: slideDown 0.4s ease;
}
@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: none; } }
.live-banner.now { background: linear-gradient(135deg, var(--green-soft), var(--accent-soft)); }
.live-banner.before { background: linear-gradient(135deg, var(--orange-soft), var(--accent-soft)); }
.live-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--green);
    box-shadow: 0 0 0 0 var(--green); animation: pulse 1.6s infinite; flex-shrink: 0; }
.live-banner.before .live-dot { background: var(--orange); box-shadow: 0 0 0 0 var(--orange); }
@keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(16,185,129,0.6); }
    70% { box-shadow: 0 0 0 12px rgba(16,185,129,0); }
    100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
}
.live-info { flex: 1; min-width: 0; }
.live-label { font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--green); margin-bottom: 3px; }
.live-banner.before .live-label { color: var(--orange); }
.live-lesson { font-size: 1.05rem; font-weight: 800; letter-spacing: -0.01em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.live-time { font-size: 0.78rem; color: var(--muted); font-weight: 700; margin-top: 2px; }
.progress-bar {
    height: 5px; border-radius: 3px; background: var(--border); overflow: hidden;
    margin-top: 8px;
}
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--green), var(--accent2));
    border-radius: 3px; transition: width 0.6s ease; }

/* === TABS === */
.tabs {
    display: flex; gap: 6px; margin-bottom: 16px; overflow-x: auto;
    padding: 4px; scrollbar-width: none; -ms-overflow-style: none;
    background: var(--card); border-radius: 18px; border: 1px solid var(--border);
    box-shadow: var(--shadow); backdrop-filter: blur(14px);
}
.tabs::-webkit-scrollbar { display: none; }
.tab {
    flex: 1; min-width: 52px; padding: 11px 8px; border-radius: 13px; border: none;
    background: transparent; color: var(--muted); font-weight: 800; font-size: 0.88rem;
    cursor: pointer; font-family: inherit; transition: all 0.25s;
    display: flex; flex-direction: column; align-items: center; gap: 3px; position: relative;
}
.tab .tab-day { font-size: 0.68rem; font-weight: 700; opacity: 0.7; letter-spacing: 0.02em; }
.tab.active { background: linear-gradient(135deg, var(--accent), var(--accent2));
    color: white; box-shadow: 0 6px 18px var(--accent-soft); }
.tab.active .tab-day { opacity: 0.9; }
.tab.today:not(.active)::after {
    content: ""; position: absolute; bottom: 4px; left: 50%; transform: translateX(-50%);
    width: 5px; height: 5px; border-radius: 50%; background: var(--accent);
}
.tab:active { transform: scale(0.94); }

/* === CARDS === */
.day-block { display: none; }
.day-block.active { display: block; animation: fadeUp 0.35s ease; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.day-title {
    font-size: 1.15rem; font-weight: 800; color: var(--text);
    margin: 4px 4px 12px; letter-spacing: -0.02em; display: flex; justify-content: space-between; align-items: center;
}
.today-pill {
    font-size: 0.68rem; background: linear-gradient(135deg, var(--accent-soft), var(--accent-soft2));
    color: var(--accent); padding: 5px 11px; border-radius: 20px;
    font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em;
    border: 1px solid var(--border);
}
.card {
    background: var(--card); padding: 14px 16px; margin-bottom: 9px; border-radius: 18px;
    box-shadow: var(--shadow); display: flex; align-items: center; gap: 14px;
    border: 1px solid var(--border); transition: all 0.25s;
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    position: relative; overflow: hidden;
}
.card.now {
    box-shadow: 0 8px 28px var(--green-soft), 0 0 0 1px var(--green);
    background: linear-gradient(135deg, var(--green-soft), var(--card));
}
.card.now::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: linear-gradient(180deg, var(--green), var(--accent2));
}
.card.next-up { box-shadow: 0 6px 22px var(--orange-soft), 0 0 0 1px var(--orange); }
.num {
    min-width: 40px; height: 40px; border-radius: 12px;
    background: linear-gradient(135deg, var(--accent-soft), var(--accent-soft2));
    color: var(--accent); display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 1rem; flex-shrink: 0;
    border: 1px solid var(--border);
}
.card.now .num { background: linear-gradient(135deg, var(--green), var(--accent2)); color: white; border-color: transparent; }
.left-side { display: flex; flex-direction: column; gap: 2px; flex-grow: 1; min-width: 0; }
.time { font-size: 0.78rem; color: var(--muted); font-weight: 700; letter-spacing: 0.01em; }
.lesson { font-size: 1rem; font-weight: 800; color: var(--text); letter-spacing: -0.01em; word-wrap: break-word; }
.now-pill {
    font-size: 0.62rem; background: var(--green); color: white; padding: 3px 8px;
    border-radius: 20px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;
    margin-left: auto; flex-shrink: 0; animation: pulse2 2s infinite;
}
@keyframes pulse2 { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }

/* === EMPTY / ERROR === */
.info-box {
    background: var(--card); padding: 32px 20px; border-radius: 20px;
    box-shadow: var(--shadow); text-align: center; font-size: 1rem; font-weight: 700;
    color: var(--muted); border: 1px solid var(--border);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    line-height: 1.5;
}
.info-box .big { font-size: 2.2rem; display: block; margin-bottom: 8px; }
.error { background: linear-gradient(135deg, rgba(239,68,68,0.1), var(--card));
    color: var(--danger); padding: 20px; border-radius: 18px; font-weight: 700;
    text-align: center; border: 1px solid var(--border); }

/* === FOOTER === */
.sheet-link {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    margin-top: 20px; padding: 13px; color: var(--muted); text-decoration: none;
    font-size: 0.82rem; font-weight: 700; border-radius: 14px;
    border: 1px dashed var(--border); opacity: 0.8; transition: all 0.25s;
    background: var(--card);
}
.sheet-link:hover, .sheet-link:active { opacity: 1; color: var(--accent); border-color: var(--accent); border-style: solid; }
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
        <button class="icon-btn" id="settingsBtn" onclick="toggleSettings()">⚙️</button>
    </div>
</div>

<div class="settings" id="settingsPanel">
    <div class="settings-title">🎨 Тема оформления</div>
    <div class="theme-options">
        <button class="theme-btn" data-theme-btn="light" onclick="setTheme('light')"><span class="emoji">☀️</span>Светлая</button>
        <button class="theme-btn" data-theme-btn="dark" onclick="setTheme('dark')"><span class="emoji">🌙</span>Тёмная</button>
        <button class="theme-btn" data-theme-btn="cosmic" onclick="setTheme('cosmic')"><span class="emoji">🌌</span>Космос</button>
    </div>
    <div class="settings-title">📱 Приложение</div>
    <div id="installSection"></div>
</div>

{live_banner}

{tabs}

{content}

<a class="sheet-link" href="{sheet_url}" target="_blank" rel="noopener">
    <span>📊</span> Открыть таблицу в Google Sheets
</a>

</div>

<script>
(function() {
    var saved = localStorage.getItem('rs_theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    var meta = document.getElementById('themeColorMeta');
    if (meta) {
        var colors = {light: '#eef2f7', dark: '#0b0d12', cosmic: '#06021a'};
        meta.setAttribute('content', colors[saved] || '#eef2f7');
    }
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        if (b.getAttribute('data-theme-btn') === saved) b.classList.add('active');
    });
})();
function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('rs_theme', t);
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-theme-btn') === t);
    });
    var meta = document.getElementById('themeColorMeta');
    if (meta) {
        var colors = {light: '#eef2f7', dark: '#0b0d12', cosmic: '#06021a'};
        meta.setAttribute('content', colors[t] || '#eef2f7');
    }
}
function toggleSettings() {
    document.getElementById('settingsPanel').classList.toggle('open');
    var btn = document.getElementById('settingsBtn');
    btn.classList.remove('spin'); void btn.offsetWidth; btn.classList.add('spin');
}
function showDay(day) {
    document.querySelectorAll('.day-block').forEach(function(el) { el.classList.remove('active'); });
    var target = document.getElementById('day-' + day);
    if (target) target.classList.add('active');
    document.querySelectorAll('.tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-day') === day);
    });
    localStorage.setItem('rs_last_day', day);
}
var deferredPrompt = null;
var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e) { e.preventDefault(); deferredPrompt = e; renderInstallSection(); });
window.addEventListener('appinstalled', function() { deferredPrompt = null; localStorage.setItem('rs_installed', '1'); renderInstallSection(); });
function detectPlatform() {
    var ua = navigator.userAgent || '';
    if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
    if (/Android/i.test(ua)) return 'android';
    return 'desktop';
}
function renderInstallSection() {
    var el = document.getElementById('installSection');
    if (!el) return;
    var installed = isStandalone || localStorage.getItem('rs_installed') === '1';
    if (installed) {
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>' +
                       '<button class="link-btn" onclick="resetInstallFlag()">Сбросить флаг</button>';
        return;
    }
    var hidden = localStorage.getItem('rs_install_hidden') === '1';
    if (hidden) {
        el.innerHTML = '<button class="link-btn" onclick="showInstall()">Показать инструкцию</button>';
        return;
    }
    if (deferredPrompt) {
        el.innerHTML = '<button class="install-btn" onclick="doInstall()">📲 Добавить на рабочий стол</button>' +
                       '<button class="link-btn" onclick="hideInstall()">Скрыть</button>';
        return;
    }
    var plat = detectPlatform();
    var hint = '';
    if (plat === 'ios') hint = '📱 <b>iPhone:</b> открой в <b>Safari</b> → «Поделиться» → «На экран Домой».';
    else if (plat === 'android') hint = '📱 <b>Android:</b> открой в <b>Chrome</b> → меню <b>⋮</b> → «Установить приложение».';
    else hint = '💻 <b>ПК:</b> открой в Chrome — иконка установки появится в адресной строке.';
    el.innerHTML = '<div class="hint-text">' + hint + '</div>' +
                   '<button class="link-btn" onclick="hideInstall()">Скрыть</button>';
}
function doInstall() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(function(choice) {
        if (choice.outcome === 'accepted') localStorage.setItem('rs_installed', '1');
        deferredPrompt = null;
        renderInstallSection();
    });
}
function hideInstall() { localStorage.setItem('rs_install_hidden', '1'); renderInstallSection(); }
function showInstall() { localStorage.removeItem('rs_install_hidden'); renderInstallSection(); }
function resetInstallFlag() { localStorage.removeItem('rs_installed'); renderInstallSection(); }
renderInstallSection();
setTimeout(function() { if (deferredPrompt) renderInstallSection(); }, 3000);
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.getRegistrations().then(function(r){r.forEach(function(x){x.unregister()})}).catch(function() {});
    });
}
</script>
</body>
</html>"""


def build_tabs(active_day, days_schedule):
    today = datetime.now(PERM_TZ)
    today_idx = today.weekday()
    html = '<div class="tabs">'
    for i, full in enumerate(DAY_FULL):
        short = DAY_SHORT[full]
        has = full in days_schedule and len(days_schedule[full]) > 0
        cls = "tab"
        if full == active_day: cls += " active"
        if i == today_idx: cls += " today"
        html += f'<button class="{cls}" data-day="{full}" onclick="showDay(\'{full}\')">'
        html += f'{short}<span class="tab-day">{"•" if has else "—"}</span></button>'
    html += '</div>'
    return html


def build_live_banner(status):
    if not status:
        return ""
    if status["type"] == "now":
        left = status["left"]
        return (
            '<div class="live-banner now">'
            '<div class="live-dot"></div>'
            '<div class="live-info">'
            '<div class="live-label">Сейчас идёт</div>'
            f'<div class="live-lesson">{status["lesson"]}</div>'
            f'<div class="live-time">До конца {left} мин · до {status["until"]}</div>'
            f'<div class="progress-bar"><div class="progress-fill" style="width:{status["progress"]}%"></div></div>'
            '</div></div>'
        )
    if status["type"] == "before":
        return (
            '<div class="live-banner before">'
            '<div class="live-dot"></div>'
            '<div class="live-info">'
            '<div class="live-label">Скоро урок</div>'
            f'<div class="live-lesson">{status["lesson"]}</div>'
            f'<div class="live-time">Через {status["wait"]} мин · в {status["start"]}</div>'
            '</div></div>'
        )
    return ""


def build_content(days_schedule, active_day, error_msg, live_status):
    if error_msg and not cache["days_schedule"]:
        return f"<div class='error'>{error_msg}</div>"
    today_full = DAY_FULL[datetime.now(PERM_TZ).weekday()] if datetime.now(PERM_TZ).weekday() < 6 else ""
    html = ""
    for full in DAY_FULL:
        lessons = days_schedule.get(full, [])
        is_active = " active" if full == active_day else ""
        html += f'<div class="day-block{is_active}" id="day-{full}">'
        if full == today_full:
            html += f'<div class="day-title">{full}<span class="today-pill">✨ Сегодня</span></div>'
        else:
            html += f'<div class="day-title">{full}</div>'
        if not lessons:
            html += '<div class="info-box"><span class="big">📭</span>Нет уроков на этот день</div>'
        else:
            for i, (time_str, num, lesson) in enumerate(lessons):
                card_cls = "card"
                now_pill = ""
                if full == today_full and live_status and live_status["type"] == "now" and num == live_status["num"]:
                    card_cls += " now"
                    now_pill = '<span class="now-pill">сейчас</span>'
                elif full == today_full and live_status and live_status["type"] == "before" and num == live_status["num"]:
                    card_cls += " next-up"
                html += f'<div class="{card_cls}">'
                html += f'<div class="num">{num}</div>'
                html += f'<div class="left-side"><div class="time">{time_str}</div>'
                html += f'<div class="lesson">{lesson}</div></div>'
                html += now_pill
                html += '</div>'
        html += '</div>'
    return html


class SimpleHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, content_type, body):
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            path = self.path.split("?")[0]
            if path == "/manifest.json":
                self._send("application/manifest+json; charset=utf-8", MANIFEST.encode("utf-8")); return
            if path == "/sw.js":
                self._send("application/javascript; charset=utf-8", SW_JS.encode("utf-8")); return
            if path == "/icon.svg":
                self._send("image/svg+xml; charset=utf-8", ICON_SVG.encode("utf-8")); return

            now_perm = datetime.now(PERM_TZ)
            hour = now_perm.hour
            minute = now_perm.minute
            weekday_idx = now_perm.weekday()

            current_day_name = DAY_FULL[weekday_idx] if weekday_idx < 6 else "Суббота"
            is_weekend = (weekday_idx >= 5)
            refresh_tag = "<meta http-equiv='refresh' content='900'>" if not (1 <= hour < 5) else ""

            days_schedule, error_msg = get_schedule()

            # Header date
            months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
            header_date = f"{current_day_name}, {now_perm.day} {months[now_perm.month-1]}"

            # Активный день: по умолчанию — сегодня, но если после школы и есть завтра — завтра
            today_lessons = days_schedule.get(current_day_name, [])
            school_over = (hour > 14 or (hour == 14 and minute >= 40) or is_weekend or not today_lessons)
            if school_over and weekday_idx < 5:
                next_idx = weekday_idx + 1
                if next_idx < 6:
                    tomorrow = DAY_FULL[next_idx]
                    if days_schedule.get(tomorrow):
                        active_day = tomorrow
                    else:
                        active_day = current_day_name
                else:
                    active_day = current_day_name
            else:
                active_day = current_day_name
            if active_day not in DAY_FULL:
                active_day = current_day_name
            if not days_schedule.get(active_day) and days_schedule.get(current_day_name):
                active_day = current_day_name

            live_status = get_live_status(today_lessons) if not is_weekend else None

            live_banner = build_live_banner(live_status)
            tabs = build_tabs(active_day, days_schedule)
            content = build_content(days_schedule, active_day, error_msg, live_status)

            html = PAGE_TEMPLATE
            html = html.replace("{refresh_tag}", refresh_tag)
            html = html.replace("{header_date}", header_date)
            html = html.replace("{live_banner}", live_banner)
            html = html.replace("{tabs}", tabs)
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
            except Exception:
                pass


def keep_alive():
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(SELF_URL, timeout=30)
            print(f"[keep-alive] {datetime.now(PERM_TZ).strftime('%H:%M')}")
        except Exception:
            pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Сервер запущен на порту {port}")
    threading.Thread(target=keep_alive, daemon=True).start()
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()
