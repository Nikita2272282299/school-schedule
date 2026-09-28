import threading, urllib.request, csv, io, time, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

SPREADSHEET_ID = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SELF_URL = "https://school-schedule-4ldw.onrender.com/"
PERM_TZ = timezone(timedelta(hours=5))

TIME_TO_NUM = {"8:00-8:40":1,"8:50-9:30":2,"9:45-10:25":3,"10:40-11:20":4,
    "11:35-12:15":5,"12:25-13:05":6,"13:15-13:55":7,"14:00-14:40":8}

cache = {"days_schedule": {}, "error_msg": "", "last_update": 0}
CACHE_TTL = 300

MANIFEST = '{"name":"Расписание 8Г","short_name":"8Г","start_url":"/","display":"standalone","background_color":"#0a0620","theme_color":"#4c6ef5","icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4c6ef5"/><stop offset="1" stop-color="#7950f2"/></linearGradient></defs><rect width="512" height="512" rx="110" fill="url(#g)"/><rect x="130" y="110" width="252" height="46" rx="23" fill="#ffffff" opacity="0.25"/><text x="256" y="360" font-family="Arial,Helvetica,sans-serif" font-size="230" font-weight="900" fill="#ffffff" text-anchor="middle">8Г</text></svg>'''

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>self.clients.claim());self.addEventListener('fetch',e=>{e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});"


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
            error_msg = "Класс 8Г не найден."
            cache["error_msg"] = error_msg
    except Exception:
        if cache["days_schedule"]:
            return cache["days_schedule"], ""
        cache["error_msg"] = "Офлайн-режим (нет сети)"
    return cache["days_schedule"], cache["error_msg"]


def get_live_status(today_lessons):
    if not today_lessons: return None
    now = datetime.now(PERM_TZ)
    cur = now.hour * 60 + now.minute
    for tv, num, lesson in today_lessons:
        try:
            start, end = tv.split("-")
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
        except Exception: continue
        s = sh*60+sm; e = eh*60+em
        if s <= cur < e:
            prog = int((cur - s) / max(e - s, 1) * 100)
            return {"type":"now","num":num,"lesson":lesson,"progress":prog,"left":e-cur,"until":end}
        if cur < s:
            return {"type":"before","num":num,"lesson":lesson,"wait":s-cur,"start":start}
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
<meta name="apple-mobile-web-app-title" content="8Г">
{refresh_tag}
<title>Расписание 8Г</title>
<style>
:root, [data-theme="light"] {
    --bg: #f0f4f8; --card-bg: #ffffff; --text-main: #1a202c; --text-muted: #4a5568;
    --accent: #4c6ef5; --accent-light: #edf2ff; --today-badge: #38a169;
    --error: #e03131; --shadow: 0 4px 16px rgba(0,0,0,0.06); --border: #edf2f7;
    --banner-bg: linear-gradient(135deg,#ebfbee,#d3f9d8); --banner-border:#b2f2bb;
    --banner-text:#2b8a3e; --btn-bg:#2b8a3e;
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
    --num-bg:#edf2ff; --num-color:#4c6ef5; --num-radius:11px; --num-shadow:none;
}
[data-theme="dark"] {
    --bg:#0f1115; --card-bg:#1a1d24; --text-main:#e6e8ec; --text-muted:#9aa3b2;
    --accent:#7c93ff; --accent-light:#232741; --today-badge:#4ade80;
    --error:#ff6b6b; --shadow:0 4px 16px rgba(0,0,0,0.4); --border:#232733;
    --banner-bg:linear-gradient(135deg,#1a2e1e,#14321c); --banner-border:#2b5733;
    --banner-text:#86efac; --btn-bg:#2b8a3e;
    --green:#34d399; --green-soft:rgba(52,211,153,0.14);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.14);
    --num-bg:#232741; --num-color:#c7d2fe; --num-radius:11px; --num-shadow:none;
    color-scheme:dark;
}
[data-theme="cosmic"] {
    --bg:#05021a; --card-bg:rgba(30,20,65,0.7); --text-main:#ece6ff; --text-muted:#a89cc7;
    --accent:#b794f6; --accent-light:rgba(183,148,246,0.18); --today-badge:#7cf5c0;
    --error:#ff8ab5; --shadow:0 8px 32px rgba(120,60,220,0.28); --border:rgba(183,148,246,0.16);
    --banner-bg:linear-gradient(135deg,rgba(124,245,192,0.15),rgba(183,148,246,0.15));
    --banner-border:rgba(124,245,192,0.4); --banner-text:#7cf5c0; --btn-bg:#7c3aed;
    --green:#7cf5c0; --green-soft:rgba(124,245,192,0.14);
    --orange:#fbbf77; --orange-soft:rgba(251,191,119,0.14);
    --num-bg:linear-gradient(135deg,rgba(183,148,246,0.35),rgba(124,245,192,0.25));
    --num-color:#ece6ff; --num-radius:11px;
    --num-shadow:0 0 14px rgba(183,148,246,0.4);
    color-scheme:dark;
}
html { min-height:100%; background:var(--bg); }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body {
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:var(--bg); color:var(--text-main); margin:0;
    padding:20px 16px 30px; display:flex; justify-content:center;
    min-height:100vh; -webkit-font-smoothing:antialiased;
    transition:background 0.4s ease, color 0.3s ease;
    position:relative; overflow-x:hidden;
}
[data-theme="light"] body { background-image:linear-gradient(180deg,#f1f5fa 0%,#e4ebf3 100%); }
[data-theme="dark"] body { background-image:linear-gradient(180deg,#10131a 0%,#0b0d12 100%); }
[data-theme="cosmic"] body {
    background-image:
        radial-gradient(ellipse at 20% 15%, rgba(139,92,246,0.28), transparent 45%),
        radial-gradient(ellipse at 85% 75%, rgba(56,189,248,0.18), transparent 50%),
        radial-gradient(ellipse at 60% 40%, rgba(124,245,192,0.08), transparent 55%),
        linear-gradient(180deg,#0a0424 0%,#05021a 55%,#01000a 100%);
    background-attachment:scroll;
}
[data-theme="cosmic"] body::before {
    content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
    background-image:
        radial-gradient(1.5px 1.5px at 24px 32px, rgba(255,255,255,0.95), transparent 60%),
        radial-gradient(1px 1px at 118px 88px, rgba(255,255,255,0.8), transparent 60%),
        radial-gradient(2px 2px at 210px 156px, rgba(183,148,246,1), transparent 60%),
        radial-gradient(1px 1px at 60px 200px, rgba(255,255,255,0.7), transparent 60%),
        radial-gradient(1.5px 1.5px at 260px 40px, rgba(124,245,192,1), transparent 60%),
        radial-gradient(1.2px 1.2px at 180px 240px, rgba(255,255,255,0.85), transparent 60%),
        radial-gradient(1px 1px at 340px 100px, rgba(255,255,255,0.65), transparent 60%),
        radial-gradient(1.8px 1.8px at 90px 130px, rgba(183,148,246,0.9), transparent 60%),
        radial-gradient(1px 1px at 400px 300px, rgba(255,255,255,0.75), transparent 60%),
        radial-gradient(1.3px 1.3px at 30px 340px, rgba(124,245,192,0.85), transparent 60%);
    background-size:460px 380px; background-repeat:repeat;
    animation:twinkle 6s ease-in-out infinite alternate;
}
@keyframes twinkle { 0% { opacity:0.7; } 100% { opacity:1; } }
.container { width:100%; max-width:500px; position:relative; z-index:1; }

.header-card {
    background:var(--card-bg); padding:18px 22px; border-radius:22px;
    box-shadow:var(--shadow); margin-bottom:14px;
    display:flex; align-items:center; justify-content:space-between;
    border:1px solid var(--border); gap:10px;
}
h2 { margin:0; font-size:1.4rem; font-weight:800; display:flex; align-items:center; gap:10px; }
h2 span { background:linear-gradient(135deg,#4c6ef5,#7950f2); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
[data-theme="dark"] h2 span { background:linear-gradient(135deg,#7c93ff,#b794f6); -webkit-background-clip:text; background-clip:text; }
[data-theme="cosmic"] h2 span { background:linear-gradient(135deg,#b794f6,#7cf5c0); -webkit-background-clip:text; background-clip:text; }
.header-right { display:flex; align-items:center; gap:8px; }
.badge-class { background:var(--accent-light); color:var(--accent); padding:7px 14px; border-radius:12px; font-weight:800; font-size:1rem; }
.icon-btn {
    background:var(--accent-light); color:var(--accent); border:none;
    width:40px; height:40px; border-radius:12px; font-size:1.15rem;
    cursor:pointer; display:flex; align-items:center; justify-content:center;
    transition:transform 0.15s ease;
}
.icon-btn:active { transform:scale(0.92); }
[data-theme="cosmic"] .icon-btn { box-shadow:0 0 14px rgba(183,148,246,0.35); }

.settings-panel {
    background:var(--card-bg); border:1px solid var(--border); border-radius:16px;
    margin-bottom:0; box-shadow:none;
    display:grid; grid-template-rows:0fr;
    transition:grid-template-rows 0.3s cubic-bezier(0.4,0,0.2,1),
               margin-bottom 0.3s ease, box-shadow 0.3s ease;
}
.settings-panel.open { grid-template-rows:1fr; margin-bottom:14px; box-shadow:var(--shadow); }
.settings-inner { overflow:hidden; min-height:0; padding:0 18px;
    transition:padding 0.3s cubic-bezier(0.4,0,0.2,1); }
.settings-panel.open .settings-inner { padding:16px 18px; }
.settings-title { font-weight:800; font-size:0.9rem; margin-bottom:10px; }
.settings-title:not(:first-child) { margin-top:16px; }
.theme-options { display:flex; gap:8px; }
.theme-btn {
    flex:1; padding:12px 6px; border-radius:12px; border:2px solid var(--border);
    background:transparent; color:var(--text-main); font-weight:700; font-size:0.75rem;
    cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:5px;
    font-family:inherit; transition:background 0.15s, border-color 0.15s;
}
.theme-btn.active { border-color:var(--accent); background:var(--accent-light); }
.theme-btn .emoji { font-size:1.35rem; }
.size-options { display:flex; gap:8px; }
.size-btn {
    flex:1; padding:10px; border-radius:12px; border:2px solid var(--border);
    background:transparent; color:var(--text-main); font-weight:800; cursor:pointer;
    font-family:inherit; transition:background 0.15s, border-color 0.15s;
}
.size-btn[data-size="small"] { font-size:0.85rem; }
.size-btn[data-size="normal"] { font-size:1rem; }
.size-btn[data-size="large"] { font-size:1.2rem; }
.size-btn.active { border-color:var(--accent); background:var(--accent-light); }
.toggle-row {
    display:flex; justify-content:space-between; align-items:center;
    padding:9px 0; border-bottom:1px solid var(--border);
}
.toggle-row:last-child { border-bottom:none; }
.toggle-label { font-weight:700; font-size:0.88rem; }
.toggle {
    position:relative; width:46px; height:26px; background:var(--border);
    border-radius:13px; cursor:pointer; transition:background 0.2s;
}
.toggle::after {
    content:""; position:absolute; top:2px; left:2px;
    width:22px; height:22px; background:#fff; border-radius:50%;
    transition:transform 0.2s cubic-bezier(0.4,0,0.2,1);
    box-shadow:0 1px 3px rgba(0,0,0,0.15);
}
.toggle.on { background:var(--accent); }
.toggle.on::after { transform:translateX(20px); }
.install-btn {
    width:100%; padding:13px; border-radius:12px; border:none;
    background:linear-gradient(135deg,var(--accent),#7950f2); color:white;
    font-weight:800; font-size:0.92rem; cursor:pointer; font-family:inherit;
}
[data-theme="cosmic"] .install-btn { background:linear-gradient(135deg,#b794f6,#7cf5c0); color:#1a1030; }
.link-btn {
    background:none; border:none; color:var(--text-muted); font-weight:600;
    font-size:0.82rem; cursor:pointer; padding:6px 4px; text-decoration:underline;
    font-family:inherit; display:inline-block;
}
.installed-badge { color:var(--today-badge); font-weight:700; font-size:0.9rem; padding:8px 0; }
.hint-text { color:var(--text-muted); font-size:0.82rem; line-height:1.4; margin-top:4px; }

.switcher {
    display:flex; gap:6px; margin-bottom:14px; padding:4px;
    background:var(--card-bg); border-radius:16px; border:1px solid var(--border);
    box-shadow:var(--shadow);
}
.switch-btn {
    flex:1; padding:11px; border-radius:12px; border:none;
    background:transparent; color:var(--text-muted); font-weight:800; font-size:0.9rem;
    cursor:pointer; font-family:inherit;
    transition:background 0.25s ease, color 0.25s ease;
}
.switch-btn.active { background:linear-gradient(135deg,var(--accent),var(--accent2,#7950f2)); color:white; }
[data-theme="cosmic"] .switch-btn.active { background:linear-gradient(135deg,#b794f6,#7cf5c0); color:#1a1030; }

.live-banner {
    border-radius:18px; padding:14px 16px; margin-bottom:14px;
    display:flex; align-items:center; gap:12px; box-shadow:var(--shadow);
    border:1px solid var(--border);
    animation:fadeIn 0.4s ease;
}
@keyframes fadeIn { from { opacity:0; transform:translateY(-6px); } to { opacity:1; transform:none; } }
.live-banner.now { background:linear-gradient(135deg,var(--green-soft),var(--accent-light)); }
.live-banner.before { background:linear-gradient(135deg,var(--orange-soft),var(--accent-light)); }
.live-dot { width:10px; height:10px; border-radius:50%; background:var(--green); flex-shrink:0;
    animation:pulse 1.6s infinite; }
.live-banner.before .live-dot { background:var(--orange); }
@keyframes pulse {
    0%,100% { box-shadow:0 0 0 0 var(--green); }
    70% { box-shadow:0 0 0 10px transparent; }
}
.live-info { flex:1; min-width:0; }
.live-label { font-size:0.7rem; font-weight:800; text-transform:uppercase;
    letter-spacing:0.08em; color:var(--green); margin-bottom:3px; }
.live-banner.before .live-label { color:var(--orange); }
.live-lesson { font-size:1.05rem; font-weight:800;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.live-time { font-size:0.78rem; color:var(--text-muted); font-weight:700; margin-top:2px; }
.progress-bar { height:4px; border-radius:2px; background:var(--border); overflow:hidden; margin-top:7px; }
.progress-fill { height:100%; background:linear-gradient(90deg,var(--green),var(--accent)); border-radius:2px; }

.day-title {
    font-size:1.15rem; font-weight:800; color:var(--text-muted); margin-bottom:12px;
    padding-left:6px; display:flex; justify-content:space-between; align-items:center;
}
.day-title.today { color:var(--text-main); }
.today-pill {
    font-size:0.7rem; background:var(--accent-light); color:var(--today-badge);
    padding:5px 12px; border-radius:20px; font-weight:800; text-transform:uppercase;
}
.card {
    background:var(--card-bg); padding:16px 18px; margin-bottom:10px; border-radius:16px;
    box-shadow:var(--shadow); display:flex; align-items:center; gap:14px;
    border:1px solid var(--border);
    animation:fadeUp 0.35s ease backwards;
    transition:box-shadow 0.25s ease;
}
@keyframes fadeUp {
    from { opacity:0; transform:translateY(10px); }
    to { opacity:1; transform:none; }
}
.card:nth-child(2) { animation-delay:0.03s; }
.card:nth-child(3) { animation-delay:0.06s; }
.card:nth-child(4) { animation-delay:0.09s; }
.card:nth-child(5) { animation-delay:0.12s; }
.card:nth-child(6) { animation-delay:0.15s; }
.card:nth-child(7) { animation-delay:0.18s; }
.card:nth-child(8) { animation-delay:0.21s; }
.card.now {
    box-shadow:0 6px 24px var(--green-soft), 0 0 0 1px var(--green);
    background:linear-gradient(135deg,var(--green-soft),var(--card-bg));
}
.card.next-up { box-shadow:0 6px 20px var(--orange-soft), 0 0 0 1px var(--orange); }
.num {
    min-width:38px; height:38px; border-radius:var(--num-radius);
    background:var(--num-bg); color:var(--num-color);
    display:flex; align-items:center; justify-content:center;
    font-weight:800; font-size:1.05rem; flex-shrink:0;
    box-shadow:var(--num-shadow);
}
.card.now .num { background:linear-gradient(135deg,var(--green),#7cf5c0); color:#0a1f1a; }
.left-side { display:flex; flex-direction:column; gap:3px; flex-grow:1; min-width:0; }
.time { font-size:0.8rem; color:var(--text-muted); font-weight:700; }
.lesson { font-size:1.05rem; font-weight:800; color:var(--text-main); word-wrap:break-word; }
.now-pill {
    font-size:0.6rem; background:var(--green); color:#0a1f1a;
    padding:3px 8px; border-radius:20px; font-weight:800;
    text-transform:uppercase; letter-spacing:0.06em;
    margin-left:auto; flex-shrink:0;
}
.error { background:rgba(224,49,49,0.1); color:var(--error); padding:16px; border-radius:16px; font-weight:700; text-align:center; }
.info-box {
    background:var(--card-bg); padding:28px 20px; border-radius:18px; box-shadow:var(--shadow);
    text-align:center; font-size:1.05rem; font-weight:700; color:var(--text-muted);
    border:1px solid var(--border);
}
.switcher-footer { margin-top:16px; text-align:center; }
.switch-link { background:none; border:none; color:var(--accent); font-weight:800; font-size:0.95rem; cursor:pointer; padding:10px; }
.sheet-link {
    display:flex; align-items:center; justify-content:center; gap:6px;
    text-align:center; margin-top:22px; color:var(--text-muted);
    text-decoration:none; font-size:0.85rem; font-weight:700;
    padding:12px; border-radius:12px; border:1px dashed var(--border);
    background:var(--card-bg); opacity:0.85;
}

/* === РАЗМЕР ТЕКСТА === */
html.font-small .lesson { font-size:0.9rem; }
html.font-small .live-lesson { font-size:0.95rem; }
html.font-large .lesson { font-size:1.18rem; }
html.font-large .live-lesson { font-size:1.18rem; }
html.font-large .day-title { font-size:1.3rem; }

/* === КОМПАКТНЫЙ РЕЖИМ === */
html.compact .card { padding:11px 14px; margin-bottom:7px; }
html.compact .num { min-width:34px; height:34px; font-size:0.9rem; }
html.compact .header-card { padding:14px 18px; }

/* === СКРЫТЬ ВРЕМЯ === */
html.hide-time .time { display:none; }
</style>
</head>
<body>
<div class="container">

<div class="header-card">
    <h2>📅 <span>Расписание</span></h2>
    <div class="header-right">
        <div class="badge-class">8Г</div>
        <button class="icon-btn" onclick="toggleSettings()" title="Настройки">⚙️</button>
    </div>
</div>

<div class="settings-panel" id="settingsPanel">
    <div class="settings-inner">
        <div class="settings-title">🎨 Тема оформления</div>
        <div class="theme-options">
            <button class="theme-btn" data-theme-btn="light" onclick="setTheme('light')"><span class="emoji">☀️</span>Светлая</button>
            <button class="theme-btn" data-theme-btn="dark" onclick="setTheme('dark')"><span class="emoji">🌙</span>Тёмная</button>
            <button class="theme-btn" data-theme-btn="cosmic" onclick="setTheme('cosmic')"><span class="emoji">🌌</span>Космос</button>
        </div>

        <div class="settings-title">🔤 Размер текста</div>
        <div class="size-options">
            <button class="size-btn" data-size="small" onclick="setSize('small')">A</button>
            <button class="size-btn" data-size="normal" onclick="setSize('normal')">A</button>
            <button class="size-btn" data-size="large" onclick="setSize('large')">A</button>
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
{switcher}
{content}

<a class="sheet-link" href="{sheet_url}" target="_blank" rel="noopener">📊 Открыть таблицу в Google Sheets</a>
</div>

<script>
(function() {
    var saved = localStorage.getItem('rs_theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    var meta = document.getElementById('themeColorMeta');
    var colors = {light:'#f0f4f8', dark:'#0f1115', cosmic:'#05021a'};
    if (meta) meta.setAttribute('content', colors[saved] || '#f0f4f8');
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        if (b.getAttribute('data-theme-btn') === saved) b.classList.add('active');
    });
    var size = localStorage.getItem('rs_size') || 'normal';
    if (size === 'small') document.documentElement.classList.add('font-small');
    if (size === 'large') document.documentElement.classList.add('font-large');
    document.querySelectorAll('[data-size]').forEach(function(b) {
        if (b.getAttribute('data-size') === size) b.classList.add('active');
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
    var meta = document.getElementById('themeColorMeta');
    var colors = {light:'#f0f4f8', dark:'#0f1115', cosmic:'#05021a'};
    if (meta) meta.setAttribute('content', colors[t] || '#f0f4f8');
}
function setSize(s) {
    document.documentElement.classList.remove('font-small','font-large');
    if (s === 'small') document.documentElement.classList.add('font-small');
    if (s === 'large') document.documentElement.classList.add('font-large');
    localStorage.setItem('rs_size', s);
    document.querySelectorAll('[data-size]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-size') === s);
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
var currentDayName = '{current_day_name}';
function showDayByName(dayName) {
    document.querySelectorAll('.day-block').forEach(function(el) { el.classList.remove('active-day'); });
    var target = document.getElementById('block-' + dayName);
    if (target) target.classList.add('active-day');
    var banner = document.getElementById('notificationBanner');
    var footer = document.getElementById('switcherFooter');
    if (dayName !== currentDayName) {
        if (banner) banner.style.display = 'none';
        if (footer) footer.style.display = 'block';
    } else {
        if (banner) banner.style.display = 'flex';
        if (footer) footer.style.display = 'none';
    }
}
var deferredPrompt = null;
var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e) { e.preventDefault(); deferredPrompt = e; renderInstallSection(); });
window.addEventListener('appinstalled', function() { deferredPrompt = null; localStorage.setItem('rs_installed','1'); renderInstallSection(); });
function renderInstallSection() {
    var el = document.getElementById('installSection');
    if (!el) return;
    if (isStandalone || localStorage.getItem('rs_installed') === '1') {
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>' +
                       '<button class="link-btn" onclick="resetInstallFlag()">Сбросить флаг</button>';
        return;
    }
    if (deferredPrompt) {
        el.innerHTML = '<button class="install-btn" onclick="doInstall()">📲 Добавить на рабочий стол</button>';
        return;
    }
    var ua = navigator.userAgent, hint;
    if (/iPhone|iPad|iPod/i.test(ua)) hint = '📱 <b>iPhone:</b> Safari → «Поделиться» → «На экран Домой».';
    else if (/Android/i.test(ua)) hint = '📱 <b>Android:</b> Chrome → ⋮ → «Установить приложение».';
    else hint = '💻 <b>ПК:</b> в Chrome — иконка в адресной строке.';
    el.innerHTML = '<div class="hint-text">' + hint + '</div>';
}
function doInstall() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(function(c) {
        if (c.outcome === 'accepted') localStorage.setItem('rs_installed','1');
        deferredPrompt = null; renderInstallSection();
    });
}
function resetInstallFlag() { localStorage.removeItem('rs_installed'); renderInstallSection(); }
renderInstallSection();
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js').catch(function() {});
    });
}
</script>
</body>
</html>"""


def build_live_banner(status):
    if not status: return ""
    if status["type"] == "now":
        return ('<div class="live-banner now"><div class="live-dot"></div>'
            '<div class="live-info"><div class="live-label">Сейчас идёт</div>'
            f'<div class="live-lesson">{status["lesson"]}</div>'
            f'<div class="live-time">До конца {status["left"]} мин · до {status["until"]}</div>'
            f'<div class="progress-bar"><div class="progress-fill" style="width:{status["progress"]}%"></div></div>'
            '</div></div>')
    if status["type"] == "before":
        return ('<div class="live-banner before"><div class="live-dot"></div>'
            '<div class="live-info"><div class="live-label">Скоро урок</div>'
            f'<div class="live-lesson">{status["lesson"]}</div>'
            f'<div class="live-time">Через {status["wait"]} мин · в {status["start"]}</div>'
            '</div></div>')
    return ""


def build_switcher(today_name, tomorrow_name, show_tomorrow):
    t1 = "" if show_tomorrow else " active"
    t2 = " active" if show_tomorrow else ""
    return ('<div class="switcher">'
        f'<button class="switch-btn{t1}" onclick="showDayByName(\'{today_name}\')">Сегодня · {today_name[:2]}</button>'
        f'<button class="switch-btn{t2}" onclick="showDayByName(\'{tomorrow_name}\')">Завтра · {tomorrow_name[:2]}</button>'
        '</div>')


def build_content(current_day_name, next_day_name, days_schedule, error_msg, is_weekend, has_new_schedule, show_tomorrow_by_default, live_status):
    content = ""
    if error_msg and not cache["days_schedule"]:
        return "<div class='error'>" + error_msg + "</div>"
    today_lessons = days_schedule.get(current_day_name, [])
    if has_new_schedule:
        banner_display = "none" if show_tomorrow_by_default else "flex"
        content += '<div class="notification-banner" id="notificationBanner" style="display: ' + banner_display + '; background:var(--banner-bg); border:1px solid var(--banner-border); padding:14px 18px; border-radius:16px; margin-bottom:16px; align-items:center; justify-content:space-between; gap:10px;">'
        content += '<span style="font-size:0.9rem; font-weight:700; color:var(--banner-text);">✨ Есть расписание на ' + next_day_name + '!</span>'
        content += '<button onclick="showDayByName(\'' + next_day_name + '\')" style="background:var(--btn-bg); color:white; border:none; padding:9px 14px; border-radius:10px; font-weight:700; font-size:0.85rem; cursor:pointer; font-family:inherit;">Посмотреть</button></div>'
    active_view_name = next_day_name if show_tomorrow_by_default else current_day_name
    today_active_class = " active-day" if (current_day_name == active_view_name) else ""
    if is_weekend:
        content += '<div class="day-block' + today_active_class + '" id="block-' + current_day_name + '">'
        content += '<div class="info-box">🎉 Сегодня выходной (' + current_day_name + ')! Отдыхай! 🎮</div></div>'
    elif not today_lessons:
        content += '<div class="day-block' + today_active_class + '" id="block-' + current_day_name + '">'
        content += '<div class="info-box">📭 Уроки на сегодня (' + current_day_name + ') не найдены.</div></div>'
    else:
        content += '<div class="day-block' + today_active_class + '" id="block-' + current_day_name + '">'
        content += '<div class="day-title today"><span>' + current_day_name + '</span><span class="today-pill">✨ Сегодня</span></div>'
        for time_val, num_val, lesson in today_lessons:
            cls = "card"; pill = ""
            if live_status and live_status["type"] == "now" and num_val == live_status["num"]:
                cls += " now"; pill = '<span class="now-pill">сейчас</span>'
            elif live_status and live_status["type"] == "before" and num_val == live_status["num"]:
                cls += " next-up"
            content += '<div class="' + cls + '"><div class="num">' + str(num_val) + '</div>'
            content += '<div class="left-side"><div class="time">' + time_val + '</div>'
            content += '<div class="lesson">' + lesson + '</div></div>' + pill + '</div>'
        content += '</div>'
    if has_new_schedule:
        tomorrow_active_class = " active-day" if (next_day_name == active_view_name) else ""
        content += '<div class="day-block' + tomorrow_active_class + '" id="block-' + next_day_name + '">'
        content += '<div class="day-title"><span>' + next_day_name + '</span></div>'
        for time_val, num_val, lesson in days_schedule[next_day_name]:
            content += '<div class="card"><div class="num">' + str(num_val) + '</div>'
            content += '<div class="left-side"><div class="time">' + time_val + '</div>'
            content += '<div class="lesson">' + lesson + '</div></div></div>'
        content += '</div>'
    footer_display = "block" if show_tomorrow_by_default else "none"
    content += '<div class="switcher-footer" id="switcherFooter" style="display:' + footer_display + ';">'
    content += '<button class="switch-link" onclick="showDayByName(\'' + current_day_name + '\')">⬅ Посмотреть сегодняшнее расписание</button></div>'
    return content


class SimpleHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
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
            days_order = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
            current_day_name = days_order[weekday_idx] if weekday_idx < 6 else "Суббота"
            is_weekend = (weekday_idx >= 5)
            refresh_tag = "<meta http-equiv='refresh' content='900'>" if not (1 <= hour < 5) else ""
            days_schedule, error_msg = get_schedule()

            if weekday_idx == 4:
                next_day_name = "Понедельник"
            elif weekday_idx < len(days_order) - 1:
                next_day_name = days_order[weekday_idx + 1]
            else:
                next_day_name = "Понедельник"

            has_new_schedule = (next_day_name in days_schedule and len(days_schedule[next_day_name]) > 0)
            today_lessons = days_schedule.get(current_day_name, [])
            school_is_over = (hour > 14 or (hour == 14 and minute >= 40) or is_weekend or not today_lessons)
            show_tomorrow_by_default = has_new_schedule and school_is_over

            live_status = get_live_status(today_lessons) if not is_weekend else None
            live_banner = build_live_banner(live_status) if not show_tomorrow_by_default else ""
            switcher = build_switcher(current_day_name, next_day_name, show_tomorrow_by_default)
            content = build_content(current_day_name, next_day_name, days_schedule, error_msg, is_weekend, has_new_schedule, show_tomorrow_by_default, live_status)

            html = PAGE_TEMPLATE
            html = html.replace("{refresh_tag}", refresh_tag)
            html = html.replace("{live_banner}", live_banner)
            html = html.replace("{switcher}", switcher)
            html = html.replace("{content}", content)
            html = html.replace("{sheet_url}", SHEET_URL)
            html = html.replace("{current_day_name}", current_day_name)

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        except Exception:
            pass


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
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()
