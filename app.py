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
DAY_SHORT = {"Понедельник":"Пн","Вторник":"Вт","Среда":"Ср","Четверг":"Чт","Пятница":"Пт","Суббота":"Сб"}
DAY_FULL = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота"]

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
            if col_index != -1: break
        if col_index != -1:
            current_day = ""
            days_list = ["понедельник","вторник","среда","четверг","пятница","суббота"]
            for row in reader:
                if not row: continue
                row_text = " ".join(row).lower()
                found_day = None
                for d in days_list:
                    if d in row_text:
                        found_day = d.capitalize(); break
                if found_day:
                    current_day = found_day
                    if current_day not in days_schedule:
                        days_schedule[current_day] = []
                    continue
                if not current_day: continue
                time_val = ""
                for cell in row:
                    cc = cell.strip()
                    if cc in TIME_TO_NUM:
                        time_val = cc; break
                if not time_val: continue
                if len(row) > col_index:
                    lv = row[col_index].strip()
                    if not lv or len(lv) < 2 or ":" in lv: continue
                    if lv.lower() in ["урок","-","—",""]: continue
                    n = TIME_TO_NUM[time_val]
                    if n not in [x[1] for x in days_schedule[current_day]]:
                        days_schedule[current_day].append((time_val, n, lv))
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
            end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            return {"type":"now","num":num,"lesson":lesson,"progress":prog,
                    "left":e-cur,"until":end,"end_unix":int(end_dt.timestamp())}
        if cur < s:
            start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            return {"type":"before","num":num,"lesson":lesson,"wait":s-cur,"start":start,
                    "start_unix":int(start_dt.timestamp())}
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
    --bg:#f0f4f8; --card-bg:#ffffff; --text-main:#1a202c; --text-muted:#4a5568;
    --accent:#4c6ef5; --accent-light:#edf2ff; --today-badge:#38a169;
    --error:#e03131; --shadow:0 4px 16px rgba(0,0,0,0.06); --border:#edf2f7;
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
    --num-bg:#edf2ff; --num-color:#4c6ef5; --num-shadow:none;
}
[data-theme="dark"] {
    --bg:#0f1115; --card-bg:#1a1d24; --text-main:#e6e8ec; --text-muted:#9aa3b2;
    --accent:#7c93ff; --accent-light:#232741; --today-badge:#4ade80;
    --error:#ff6b6b; --shadow:0 4px 16px rgba(0,0,0,0.4); --border:#232733;
    --green:#34d399; --green-soft:rgba(52,211,153,0.14);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.14);
    --num-bg:#232741; --num-color:#c7d2fe; --num-shadow:none;
    color-scheme:dark;
}
[data-theme="cosmic"] {
    --bg:#05021a; --card-bg:rgba(30,20,65,0.72); --text-main:#ece6ff; --text-muted:#a89cc7;
    --accent:#b794f6; --accent-light:rgba(183,148,246,0.18); --today-badge:#7cf5c0;
    --error:#ff8ab5; --shadow:0 8px 32px rgba(120,60,220,0.28); --border:rgba(183,148,246,0.16);
    --green:#7cf5c0; --green-soft:rgba(124,245,192,0.14);
    --orange:#fbbf77; --orange-soft:rgba(251,191,119,0.14);
    --num-bg:linear-gradient(135deg,rgba(183,148,246,0.35),rgba(124,245,192,0.25));
    --num-color:#ece6ff;
    --num-shadow:0 0 14px rgba(183,148,246,0.4);
    color-scheme:dark;
}
[data-theme="ocean"] {
    --bg:#b8e0f0; --card-bg:rgba(255,255,255,0.95); --text-main:#062b3d; --text-muted:#4a7a8f;
    --accent:#0891b2; --accent-light:rgba(8,145,178,0.12); --today-badge:#10b981;
    --error:#ef4444; --shadow:0 4px 16px rgba(8,145,178,0.12); --border:rgba(6,43,61,0.08);
    --green:#10b981; --green-soft:rgba(16,185,129,0.14);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.14);
    --num-bg:radial-gradient(circle at 30% 25%,rgba(255,255,255,0.9),rgba(34,211,238,0.5) 60%,rgba(8,145,178,0.75));
    --num-color:#fff; --num-shadow:0 3px 10px rgba(8,145,178,0.3);
    color-scheme:light;
}
[data-theme="sunset"] {
    --bg:#ffd9b0; --card-bg:rgba(255,251,245,0.95); --text-main:#3d1a0a; --text-muted:#8a6550;
    --accent:#f97316; --accent-light:rgba(249,115,22,0.12); --today-badge:#059669;
    --error:#dc2626; --shadow:0 4px 16px rgba(249,115,22,0.15); --border:rgba(61,26,10,0.08);
    --green:#059669; --green-soft:rgba(5,150,105,0.14);
    --orange:#d97706; --orange-soft:rgba(217,119,6,0.14);
    --num-bg:linear-gradient(135deg,#f97316,#ec4899); --num-color:#fff;
    --num-shadow:0 3px 10px rgba(249,115,22,0.35);
    color-scheme:light;
}
[data-theme="forest"] {
    --bg:#c9e6bf; --card-bg:rgba(255,255,255,0.95); --text-main:#0f2e1b; --text-muted:#5f7c68;
    --accent:#059669; --accent-light:rgba(5,150,105,0.12); --today-badge:#16a34a;
    --error:#dc2626; --shadow:0 4px 16px rgba(5,150,105,0.12); --border:rgba(15,46,27,0.08);
    --green:#16a34a; --green-soft:rgba(22,163,74,0.14);
    --orange:#ca8a04; --orange-soft:rgba(202,138,4,0.14);
    --num-bg:linear-gradient(135deg,#059669,#84cc16); --num-color:#fff;
    --num-shadow:0 3px 10px rgba(5,150,105,0.3);
    color-scheme:light;
}
[data-theme="sakura"] {
    --bg:#ffd6e4; --card-bg:rgba(255,255,255,0.95); --text-main:#3d1029; --text-muted:#9a6782;
    --accent:#ec4899; --accent-light:rgba(236,72,153,0.12); --today-badge:#059669;
    --error:#dc2626; --shadow:0 4px 16px rgba(236,72,153,0.12); --border:rgba(61,16,41,0.08);
    --green:#059669; --green-soft:rgba(5,150,105,0.14);
    --orange:#ea580c; --orange-soft:rgba(234,88,12,0.14);
    --num-bg:linear-gradient(135deg,#ec4899,#a855f7); --num-color:#fff;
    --num-shadow:0 3px 10px rgba(236,72,153,0.3);
    color-scheme:light;
}
[data-theme="ocean"] body { background-image:linear-gradient(180deg,#c7e8f5 0%,#94d0e6 45%,#5aafd0 100%); }
[data-theme="sunset"] body { background-image:linear-gradient(180deg,#ffe0a8 0%,#ffb572 40%,#e88898 100%); }
[data-theme="forest"] body { background-image:linear-gradient(180deg,#dff0d0 0%,#b8dfa8 40%,#7abb6c 100%); }
[data-theme="sakura"] body { background-image:linear-gradient(180deg,#ffeaf0 0%,#ffd0dd 50%,#ffb0c8 100%); }

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
        radial-gradient(1.8px 1.8px at 90px 130px, rgba(183,148,246,0.9), transparent 60%);
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
    position:relative;
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

/* === НАСТРОЙКИ — выпадающая панель под кнопкой, быстрая === */
.settings-panel {
    position:absolute;
    top:100%;
    right:0;
    margin-top:8px;
    width:320px;
    max-width:calc(100vw - 44px);
    background:var(--card-bg);
    border:1px solid var(--border);
    border-radius:16px;
    box-shadow:0 12px 40px rgba(0,0,0,0.15), 0 4px 12px rgba(0,0,0,0.08);
    padding:16px 18px;
    z-index:50;
    transform-origin:top right;
    transform:scale(0.92) translateY(-6px);
    opacity:0;
    pointer-events:none;
    transition:transform 0.18s cubic-bezier(0.4,0,0.2,1), opacity 0.15s ease;
}
[data-theme="cosmic"] .settings-panel {
    box-shadow:0 12px 40px rgba(120,60,220,0.35), 0 0 0 1px rgba(183,148,246,0.2);
}
.settings-panel.open {
    transform:scale(1) translateY(0);
    opacity:1;
    pointer-events:auto;
}
.settings-title { font-weight:800; font-size:0.85rem; margin-bottom:10px; color:var(--text-main); }
.settings-title:not(:first-child) { margin-top:14px; }
.theme-options { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
.theme-btn {
    flex:1; padding:10px 6px; border-radius:10px; border:2px solid var(--border);
    background:transparent; color:var(--text-main); font-weight:700; font-size:0.72rem;
    cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:4px;
    font-family:inherit; transition:background 0.12s, border-color 0.12s;
}
.theme-btn.active { border-color:var(--accent); background:var(--accent-light); }
.theme-btn .emoji { font-size:1.25rem; }
.size-options { display:flex; gap:8px; }
.size-btn {
    flex:1; padding:9px; border-radius:10px; border:2px solid var(--border);
    background:transparent; color:var(--text-main); font-weight:800; cursor:pointer;
    font-family:inherit; transition:background 0.12s, border-color 0.12s;
}
.size-btn[data-size="small"] { font-size:0.8rem; }
.size-btn[data-size="normal"] { font-size:1rem; }
.size-btn[data-size="large"] { font-size:1.18rem; }
.size-btn.active { border-color:var(--accent); background:var(--accent-light); }
.toggle-row {
    display:flex; justify-content:space-between; align-items:center;
    padding:8px 0; border-bottom:1px solid var(--border);
}
.toggle-row:last-child { border-bottom:none; }
.toggle-label { font-weight:700; font-size:0.85rem; }
.toggle {
    position:relative; width:44px; height:24px; background:var(--border);
    border-radius:12px; cursor:pointer; transition:background 0.15s;
    flex-shrink:0;
}
.toggle::after {
    content:""; position:absolute; top:2px; left:2px;
    width:20px; height:20px; background:#fff; border-radius:50%;
    transition:transform 0.18s cubic-bezier(0.4,0,0.2,1);
    box-shadow:0 1px 3px rgba(0,0,0,0.15);
}
.toggle.on { background:var(--accent); }
.toggle.on::after { transform:translateX(20px); }
.install-btn {
    width:100%; padding:11px; border-radius:10px; border:none;
    background:linear-gradient(135deg,var(--accent),#7950f2); color:white;
    font-weight:800; font-size:0.88rem; cursor:pointer; font-family:inherit;
}
[data-theme="cosmic"] .install-btn { background:linear-gradient(135deg,#b794f6,#7cf5c0); color:#1a1030; }
.link-btn {
    background:none; border:none; color:var(--text-muted); font-weight:600;
    font-size:0.8rem; cursor:pointer; padding:6px 4px; text-decoration:underline;
    font-family:inherit;
}
.installed-badge { color:var(--today-badge); font-weight:700; font-size:0.88rem; padding:6px 0; }
.hint-text { color:var(--text-muted); font-size:0.8rem; line-height:1.4; margin-top:4px; }

/* === ТАБЫ ПН–СБ === */
.tabs {
    display:flex; gap:5px; margin-bottom:14px; overflow-x:auto;
    padding:4px; scrollbar-width:none;
    background:var(--card-bg); border-radius:16px; border:1px solid var(--border);
    box-shadow:var(--shadow);
}
.tabs::-webkit-scrollbar { display:none; }
.tab {
    flex:1; min-width:48px; padding:10px 6px; border-radius:11px; border:none;
    background:transparent; color:var(--text-muted); font-weight:800; font-size:0.85rem;
    cursor:pointer; font-family:inherit;
    display:flex; flex-direction:column; align-items:center; gap:2px; position:relative;
    transition:background 0.15s ease, color 0.15s ease;
}
.tab .tab-day { font-size:0.65rem; font-weight:700; opacity:0.7; }
.tab.active { background:linear-gradient(135deg,var(--accent),#7950f2); color:white; }
[data-theme="cosmic"] .tab.active { background:linear-gradient(135deg,#b794f6,#7cf5c0); color:#1a1030; }
.tab.active .tab-day { opacity:0.9; }
.tab.today:not(.active)::after {
    content:""; position:absolute; bottom:3px; left:50%; transform:translateX(-50%);
    width:4px; height:4px; border-radius:50%; background:var(--accent);
}

/* === LIVE BANNER === */
.live-banner {
    border-radius:16px; padding:14px 16px; margin-bottom:14px;
    display:flex; align-items:center; gap:12px; box-shadow:var(--shadow);
    border:1px solid var(--border);
    animation:fadeIn 0.3s ease;
}
@keyframes fadeIn { from { opacity:0; transform:translateY(-4px); } to { opacity:1; transform:none; } }
.live-banner.now { background:linear-gradient(135deg,var(--accent-light),var(--card-bg)); box-shadow:0 6px 20px var(--accent-light); }
.live-banner.before { background:linear-gradient(135deg,var(--orange-soft),var(--card-bg)); }
.live-dot { width:10px; height:10px; border-radius:50%; background:var(--accent); flex-shrink:0;
    animation:pulse 1.6s infinite; }
.live-banner.before .live-dot { background:var(--orange); }
@keyframes pulse {
    0%,100% { box-shadow:0 0 0 0 var(--green); }
    70% { box-shadow:0 0 0 10px transparent; }
}
.live-info { flex:1; min-width:0; }
.live-label { font-size:0.7rem; font-weight:800; text-transform:uppercase;
    letter-spacing:0.08em; color:var(--accent); margin-bottom:3px; }
.live-banner.before .live-label { color:var(--orange); }
.live-lesson { font-size:1.02rem; font-weight:800;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.live-time { font-size:0.76rem; color:var(--text-muted); font-weight:700; margin-top:2px; }
.progress-bar { height:4px; border-radius:2px; background:var(--border); overflow:hidden; margin-top:7px; }
.progress-fill { height:100%; background:linear-gradient(90deg,var(--accent),var(--accent)); border-radius:2px; }

/* === DAY / CARDS === */
.day-block { display:none; }
.day-block.active-day { display:block; }
.day-title {
    font-size:1.12rem; font-weight:800; color:var(--text-muted); margin-bottom:12px;
    padding-left:6px; display:flex; justify-content:space-between; align-items:center;
}
.day-title.today { color:var(--text-main); }
.today-pill {
    font-size:0.68rem; background:var(--accent-light); color:var(--today-badge);
    padding:5px 11px; border-radius:20px; font-weight:800; text-transform:uppercase;
}
.card {
    background:var(--card-bg); padding:16px 18px; margin-bottom:10px; border-radius:16px;
    box-shadow:var(--shadow); display:flex; align-items:center; gap:14px;
    border:1px solid var(--border);
    animation:fadeUp 0.3s ease backwards;
}
@keyframes fadeUp {
    from { opacity:0; transform:translateY(8px); }
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
    box-shadow:0 6px 24px var(--accent-light), 0 0 0 1.5px var(--accent);
    background:linear-gradient(135deg,var(--accent-light),var(--card-bg));
}
.card.next-up { box-shadow:0 6px 20px var(--orange-soft), 0 0 0 1px var(--orange); }
.num {
    min-width:38px; height:38px; border-radius:11px;
    background:var(--num-bg); color:var(--num-color);
    display:flex; align-items:center; justify-content:center;
    font-weight:800; font-size:1.05rem; flex-shrink:0;
    box-shadow:var(--num-shadow);
}
.card.now .num { background:linear-gradient(135deg,var(--accent),var(--accent)); color:#fff; box-shadow:0 4px 14px var(--accent-light); }
.left-side { display:flex; flex-direction:column; gap:3px; flex-grow:1; min-width:0; }
.time { font-size:0.8rem; color:var(--text-muted); font-weight:700; }
.lesson { font-size:1.05rem; font-weight:800; color:var(--text-main); word-wrap:break-word; }
.now-pill {
    font-size:0.6rem; background:var(--accent); color:#fff;
    padding:3px 8px; border-radius:20px; font-weight:800;
    text-transform:uppercase; letter-spacing:0.06em;
    margin-left:auto; flex-shrink:0;
}
.error { background:rgba(224,49,49,0.1); color:var(--error); padding:16px; border-radius:16px; font-weight:700; text-align:center; }
.info-box {
    background:var(--card-bg); padding:28px 20px; border-radius:18px; box-shadow:var(--shadow);
    text-align:center; font-size:1.02rem; font-weight:700; color:var(--text-muted);
    border:1px solid var(--border);
}
.sheet-link {
    display:flex; align-items:center; justify-content:center; gap:6px;
    text-align:center; margin-top:22px; color:var(--text-muted);
    text-decoration:none; font-size:0.85rem; font-weight:700;
    padding:12px; border-radius:12px; border:1px dashed var(--border);
    background:var(--card-bg); opacity:0.85;
}

html.font-small .lesson { font-size:0.9rem; }
html.font-small .live-lesson { font-size:0.92rem; }
html.font-large .lesson { font-size:1.18rem; }
html.font-large .live-lesson { font-size:1.16rem; }
html.font-large .day-title { font-size:1.28rem; }
html.compact .card { padding:11px 14px; margin-bottom:7px; }
html.compact .num { min-width:34px; height:34px; font-size:0.9rem; }
html.compact .header-card { padding:14px 18px; }
html.hide-time .time { display:none; }

/* ========== ТЕМАТИЧЕСКИЕ НАСТРОЙКИ ========== */

/* ОБЩЕЕ — базовое скругление для кнопок-тем */
.theme-btn, .size-btn { position:relative; overflow:hidden; }

/* === КОСМОС — светящиеся плашки === */
[data-theme="cosmic"] .theme-btn {
    background:rgba(30,20,65,0.75);
    border-color:rgba(183,148,246,0.3);
    border-radius:50%;
    aspect-ratio:1;
    padding:8px 4px;
}
[data-theme="cosmic"] .theme-btn.active {
    border-color:#b794f6;
    background:linear-gradient(135deg,#b794f6,#7cf5c0);
    color:#1a1030;
}
[data-theme="cosmic"] .theme-btn:not(.active) { color:#a89cc7; }
[data-theme="cosmic"] .size-btn {
    background:rgba(30,20,65,0.75);
    border-color:rgba(183,148,246,0.3);
    border-radius:50%;
}
[data-theme="cosmic"] .size-btn.active {
    border-color:#b794f6;
    background:linear-gradient(135deg,#b794f6,#7cf5c0);
    color:#1a1030;
}
[data-theme="cosmic"] .toggle { background:rgba(183,148,246,0.25); }
[data-theme="cosmic"] .toggle.on {
    background:linear-gradient(135deg,#b794f6,#7cf5c0);
}

/* === ОКЕАН — пузырьки с бликом === */
[data-theme="ocean"] .theme-btn {
    border-radius:50% !important;
    aspect-ratio:1;
    padding:8px 4px;
    background:radial-gradient(circle at 30% 25%, rgba(255,255,255,0.95), rgba(34,211,238,0.45) 55%, rgba(8,145,178,0.7));
    border:2px solid rgba(255,255,255,0.85);
    box-shadow:0 3px 10px rgba(8,145,178,0.3), inset -3px -4px 8px rgba(8,145,178,0.25), inset 3px 3px 10px rgba(255,255,255,0.7);
    color:#0e7490;
}
[data-theme="ocean"] .theme-btn::before {
    content:""; position:absolute; top:5px; left:8px;
    width:11px; height:6px; border-radius:50%;
    background:rgba(255,255,255,0.9);
    pointer-events:none;
}
[data-theme="ocean"] .theme-btn.active {
    border-color:#fff;
    background:radial-gradient(circle at 30% 25%, #fff, #22d3ee 55%, #0891b2);
    box-shadow:0 0 0 3px rgba(255,255,255,0.4), 0 4px 14px rgba(8,145,178,0.5);
}
[data-theme="ocean"] .size-btn {
    border-radius:50% !important;
    background:radial-gradient(circle at 30% 25%, rgba(255,255,255,0.95), rgba(34,211,238,0.45) 55%, rgba(8,145,178,0.7));
    border:2px solid rgba(255,255,255,0.85);
    box-shadow:0 3px 10px rgba(8,145,178,0.3), inset -3px -4px 8px rgba(8,145,178,0.25), inset 3px 3px 10px rgba(255,255,255,0.7);
    color:#0e7490;
}
[data-theme="ocean"] .size-btn.active { border-color:#fff; box-shadow:0 0 0 3px rgba(255,255,255,0.4), 0 4px 14px rgba(8,145,178,0.5); }
[data-theme="ocean"] .toggle { background:rgba(8,145,178,0.2); }
[data-theme="ocean"] .toggle.on { background:linear-gradient(135deg,#22d3ee,#0891b2); }
[data-theme="ocean"] .settings-panel { background:rgba(255,255,255,0.97); }

/* === ЗАКАТ — тёплые градиентные кнопки === */
[data-theme="sunset"] .theme-btn {
    background:linear-gradient(135deg,#ffe4b8,#ffb572);
    border-color:rgba(249,115,22,0.2);
    color:#7c2d12;
    border-radius:14px 14px 14px 4px;
    box-shadow:0 3px 10px rgba(249,115,22,0.18);
}
[data-theme="sunset"] .theme-btn.active {
    background:linear-gradient(135deg,#f97316,#ec4899);
    color:white; border-color:transparent;
    box-shadow:0 4px 14px rgba(249,115,22,0.45), 0 0 0 2px rgba(255,255,255,0.5);
}
[data-theme="sunset"] .size-btn {
    background:linear-gradient(135deg,#ffe4b8,#ffb572);
    border-color:rgba(249,115,22,0.2);
    color:#7c2d12;
    border-radius:14px 14px 14px 4px;
}
[data-theme="sunset"] .size-btn.active {
    background:linear-gradient(135deg,#f97316,#ec4899);
    color:white; border-color:transparent;
    box-shadow:0 4px 14px rgba(249,115,22,0.45);
}
[data-theme="sunset"] .toggle.on { background:linear-gradient(135deg,#f97316,#ec4899); }
[data-theme="sunset"] .settings-panel { background:rgba(255,251,245,0.98); }

/* === ЛЕС — листочки (асимметричные скругления) === */
[data-theme="forest"] .theme-btn {
    background:linear-gradient(135deg,rgba(220,245,210,0.9),rgba(132,204,22,0.4));
    border-color:rgba(5,150,105,0.25);
    color:#064e3b;
    border-radius:24px 8px 24px 8px;
    box-shadow:0 3px 10px rgba(5,150,105,0.15);
}
[data-theme="forest"] .theme-btn.active {
    background:linear-gradient(135deg,#059669,#84cc16);
    color:white; border-color:transparent;
    box-shadow:0 4px 14px rgba(5,150,105,0.4), 0 0 0 2px rgba(255,255,255,0.5);
}
[data-theme="forest"] .size-btn {
    background:linear-gradient(135deg,rgba(220,245,210,0.9),rgba(132,204,22,0.4));
    border-color:rgba(5,150,105,0.25);
    color:#064e3b;
    border-radius:24px 8px 24px 8px;
}
[data-theme="forest"] .size-btn.active {
    background:linear-gradient(135deg,#059669,#84cc16);
    color:white; border-color:transparent;
    box-shadow:0 4px 14px rgba(5,150,105,0.4);
}
[data-theme="forest"] .toggle.on { background:linear-gradient(135deg,#059669,#84cc16); }
[data-theme="forest"] .settings-panel { background:rgba(255,255,255,0.97); }

/* === САКУРА — лепестки (мягкие круглые) === */
[data-theme="sakura"] .theme-btn {
    background:radial-gradient(circle at 30% 25%, #fff, #ffd0dd 60%, #f9a8d4);
    border-color:rgba(236,72,153,0.15);
    color:#831843;
    border-radius:50% 50% 50% 12px;
    aspect-ratio:1;
    padding:8px 4px;
    box-shadow:0 3px 10px rgba(236,72,153,0.2);
}
[data-theme="sakura"] .theme-btn::before {
    content:""; position:absolute; top:6px; left:50%;
    transform:translateX(-50%);
    width:14px; height:4px;
    background:rgba(255,255,255,0.9);
    border-radius:50%;
    filter:blur(2px);
    pointer-events:none;
}
[data-theme="sakura"] .theme-btn.active {
    background:radial-gradient(circle at 30% 25%, #fff, #ec4899 60%, #a855f7);
    color:white; border-color:transparent;
    box-shadow:0 4px 14px rgba(236,72,153,0.45), 0 0 0 2px rgba(255,255,255,0.5);
}
[data-theme="sakura"] .size-btn {
    background:radial-gradient(circle at 30% 25%, #fff, #ffd0dd 60%, #f9a8d4);
    border-color:rgba(236,72,153,0.15);
    color:#831843;
    border-radius:50% 50% 50% 12px;
}
[data-theme="sakura"] .size-btn.active {
    background:radial-gradient(circle at 30% 25%, #fff, #ec4899 60%, #a855f7);
    color:white; border-color:transparent;
    box-shadow:0 4px 14px rgba(236,72,153,0.45);
}
[data-theme="sakura"] .toggle.on { background:linear-gradient(135deg,#ec4899,#a855f7); }
[data-theme="sakura"] .settings-panel { background:rgba(255,255,255,0.97); }

/* === СВЕТЛАЯ / ТЁМНАЯ — чистый минимализм === */
[data-theme="light"] .theme-btn,
[data-theme="dark"] .theme-btn {
    border-radius:12px;
}

/* ========== ТЕМАТИЧЕСКАЯ ШАПКА ========== */

/* === КОСМОС — космическая станция === */
[data-theme="cosmic"] .header-card {
    background:rgba(30,20,65,0.85);
    border-color:rgba(183,148,246,0.28);
}
[data-theme="cosmic"] .badge-class {
    background:linear-gradient(135deg,rgba(183,148,246,0.35),rgba(124,245,192,0.2));
    color:#ece6ff;
    border:1px solid rgba(183,148,246,0.4);
    border-radius:50%;
    width:42px; height:42px;
    padding:0; display:flex; align-items:center; justify-content:center;
    font-size:0.9rem;
}
[data-theme="cosmic"] .icon-btn {
    background:linear-gradient(135deg,rgba(183,148,246,0.3),rgba(124,245,192,0.2));
    color:#ece6ff;
    border:1px solid rgba(183,148,246,0.4);
    border-radius:50%;
}
[data-theme="cosmic"] .icon-btn:active { background:linear-gradient(135deg,#b794f6,#7cf5c0); color:#1a1030; }

/* === ОКЕАН — пузыри с бликом, лёгкое парение === */
[data-theme="ocean"] .header-card {
    background:rgba(255,255,255,0.55);
    border:2px solid rgba(255,255,255,0.8);
    box-shadow:0 8px 24px rgba(8,145,178,0.18), inset 0 2px 12px rgba(255,255,255,0.85);
}
[data-theme="ocean"] .badge-class {
    background:radial-gradient(circle at 30% 25%, rgba(255,255,255,0.95), rgba(34,211,238,0.5) 55%, rgba(8,145,178,0.8));
    color:#fff;
    border:2px solid rgba(255,255,255,0.9);
    border-radius:50%;
    width:44px; height:44px;
    padding:0; display:flex; align-items:center; justify-content:center;
    font-size:0.95rem;
    box-shadow:0 3px 12px rgba(8,145,178,0.35), inset -3px -4px 8px rgba(8,145,178,0.25), inset 3px 3px 10px rgba(255,255,255,0.75);
    position:relative;
    animation:floaty 4s ease-in-out infinite;
}
[data-theme="ocean"] .badge-class::before {
    content:""; position:absolute; top:6px; left:8px;
    width:14px; height:7px; border-radius:50%;
    background:rgba(255,255,255,0.9);
    pointer-events:none;
}
[data-theme="ocean"] .icon-btn {
    background:radial-gradient(circle at 30% 25%, rgba(255,255,255,0.95), rgba(34,211,238,0.5) 55%, rgba(8,145,178,0.8));
    color:#fff;
    border:2px solid rgba(255,255,255,0.9);
    border-radius:50%;
    box-shadow:0 3px 12px rgba(8,145,178,0.35), inset -3px -4px 8px rgba(8,145,178,0.25), inset 3px 3px 10px rgba(255,255,255,0.75);
    position:relative;
    animation:floaty 5s ease-in-out infinite;
}
[data-theme="ocean"] .icon-btn::before {
    content:""; position:absolute; top:6px; left:8px;
    width:12px; height:6px; border-radius:50%;
    background:rgba(255,255,255,0.9);
    pointer-events:none;
}
[data-theme="ocean"] .icon-btn:active {
    animation:none;
    box-shadow:0 0 0 3px rgba(255,255,255,0.5), 0 2px 8px rgba(8,145,178,0.4);
}
@keyframes floaty {
    0%,100% { transform:translate3d(0,0,0); }
    50% { transform:translate3d(0,-3px,0); }
}

/* === ЗАКАТ — тёплые асимметричные формы === */
[data-theme="sunset"] .header-card {
    background:rgba(255,251,245,0.92);
    border:1px solid rgba(249,115,22,0.2);
    border-radius:24px 24px 24px 8px;
}
[data-theme="sunset"] .badge-class {
    background:linear-gradient(135deg,#f97316,#ec4899);
    color:white;
    border:none;
    border-radius:14px 14px 14px 4px;
}
[data-theme="sunset"] .icon-btn {
    background:linear-gradient(135deg,#f97316,#ec4899);
    color:white;
    border:none;
    border-radius:14px 14px 4px 14px;
}
[data-theme="sunset"] .icon-btn:active { opacity:0.85; }

/* === ЛЕС — листики === */
[data-theme="forest"] .header-card {
    background:rgba(255,255,255,0.9);
    border:1px solid rgba(5,150,105,0.2);
    border-radius:28px 12px 28px 12px;
}
[data-theme="forest"] .badge-class {
    background:linear-gradient(135deg,#059669,#84cc16);
    color:white;
    border:none;
    border-radius:24px 8px 24px 8px;
}
[data-theme="forest"] .icon-btn {
    background:linear-gradient(135deg,#059669,#84cc16);
    color:white;
    border:none;
    border-radius:24px 8px 24px 8px;
}
[data-theme="forest"] .icon-btn:active { opacity:0.85; }

/* === САКУРА — лепестки === */
[data-theme="sakura"] .header-card {
    background:rgba(255,255,255,0.9);
    border:2px solid rgba(236,72,153,0.15);
    border-radius:26px;
}
[data-theme="sakura"] .badge-class {
    background:radial-gradient(circle at 30% 25%, #fff, #ec4899 60%, #a855f7);
    color:white;
    border:none;
    border-radius:50% 50% 50% 12px;
    width:44px; height:44px;
    padding:0; display:flex; align-items:center; justify-content:center;
    font-size:0.95rem;
    box-shadow:0 3px 12px rgba(236,72,153,0.3);
    position:relative;
}
[data-theme="sakura"] .badge-class::before {
    content:""; position:absolute; top:6px; left:50%;
    transform:translateX(-50%);
    width:14px; height:4px;
    background:rgba(255,255,255,0.9);
    border-radius:50%;
    filter:blur(2px);
    pointer-events:none;
}
[data-theme="sakura"] .icon-btn {
    background:radial-gradient(circle at 30% 25%, #fff, #ec4899 60%, #a855f7);
    color:white;
    border:none;
    border-radius:50% 50% 50% 12px;
    box-shadow:0 3px 12px rgba(236,72,153,0.3);
    position:relative;
}
[data-theme="sakura"] .icon-btn::before {
    content:""; position:absolute; top:6px; left:50%;
    transform:translateX(-50%);
    width:12px; height:4px;
    background:rgba(255,255,255,0.9);
    border-radius:50%;
    filter:blur(2px);
    pointer-events:none;
}
[data-theme="sakura"] .icon-btn:active { opacity:0.85; }

/* === НОВЫЕ ТЕМЫ === */
/* === ЧЁТКОЕ КОЛЬЦО У АКТИВНОЙ (видно во всех темах) === */


/* Новые темы: базовый стиль кнопок */

/* === АКТИВНАЯ КНОПКА — чёткий бордер без прослойки === */
.theme-btn.active,
.size-btn.active {
    border: 3px solid var(--accent) !important;
    outline: none !important;
    background: linear-gradient(135deg, var(--accent), var(--accent2, var(--accent))) !important;
    color: #fff !important;
    font-weight: 800 !important;
}
[data-theme="sakura"] .theme-btn.active,
[data-theme="sakura"] .size-btn.active,
/* Убираем aspect-ratio — border больше не обрезается */
[data-theme="ocean"] .theme-btn,
[data-theme="sakura"] .theme-btn,
[data-theme="cosmic"] .theme-btn,
[data-theme="ocean"] .size-btn,
[data-theme="sakura"] .size-btn,
[data-theme="cosmic"] .size-btn { aspect-ratio: auto !important; }

/* === НОВЫЕ 5 ТЕМ === */

/* 💎 Бирюза */
/* 🍑 Персик */
/* 🌺 Магнолия */
/* 🔥 Огонь */
/* 🌈 Радуга */

/* === АКТИВНАЯ КНОПКА ТЕМЫ: чистое кольцо без прослоек === */
.theme-btn.active,
.size-btn.active {
    box-shadow: 0 0 0 3px var(--accent), 0 4px 14px var(--accent-light) !important;
    border-color: transparent !important;
}
/* В светлых темах (Океан/Сакура/Закат/Лес) — только ring + заливка через тему */
[data-theme="ocean"] .theme-btn.active,
[data-theme="sunset"] .theme-btn.active,
[data-theme="forest"] .theme-btn.active,
[data-theme="sakura"] .theme-btn.active { box-shadow: 0 0 0 3px var(--accent), 0 4px 16px var(--accent-light) !important; }

/* Убираем aspect-ratio (обрезало кольцо) */
[data-theme="ocean"] .theme-btn,
[data-theme="sakura"] .theme-btn,
[data-theme="cosmic"] .theme-btn,
[data-theme="ocean"] .size-btn,
[data-theme="sakura"] .size-btn,
[data-theme="cosmic"] .size-btn { aspect-ratio: auto !important; }

/* === УЛУЧШЕНИЯ 7 ТЕМ === */

/* СВЕТЛАЯ — мягкие тени */
[data-theme="light"] .header-card { box-shadow: 0 6px 20px rgba(99,102,241,0.08); }
[data-theme="light"] .card { border-color: rgba(99,102,241,0.06); }

/* ТЁМНАЯ — глянцевые карточки */
[data-theme="dark"] .card { border: 1px solid rgba(255,255,255,0.08); box-shadow: 0 4px 18px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04); }
[data-theme="dark"] .header-card { border: 1px solid rgba(255,255,255,0.09); box-shadow: 0 6px 24px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.05); }

/* КОСМОС — насыщенней туманности и свечение */
[data-theme="cosmic"] .header-card {
    border:1px solid rgba(183,148,246,0.35);
    box-shadow:0 8px 32px rgba(120,60,220,0.35), inset 0 1px 0 rgba(255,255,255,0.08);
}
[data-theme="cosmic"] .card {
    border:1px solid rgba(183,148,246,0.28);
    box-shadow:0 6px 22px rgba(120,60,220,0.28), inset 0 1px 0 rgba(255,255,255,0.06);
}

/* ОКЕАН — волны снизу + блики */
[data-theme="ocean"] .card {
    background:rgba(255,255,255,0.96);
    border:1px solid rgba(34,211,238,0.25);
    box-shadow:0 4px 16px rgba(8,145,178,0.14), inset 0 1px 0 rgba(255,255,255,0.9);
}
[data-theme="ocean"] .header-card {
    border:2px solid rgba(255,255,255,0.85);
    box-shadow:0 8px 28px rgba(8,145,178,0.22), inset 0 2px 14px rgba(255,255,255,0.85);
}

/* ЗАКАТ — тёплое свечение снизу */
[data-theme="sunset"] .card {
    background:rgba(255,252,245,0.96);
    border:1px solid rgba(249,115,22,0.18);
    box-shadow:0 4px 16px rgba(249,115,22,0.16), inset 0 1px 0 rgba(255,255,255,0.9);
}
[data-theme="sunset"] .header-card {
    border:1px solid rgba(249,115,22,0.22);
    box-shadow:0 6px 24px rgba(249,115,22,0.2);
}

/* ЛЕС — органичные тени */
[data-theme="forest"] .card {
    background:rgba(255,255,255,0.96);
    border:1px solid rgba(5,150,105,0.2);
    box-shadow:0 4px 16px rgba(5,150,105,0.14), inset 0 1px 0 rgba(255,255,255,0.9);
}
[data-theme="forest"] .header-card {
    border:1px solid rgba(5,150,105,0.2);
    box-shadow:0 6px 24px rgba(5,150,105,0.18);
}

/* САКУРА — лепестковое свечение */
[data-theme="sakura"] .card {
    background:rgba(255,255,255,0.96);
    border:1px solid rgba(236,72,153,0.16);
    box-shadow:0 4px 16px rgba(236,72,153,0.14), inset 0 1px 0 rgba(255,255,255,0.9);
}
[data-theme="sakura"] .header-card {
    border:2px solid rgba(236,72,153,0.18);
    box-shadow:0 6px 24px rgba(236,72,153,0.18);
}

/* === КРАСОТА — без тормозов === */

/* Атмосферные фоны для каждой темы */
[data-theme="light"] body {
    background-image:
        radial-gradient(ellipse at 20% 10%, rgba(99,102,241,0.15), transparent 45%),
        radial-gradient(ellipse at 80% 90%, rgba(168,85,247,0.10), transparent 45%),
        linear-gradient(180deg,#f1f5fa 0%,#e4ebf3 100%);
}
[data-theme="dark"] body {
    background-image:
        radial-gradient(ellipse at 20% 10%, rgba(99,102,241,0.18), transparent 45%),
        radial-gradient(ellipse at 80% 90%, rgba(192,132,252,0.12), transparent 45%),
        linear-gradient(180deg,#10131a 0%,#0b0d12 100%);
}
[data-theme="cosmic"] body {
    background-image:
        radial-gradient(ellipse at 20% 15%, rgba(139,92,246,0.32), transparent 45%),
        radial-gradient(ellipse at 85% 75%, rgba(56,189,248,0.22), transparent 50%),
        radial-gradient(ellipse at 60% 40%, rgba(124,245,192,0.10), transparent 55%),
        linear-gradient(180deg,#0a0424 0%,#05021a 55%,#01000a 100%);
}
[data-theme="ocean"] body {
    background-image:
        radial-gradient(ellipse at 50% 0%, rgba(255,255,255,0.55), transparent 50%),
        radial-gradient(ellipse at 20% 80%, rgba(34,211,238,0.25), transparent 50%),
        linear-gradient(180deg,#c7e8f5 0%,#94d0e6 45%,#5aafd0 100%);
}
[data-theme="sunset"] body {
    background-image:
        radial-gradient(circle at 75% 25%, rgba(255,240,180,0.55), transparent 30%),
        radial-gradient(circle at 75% 25%, rgba(255,180,90,0.4), transparent 45%),
        linear-gradient(180deg,#ffe0a8 0%,#ffb572 40%,#e88898 100%);
}
[data-theme="forest"] body {
    background-image:
        radial-gradient(ellipse at 50% 0%, rgba(255,255,255,0.5), transparent 45%),
        radial-gradient(ellipse at 15% 85%, rgba(132,204,22,0.22), transparent 50%),
        linear-gradient(180deg,#dff0d0 0%,#b8dfa8 40%,#7abb6c 100%);
}
[data-theme="sakura"] body {
    background-image:
        radial-gradient(ellipse at 85% 15%, rgba(255,180,215,0.7), transparent 45%),
        radial-gradient(ellipse at 15% 80%, rgba(220,180,255,0.5), transparent 45%),
        linear-gradient(180deg,#ffeaf0 0%,#ffd0dd 50%,#ffb0c8 100%);
}

/* Космос — звёзды поверх фона */
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
    animation:twinkle 5s ease-in-out infinite alternate;
}
@keyframes twinkle { 0% { opacity:0.6; } 100% { opacity:1; } }

/* Океан — волны снизу */
[data-theme="ocean"] body::before {
    content:""; position:fixed; left:0; right:0; bottom:0;
    height:160px; z-index:0; pointer-events:none;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 160' preserveAspectRatio='none'><path d='M0,80 Q75,40 150,80 T300,80 T450,80 T600,80 L600,160 L0,160 Z' fill='%230891b2' opacity='0.3'/><path d='M0,110 Q75,70 150,110 T300,110 T450,110 T600,110 L600,160 L0,160 Z' fill='%2306b6d4' opacity='0.45'/><path d='M0,135 Q75,105 150,135 T300,135 T450,135 T600,135 L600,160 L0,160 Z' fill='%23064a5c' opacity='0.5'/></svg>");
    background-size:100% 100%; background-repeat:repeat-x;
}
[data-theme="ocean"] body::after {
    content:""; position:fixed; top:40px; right:30px;
    width:120px; height:120px; border-radius:50%; z-index:0; pointer-events:none;
    background:radial-gradient(circle, rgba(255,255,255,0.5), transparent 70%);
    animation:floatUp 6s ease-in-out infinite alternate;
}
@keyframes floatUp { from { transform:translateY(0); } to { transform:translateY(-10px); } }

/* Закат — пульсирующее солнце */
[data-theme="sunset"] body::before {
    content:""; position:fixed; top:60px; right:50px;
    width:160px; height:160px; border-radius:50%; z-index:0; pointer-events:none;
    background:radial-gradient(circle, rgba(255,250,200,0.9) 0%, rgba(255,200,120,0.5) 40%, transparent 70%);
    animation:sunPulse 6s ease-in-out infinite;
}
@keyframes sunPulse {
    0%,100% { transform:scale(1); opacity:0.9; }
    50% { transform:scale(1.08); opacity:1; }
}

/* Лес — силуэты ёлок снизу */
[data-theme="forest"] body::before {
    content:""; position:fixed; left:0; right:0; bottom:0;
    height:150px; z-index:0; pointer-events:none;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 150' preserveAspectRatio='none'><g fill='%232d5a1f' opacity='0.55'><path d='M30,150 L30,100 L15,100 L40,65 L65,100 L50,100 L50,150 Z'/><path d='M110,150 L110,90 L90,90 L120,50 L150,90 L130,90 L130,150 Z'/><path d='M200,150 L200,110 L185,110 L210,75 L235,110 L220,110 L220,150 Z'/><path d='M290,150 L290,95 L270,95 L300,55 L330,95 L310,95 L310,150 Z'/><path d='M370,150 L370,105 L355,105 L380,70 L405,105 L390,105 L390,150 Z'/></g></svg>");
    background-size:100% 100%; background-repeat:repeat-x;
}

/* Сакура — розовые пятна */
[data-theme="sakura"] body::before {
    content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
    background-image:
        radial-gradient(circle at 15% 20%, rgba(236,72,153,0.18), transparent 25%),
        radial-gradient(circle at 85% 15%, rgba(255,150,200,0.2), transparent 30%),
        radial-gradient(circle at 75% 75%, rgba(236,72,153,0.12), transparent 30%),
        radial-gradient(circle at 25% 85%, rgba(255,192,220,0.18), transparent 25%);
    animation:softFloat 8s ease-in-out infinite alternate;
}
@keyframes softFloat { from { transform:translateY(0); } to { transform:translateY(-8px); } }

/* Частицы (JS создаёт) */
#particles { position:fixed; inset:0; pointer-events:none; z-index:1; overflow:hidden; }
.particle {
    position:absolute; top:-40px; user-select:none;
    animation-name:fall; animation-timing-function:linear; animation-iteration-count:infinite;
    will-change:transform;
}
@keyframes fall {
    0% { transform:translate3d(0,-40px,0) rotate(0deg); opacity:0; }
    10% { opacity:0.85; }
    90% { opacity:0.85; }
    100% { transform:translate3d(30px,110vh,0) rotate(360deg); opacity:0; }
}

/* Улучшенные тени карточек */
.card {
    box-shadow: 0 3px 14px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.03);
}
[data-theme="cosmic"] .card {
    box-shadow: 0 4px 20px rgba(120,60,220,0.25), 0 0 0 1px rgba(183,148,246,0.15);
}
[data-theme="ocean"] .card {
    box-shadow: 0 3px 14px rgba(8,145,178,0.14);
}
[data-theme="sunset"] .card {
    box-shadow: 0 3px 14px rgba(249,115,22,0.14);
}
[data-theme="forest"] .card {
    box-shadow: 0 3px 14px rgba(5,150,105,0.12);
}
[data-theme="sakura"] .card {
    box-shadow: 0 3px 14px rgba(236,72,153,0.12);
}

/* Логотип: лёгкая тень */
.brand-logo { box-shadow:0 4px 14px var(--accent-light, rgba(0,0,0,0.08)); }
[data-theme="cosmic"] .brand-logo { box-shadow:0 4px 18px rgba(183,148,246,0.4); }

/* Кнопки-темы: мягкий подъём */
.theme-btn, .size-btn { transition: background 0.15s, box-shadow 0.15s, transform 0.1s; }
.theme-btn:active, .size-btn:active { transform: scale(0.94); }
</style>
</head>
<body>
<div id="particles"></div>
<div class="container">

<div class="header-card">
    <h2>📅 <span>Расписание</span></h2>
    <div class="header-right">
        <div class="badge-class">8Г</div>
        <button class="icon-btn" onclick="toggleSettings(event)" title="Настройки">⚙️</button>
    </div>

    <div class="settings-panel" id="settingsPanel">
        <div class="settings-title">🎨 Тема</div>
        <div class="theme-options">
            <button class="theme-btn" data-theme-btn="light" onclick="setTheme('light')"><span class="emoji">☀️</span>Светлая</button>
            <button class="theme-btn" data-theme-btn="dark" onclick="setTheme('dark')"><span class="emoji">🌙</span>Тёмная</button>
            <button class="theme-btn" data-theme-btn="cosmic" onclick="setTheme('cosmic')"><span class="emoji">🌌</span>Космос</button>
            <button class="theme-btn" data-theme-btn="ocean" onclick="setTheme('ocean')"><span class="emoji">🌊</span>Океан</button>
            <button class="theme-btn" data-theme-btn="sunset" onclick="setTheme('sunset')"><span class="emoji">🌅</span>Закат</button>
            <button class="theme-btn" data-theme-btn="forest" onclick="setTheme('forest')"><span class="emoji">🌿</span>Лес</button>
            <button class="theme-btn" data-theme-btn="sakura" onclick="setTheme('sakura')"><span class="emoji">🌸</span>Сакура</button>
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
{tabs}
{content}

<a class="sheet-link" href="{sheet_url}" target="_blank" rel="noopener">📊 Открыть таблицу в Google Sheets</a>
</div>

<script>
(function() {
    var saved = localStorage.getItem('rs_theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    var meta = document.getElementById('themeColorMeta');
    var colors = {light:'#f0f4f8', dark:'#0f1115', cosmic:'#05021a', ocean:'#b8e0f0', sunset:'#ffd9b0', forest:'#c9e6bf', sakura:'#ffd6e4'};
var icons = {light:'☀️', dark:'🌙', cosmic:'🌌', ocean:'🌊', sunset:'🌅', forest:'🌿', sakura:'🌸'};
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
    var colors = {light:'#f0f4f8', dark:'#0f1115', cosmic:'#05021a', ocean:'#b8e0f0', sunset:'#ffd9b0', forest:'#c9e6bf', sakura:'#ffd6e4'};
var icons = {light:'☀️', dark:'🌙', cosmic:'🌌', ocean:'🌊', sunset:'🌅', forest:'🌿', sakura:'🌸'};
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
function toggleSettings(e) {
    if (e) e.stopPropagation();
    document.getElementById('settingsPanel').classList.toggle('open');
}
document.addEventListener('click', function(e) {
    var p = document.getElementById('settingsPanel');
    if (!p.classList.contains('open')) return;
    if (p.contains(e.target)) return;
    if (e.target.closest('.icon-btn')) return;
    p.classList.remove('open');
});
function showDay(day) {
    document.querySelectorAll('.day-block').forEach(function(el) { el.classList.remove('active-day'); });
    var t = document.getElementById('block-' + day);
    if (t) t.classList.add('active-day');
    document.querySelectorAll('.tab').forEach(function(x) {
        x.classList.toggle('active', x.getAttribute('data-day') === day);
    });
}
var deferredPrompt = null;
var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e) { e.preventDefault(); deferredPrompt = e; renderInstallSection(); });
window.addEventListener('appinstalled', function() { deferredPrompt = null; localStorage.setItem('rs_installed','1'); renderInstallSection(); });
function renderInstallSection() {
    var el = document.getElementById('installSection');
    if (!el) return;
    if (isStandalone || localStorage.getItem('rs_installed') === '1') {
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>';
        return;
    }
    if (deferredPrompt) {
        el.innerHTML = '<button class="install-btn" onclick="doInstall()">📲 Установить приложение</button>';
        return;
    }
    var ua = navigator.userAgent, hint;
    if (/iPhone|iPad|iPod/i.test(ua)) hint = 'iPhone: Safari → «Поделиться» → «На экран Домой».';
    else if (/Android/i.test(ua)) hint = 'Android: Chrome → ⋮ → «Установить приложение».';
    else hint = 'ПК: в Chrome — иконка в адресной строке.';
    el.innerHTML = '<div class="hint-text">📱 ' + hint + '</div>';
}
function doInstall() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(function(c) {
        if (c.outcome === 'accepted') localStorage.setItem('rs_installed','1');
        deferredPrompt = null; renderInstallSection();
    });
}




/* === ЧАСТИЦЫ ПО ТЕМАМ === */
function spawnParticles(theme) {
    var container = document.getElementById('particles');
    if (!container) return;
    container.innerHTML = '';
    if (window.innerWidth < 300) return;
    var configs = {
        cosmic: { chars: ['✦','✧','·','+'], colors: ['#ffffff','#b794f6','#7cf5c0','#e0d4ff'], count: 18, sizes: [10,18], dur: [15,28] },
        sakura: { chars: ['🌸','🌸','❀'], colors: ['#ec4899','#f9a8d4','#fbcfe8'], count: 14, sizes: [14,22], dur: [11,20] },
        forest: { chars: ['🍃','🌿'], colors: ['#059669','#16a34a','#84cc16'], count: 12, sizes: [14,22], dur: [13,24] },
        ocean:  { chars: ['●','○','·'], colors: ['rgba(34,211,238,0.75)','rgba(8,145,178,0.65)','rgba(255,255,255,0.55)'], count: 12, sizes: [8,16], dur: [11,20] },
        sunset: { chars: ['✨','·','✦'], colors: ['#f97316','#ec4899','#fbbf24'], count: 10, sizes: [10,18], dur: [13,22] }
    };
    var cfg = configs[theme];
    if (!cfg) return;
    var isMobile = window.innerWidth < 820;
    var n = isMobile ? Math.max(6, Math.round(cfg.count * 0.6)) : cfg.count;
    var frag = document.createDocumentFragment();
    for (var i = 0; i < n; i++) {
        var el = document.createElement('span');
        el.className = 'particle';
        el.textContent = cfg.chars[Math.floor(Math.random() * cfg.chars.length)];
        el.style.left = (Math.random() * 100) + '%';
        var size = cfg.sizes[0] + Math.random() * (cfg.sizes[1] - cfg.sizes[0]);
        el.style.fontSize = size + 'px';
        el.style.color = cfg.colors[Math.floor(Math.random() * cfg.colors.length)];
        var dur = cfg.dur[0] + Math.random() * (cfg.dur[1] - cfg.dur[0]);
        el.style.animationDuration = dur + 's';
        el.style.animationDelay = (-Math.random() * dur) + 's';
        frag.appendChild(el);
    }
    container.appendChild(frag);
}
spawnParticles(localStorage.getItem('rs_theme') || 'light');
document.addEventListener('visibilitychange', function() {
    var ps = document.hidden ? 'paused' : 'running';
    document.querySelectorAll('.particle').forEach(function(p) { p.style.animationPlayState = ps; });
});

renderInstallSection();
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js').catch(function() {});
    });
}

/* === ЖИВОЙ ТАЙМЕР === */
(function(){
    function pad(n){ return (n<10?'0':'')+n; }
    function update(){
        var nowSec = Math.floor(Date.now()/1000);
        var nowEl = document.querySelector('.live-banner.now');
        if (nowEl) {
            var endUnix = parseInt(nowEl.getAttribute('data-end-unix'), 10);
            var until = nowEl.getAttribute('data-until') || '';
            var tEl = nowEl.querySelector('.live-timer');
            if (endUnix && tEl) {
                var left = Math.max(0, Math.ceil((endUnix - nowSec) / 60));
                tEl.textContent = 'до ' + until + ' · осталось ' + left + ' мин';
            }
        }
        var beforeEl = document.querySelector('.live-banner.before');
        if (beforeEl) {
            var startUnix = parseInt(beforeEl.getAttribute('data-start-unix'), 10);
            var startStr = beforeEl.getAttribute('data-start') || '';
            var tEl2 = beforeEl.querySelector('.live-timer');
            if (startUnix && tEl2) {
                var wait = Math.max(0, Math.ceil((startUnix - nowSec) / 60));
                tEl2.textContent = 'в ' + startStr + ' · через ' + wait + ' мин';
            }
        }
    }
    update();
    setInterval(update, 10000);
    document.addEventListener('visibilitychange', function(){
        if (!document.hidden) update();
    });
})();

</script>
</body>
</html>"""


def build_tabs(active_day, days_schedule):
    today_idx = datetime.now(PERM_TZ).weekday()
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
    if not status: return ""
    if status["type"] == "now":
        return ('<div class="live-banner now" data-end-unix="' + str(status["end_unix"]) + '" data-until="' + status["until"] + '"><div class="live-dot"></div>'
            '<div class="live-info"><div class="live-label">Сейчас идёт</div>'
            f'<div class="live-lesson">{status["lesson"]}</div>'
            f'<div class="live-time"><span class="live-timer">до {status["until"]}</span></div>'
            f'<div class="progress-bar"><div class="progress-fill" style="width:{status["progress"]}%"></div></div>'
            '</div></div>')
    if status["type"] == "before":
        return ('<div class="live-banner before" data-start-unix="' + str(status["start_unix"]) + '" data-start="' + status["start"] + '"><div class="live-dot"></div>'
            '<div class="live-info"><div class="live-label">Скоро урок</div>'
            f'<div class="live-lesson">{status["lesson"]}</div>'
            f'<div class="live-time"><span class="live-timer">в {status["start"]}</span></div>'
            '</div></div>')
    return ""


def build_content(days_schedule, active_day, error_msg, live_status):
    if error_msg and not days_schedule:
        return f"<div class='error'>{error_msg}</div>"
    today_idx = datetime.now(PERM_TZ).weekday()
    today_full = DAY_FULL[today_idx] if today_idx < 6 else ""
    html = ""
    for full in DAY_FULL:
        lessons = days_schedule.get(full, [])
        is_active = " active-day" if full == active_day else ""
        html += f'<div class="day-block{is_active}" id="block-{full}">'
        if full == today_full:
            html += f'<div class="day-title today"><span>{full}</span><span class="today-pill">✨ Сегодня</span></div>'
        else:
            html += f'<div class="day-title"><span>{full}</span></div>'
        if not lessons:
            html += '<div class="info-box">📭 Нет уроков на этот день</div>'
        else:
            for tv, num, lesson in lessons:
                cls = "card"; pill = ""
                if full == today_full and live_status and live_status["type"] == "now" and num == live_status["num"]:
                    cls += " now"; pill = '<span class="now-pill">сейчас</span>'
                elif full == today_full and live_status and live_status["type"] == "before" and num == live_status["num"]:
                    cls += " next-up"
                html += f'<div class="{cls}"><div class="num">{num}</div>'
                html += f'<div class="left-side"><div class="time">{tv}</div>'
                html += f'<div class="lesson">{lesson}</div></div>{pill}</div>'
        html += '</div>'
    return html


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
            current_day_name = DAY_FULL[weekday_idx] if weekday_idx < 6 else "Суббота"
            is_weekend = (weekday_idx >= 5)
            refresh_tag = "<meta http-equiv='refresh' content='90'>" if not (1 <= hour < 5) else ""

            days_schedule, error_msg = get_schedule()

            today_lessons = days_schedule.get(current_day_name, [])
            school_over = (hour > 14 or (hour == 14 and minute >= 40) or is_weekend or not today_lessons)
            if school_over and weekday_idx < 5:
                next_idx = weekday_idx + 1
                if next_idx < 6:
                    tomorrow = DAY_FULL[next_idx]
                    active_day = tomorrow if days_schedule.get(tomorrow) else current_day_name
                else:
                    active_day = current_day_name
            else:
                active_day = current_day_name
            if active_day not in DAY_FULL: active_day = current_day_name
            if not days_schedule.get(active_day) and days_schedule.get(current_day_name):
                active_day = current_day_name

            live_status = get_live_status(today_lessons) if not is_weekend else None
            live_banner = build_live_banner(live_status)
            tabs = build_tabs(active_day, days_schedule)
            content = build_content(days_schedule, active_day, error_msg, live_status)

            html = PAGE_TEMPLATE
            html = html.replace("{refresh_tag}", refresh_tag)
            html = html.replace("{live_banner}", live_banner)
            html = html.replace("{tabs}", tabs)
            html = html.replace("{content}", content)
            html = html.replace("{sheet_url}", SHEET_URL)

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
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
