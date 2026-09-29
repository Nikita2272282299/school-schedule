import threading, urllib.request, csv, io, time, os, json
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


CACHE_FILE = "schedule_cache.json"

def _week_key():
    now = datetime.now(PERM_TZ)
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]}"

def load_disk_cache():
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('week') != _week_key():
            return None
        days = {}
        for k, v in data.get('days', {}).items():
            days[k] = [tuple(x) for x in v]
        return days
    except Exception:
        return None

def save_disk_cache(days):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'week': _week_key(),
                'days': {k: [list(x) for x in v] for k, v in days.items()}
            }, f, ensure_ascii=False)
    except Exception:
        pass


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
        disk = load_disk_cache()
        if disk:
            cache["days_schedule"] = disk
            cache["last_update"] = now
            return disk, ""
        cache["error_msg"] = "Офлайн-режим (нет сети)"
    if days_schedule:
        save_disk_cache(days_schedule)
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
    
}
 100% { opacity:1; } }
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
    
}
 100% { opacity:1; } }

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
    
}
 to { transform:translateY(-10px); } }

/* Закат — пульсирующее солнце */
[data-theme="sunset"] body::before {
    content:""; position:fixed; top:60px; right:50px;
    width:160px; height:160px; border-radius:50%; z-index:0; pointer-events:none;
    background:radial-gradient(circle, rgba(255,250,200,0.9) 0%, rgba(255,200,120,0.5) 40%, transparent 70%);
    
}

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
    
}
 to { transform:translateY(-8px); } }

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

/* === ТЕМАТИЧЕСКИЕ КАРТОЧКИ УРОКОВ === */

/* 🌿 ЛЕС — деревянные доски / кора */
[data-theme="forest"] .card {
    background:
        linear-gradient(180deg, rgba(140,100,60,0.15) 0%, rgba(90,60,30,0.05) 100%),
        linear-gradient(90deg,
            rgba(180,140,90,0.12) 0%, transparent 3%,
            transparent 10%, rgba(140,100,60,0.08) 12%, transparent 15%,
            transparent 45%, rgba(140,100,60,0.06) 47%, transparent 50%,
            transparent 82%, rgba(140,100,60,0.08) 84%, transparent 88%,
            rgba(180,140,90,0.1) 100%),
        linear-gradient(180deg, #f5ecd8 0%, #e8d9b8 40%, #d8c498 100%);
    border: 1px solid rgba(90,60,30,0.25);
    border-radius: 10px 6px 10px 6px;
    box-shadow: 0 3px 10px rgba(60,40,20,0.2), inset 0 1px 0 rgba(255,240,210,0.6), inset 0 -2px 4px rgba(90,60,30,0.12);
    position: relative;
    overflow: hidden;
}
[data-theme="forest"] .card::before {
    content:""; position:absolute; inset:0; pointer-events:none;
    background:
        repeating-linear-gradient(90deg, transparent 0px, transparent 28px, rgba(90,60,30,0.06) 28px, rgba(90,60,30,0.06) 29px);
    opacity:0.7;
}
[data-theme="forest"] .card::after {
    content:""; position:absolute; top:8px; bottom:8px; left:6px; width:2px;
    background:linear-gradient(180deg, transparent, rgba(90,60,30,0.2), transparent);
    border-radius:1px;
}
[data-theme="forest"] .card.now {
    background:
        linear-gradient(180deg, rgba(140,200,80,0.35) 0%, rgba(80,150,40,0.15) 100%),
        linear-gradient(180deg, #f0f8dd 0%, #d4e8a8 40%, #a8d478 100%);
    border-color: rgba(80,140,40,0.5);
    box-shadow: 0 3px 14px rgba(80,140,40,0.3), inset 0 1px 0 rgba(255,255,255,0.7);
}
[data-theme="forest"] .num {
    background: linear-gradient(180deg, #c9a86a 0%, #a8874a 50%, #8a6a2f 100%);
    color: #fffbf0;
    border-radius: 8px 4px 8px 4px;
    border: 1px solid rgba(90,60,20,0.4);
    box-shadow: 0 2px 6px rgba(60,40,10,0.3), inset 0 1px 0 rgba(255,240,200,0.5);
    font-family: Georgia, serif;
    font-weight: 900;
}

/* 🌊 ОКЕАН — капли воды / стекло */
[data-theme="ocean"] .card {
    background:
        radial-gradient(ellipse at 15% 20%, rgba(255,255,255,0.6), transparent 45%),
        linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(220,245,252,0.85) 50%, rgba(180,230,245,0.8) 100%);
    border: 1px solid rgba(34,211,238,0.35);
    border-radius: 18px 18px 18px 6px;
    box-shadow: 0 6px 16px rgba(8,145,178,0.2), inset 0 2px 6px rgba(255,255,255,0.95), inset 0 -3px 6px rgba(8,145,178,0.1);
    position: relative;
    overflow: hidden;
}
[data-theme="ocean"] .card::before {
    content:""; position:absolute; top:8px; left:12px; width:44px; height:14px;
    border-radius:50%;
    background:radial-gradient(ellipse, rgba(255,255,255,0.9), transparent 70%);
    pointer-events:none;
}
[data-theme="ocean"] .card.now {
    background:
        radial-gradient(ellipse at 15% 20%, rgba(255,255,255,0.7), transparent 50%),
        linear-gradient(180deg, #b8f5e8 0%, #6ee7d0 50%, #14b8a6 100%);
    border-color: rgba(20,184,166,0.6);
    box-shadow: 0 6px 20px rgba(20,184,166,0.4), inset 0 2px 8px rgba(255,255,255,0.8);
}
[data-theme="ocean"] .num {
    background: radial-gradient(circle at 30% 25%, #ffffff, #22d3ee 55%, #0891b2 100%);
    color: #fff;
    border-radius: 50%;
    box-shadow: 0 3px 10px rgba(8,145,178,0.4), inset -3px -4px 8px rgba(8,145,178,0.3), inset 3px 3px 10px rgba(255,255,255,0.7);
    border: 2px solid rgba(255,255,255,0.9);
}

/* 🌅 ЗАКАТ — тёплый пергамент */
[data-theme="sunset"] .card {
    background:
        linear-gradient(135deg, rgba(255,220,160,0.4) 0%, rgba(255,180,120,0.2) 50%, rgba(255,150,120,0.3) 100%),
        linear-gradient(180deg, #fff8ec 0%, #ffe9cc 60%, #ffd9b0 100%);
    border: 1px solid rgba(249,115,22,0.28);
    border-radius: 16px 6px 16px 6px;
    box-shadow: 0 4px 14px rgba(249,115,22,0.22), inset 0 1px 0 rgba(255,255,255,0.85);
    position: relative;
    overflow: hidden;
}
[data-theme="sunset"] .card::before {
    content:""; position:absolute; top:-30px; right:-30px; width:100px; height:100px;
    border-radius:50%;
    background:radial-gradient(circle, rgba(255,200,100,0.4), transparent 70%);
    pointer-events:none;
}
[data-theme="sunset"] .card.now {
    background:
        linear-gradient(135deg, rgba(255,180,80,0.5) 0%, rgba(249,115,22,0.3) 50%, rgba(236,72,153,0.3) 100%),
        linear-gradient(180deg, #ffe9cc 0%, #ffb572 50%, #f97316 100%);
    border-color: rgba(249,115,22,0.6);
    box-shadow: 0 6px 20px rgba(249,115,22,0.45), inset 0 2px 6px rgba(255,255,255,0.5);
}
[data-theme="sunset"] .num {
    background: linear-gradient(135deg, #f97316 0%, #ec4899 100%);
    color: #fff;
    border-radius: 14px 4px 14px 4px;
    box-shadow: 0 3px 10px rgba(249,115,22,0.4), inset 0 1px 0 rgba(255,255,255,0.4);
}

/* 🌸 САКУРА — лепестки / мягкие */
[data-theme="sakura"] .card {
    background:
        radial-gradient(ellipse at 80% 15%, rgba(255,220,235,0.7), transparent 40%),
        radial-gradient(ellipse at 15% 85%, rgba(255,200,225,0.6), transparent 40%),
        linear-gradient(180deg, #fffafc 0%, #ffe8f0 50%, #ffd0dd 100%);
    border: 1px solid rgba(236,72,153,0.2);
    border-radius: 20px 20px 20px 8px;
    box-shadow: 0 4px 14px rgba(236,72,153,0.18), inset 0 1px 0 rgba(255,255,255,0.9);
    position: relative;
    overflow: hidden;
}
[data-theme="sakura"] .card::before {
    content:""; position:absolute; top:6px; right:10px; width:16px; height:8px;
    border-radius:50%;
    background:rgba(255,255,255,0.75);
    pointer-events:none;
    filter:blur(1px);
}
[data-theme="sakura"] .card.now {
    background:
        radial-gradient(ellipse at 80% 15%, rgba(255,200,225,0.7), transparent 50%),
        linear-gradient(180deg, #ffd0dd 0%, #f9a8d4 50%, #ec4899 100%);
    border-color: rgba(236,72,153,0.5);
    box-shadow: 0 6px 20px rgba(236,72,153,0.4), inset 0 2px 6px rgba(255,255,255,0.5);
}
[data-theme="sakura"] .num {
    background: radial-gradient(circle at 30% 25%, #ffffff 0%, #f9a8d4 50%, #ec4899 100%);
    color: #fff;
    border-radius: 50% 50% 50% 14px;
    box-shadow: 0 3px 10px rgba(236,72,153,0.35), inset 0 1px 0 rgba(255,255,255,0.6);
}

/* 🌌 КОСМОС — звёздные плиты */
[data-theme="cosmic"] .card {
    background:
        radial-gradient(1px 1px at 15% 20%, rgba(255,255,255,0.6), transparent 60%),
        radial-gradient(1px 1px at 80% 70%, rgba(183,148,246,0.7), transparent 60%),
        radial-gradient(1.5px 1.5px at 45% 85%, rgba(124,245,192,0.6), transparent 60%),
        linear-gradient(135deg, rgba(50,30,100,0.85) 0%, rgba(25,15,60,0.95) 60%, rgba(15,8,40,0.98) 100%);
    border: 1px solid rgba(183,148,246,0.3);
    border-radius: 16px;
    box-shadow: 0 6px 22px rgba(120,60,220,0.3), inset 0 1px 0 rgba(255,255,255,0.08);
    position: relative;
    overflow: hidden;
}
[data-theme="cosmic"] .card.now {
    background:
        radial-gradient(1.5px 1.5px at 20% 25%, rgba(255,255,255,0.9), transparent 60%),
        radial-gradient(1px 1px at 80% 70%, rgba(124,245,192,0.9), transparent 60%),
        linear-gradient(135deg, rgba(80,50,150,0.95) 0%, rgba(50,30,110,0.95) 60%, rgba(30,15,70,0.98) 100%);
    border-color: rgba(183,148,246,0.7);
    box-shadow: 0 6px 26px rgba(183,148,246,0.5), inset 0 0 20px rgba(124,245,192,0.15);
}
[data-theme="cosmic"] .num {
    background: linear-gradient(135deg, #b794f6 0%, #7cf5c0 100%);
    color: #1a1030;
    border-radius: 12px;
    box-shadow: 0 0 16px rgba(183,148,246,0.55), inset 0 1px 0 rgba(255,255,255,0.4);
    font-weight: 900;
}

/* ☀️ СВЕТЛАЯ — мягкий глянец */
[data-theme="light"] .card {
    background: linear-gradient(180deg, #ffffff 0%, #f7f9fc 100%);
    box-shadow: 0 3px 12px rgba(99,102,241,0.08), inset 0 1px 0 rgba(255,255,255,1);
}
[data-theme="light"] .num {
    background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
    color: #4c6ef5;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), 0 1px 3px rgba(99,102,241,0.15);
}

/* 🌙 ТЁМНАЯ — глянец */
[data-theme="dark"] .card {
    background: linear-gradient(135deg, #232733 0%, #1a1d24 60%, #15171e 100%);
    box-shadow: 0 4px 16px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06);
}
[data-theme="dark"] .num {
    background: linear-gradient(135deg, #2d3142 0%, #232741 100%);
    color: #c7d2fe;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 1px 4px rgba(0,0,0,0.4);
}

/* БОЛЬШЕ ГРАДИЕНТОВ: заголовки дней */
.day-title {
    background: linear-gradient(90deg, var(--text-main) 0%, var(--text-main) 40%, transparent 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    color: transparent;
}
[data-theme="cosmic"] .day-title {
    background: linear-gradient(90deg, #ece6ff 0%, #b794f6 50%, #7cf5c0 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
}
[data-theme="ocean"] .day-title {
    background: linear-gradient(90deg, #062b3d 0%, #0891b2 50%, #22d3ee 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
}
[data-theme="sunset"] .day-title {
    background: linear-gradient(90deg, #3d1a0a 0%, #f97316 50%, #ec4899 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
}
[data-theme="forest"] .day-title {
    background: linear-gradient(90deg, #0f2e1b 0%, #059669 50%, #84cc16 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
}
[data-theme="sakura"] .day-title {
    background: linear-gradient(90deg, #3d1029 0%, #ec4899 50%, #a855f7 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* ========== GRAPHICS 2X ========== */

/* Красивый фон — многослойные градиенты */
body {
    background-attachment: scroll;
}
[data-theme="light"] body {
    background-image:
        radial-gradient(ellipse 60% 40% at 15% 10%, rgba(99,102,241,0.18), transparent 60%),
        radial-gradient(ellipse 50% 40% at 85% 85%, rgba(168,85,247,0.14), transparent 60%),
        radial-gradient(ellipse 40% 30% at 50% 50%, rgba(56,189,248,0.06), transparent 60%),
        linear-gradient(180deg,#f5f8fc 0%,#e4ebf3 100%);
}
[data-theme="dark"] body {
    background-image:
        radial-gradient(ellipse 60% 40% at 15% 10%, rgba(99,102,241,0.22), transparent 60%),
        radial-gradient(ellipse 50% 40% at 85% 85%, rgba(192,132,252,0.16), transparent 60%),
        radial-gradient(ellipse 40% 30% at 50% 50%, rgba(56,189,248,0.06), transparent 60%),
        linear-gradient(180deg,#10131a 0%,#05060a 100%);
}
[data-theme="cosmic"] body {
    background-image:
        radial-gradient(ellipse 55% 35% at 15% 10%, rgba(139,92,246,0.45), transparent 60%),
        radial-gradient(ellipse 50% 40% at 85% 80%, rgba(56,189,248,0.3), transparent 60%),
        radial-gradient(ellipse 45% 35% at 50% 55%, rgba(124,245,192,0.15), transparent 65%),
        radial-gradient(circle at 50% 100%, rgba(120,60,220,0.35), transparent 60%),
        linear-gradient(180deg,#0a0424 0%,#05021a 55%,#01000a 100%);
}
[data-theme="ocean"] body {
    background-image:
        radial-gradient(ellipse 70% 40% at 50% 0%, rgba(255,255,255,0.7), transparent 60%),
        radial-gradient(ellipse 50% 35% at 15% 80%, rgba(34,211,238,0.35), transparent 55%),
        radial-gradient(ellipse 45% 35% at 85% 90%, rgba(6,182,212,0.25), transparent 55%),
        linear-gradient(180deg,#d6f0fa 0%,#8dcce4 45%,#4898b8 100%);
}
[data-theme="sunset"] body {
    background-image:
        radial-gradient(circle at 78% 22%, rgba(255,250,200,0.85), transparent 22%),
        radial-gradient(circle at 78% 22%, rgba(255,180,90,0.5), transparent 40%),
        radial-gradient(ellipse 60% 35% at 20% 90%, rgba(236,72,153,0.3), transparent 60%),
        linear-gradient(180deg,#ffe0a8 0%,#ffb572 40%,#e88898 100%);
}
[data-theme="forest"] body {
    background-image:
        radial-gradient(ellipse 60% 35% at 50% 0%, rgba(255,255,255,0.55), transparent 55%),
        radial-gradient(ellipse 50% 35% at 15% 85%, rgba(132,204,22,0.3), transparent 55%),
        radial-gradient(ellipse 45% 35% at 90% 80%, rgba(5,150,105,0.22), transparent 55%),
        linear-gradient(180deg,#e8f5dc 0%,#b8dfa8 40%,#7abb6c 100%);
}
[data-theme="sakura"] body {
    background-image:
        radial-gradient(ellipse 60% 40% at 85% 12%, rgba(255,180,215,0.75), transparent 55%),
        radial-gradient(ellipse 50% 40% at 10% 80%, rgba(220,180,255,0.6), transparent 55%),
        radial-gradient(circle at 50% 50%, rgba(255,220,235,0.35), transparent 45%),
        linear-gradient(180deg,#fff0f5 0%,#ffd0dd 50%,#ff9dc0 100%);
}

/* Логотип — крутая градиентная рамка */
.brand-logo {
    position: relative;
    background: linear-gradient(135deg, #fff, #f0f4ff);
    border: 2px solid transparent;
    background-clip: padding-box;
    box-shadow: 0 6px 20px rgba(99,102,241,0.25), inset 0 1px 0 rgba(255,255,255,1);
    font-size: 1.5rem;
}
.brand-logo::before {
    content: ""; position: absolute; inset: -3px; border-radius: inherit;
    background: linear-gradient(135deg, var(--accent), var(--accent2, var(--accent)));
    z-index: -1;
    filter: blur(2px);
    opacity: 0.7;
}
[data-theme="dark"] .brand-logo {
    background: linear-gradient(135deg, #232733, #1a1d24);
    box-shadow: 0 6px 20px rgba(124,147,255,0.3), inset 0 1px 0 rgba(255,255,255,0.08);
}
[data-theme="cosmic"] .brand-logo {
    background: linear-gradient(135deg, #2a1a55, #1a1040);
    box-shadow: 0 8px 26px rgba(183,148,246,0.5), inset 0 1px 0 rgba(255,255,255,0.12);
}
[data-theme="cosmic"] .brand-logo::before {
    filter: blur(4px);
    opacity: 0.9;
}

/* Заголовок — с градиентом */
h2 span {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2, var(--accent)) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* Шапка — многослойная тень */
.header-card {
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 4px 12px rgba(0,0,0,0.06),
        0 12px 32px var(--accent-light, rgba(99,102,241,0.1)),
        inset 0 1px 0 rgba(255,255,255,0.9);
}
[data-theme="dark"] .header-card,
[data-theme="cosmic"] .header-card {
    box-shadow:
        0 1px 2px rgba(0,0,0,0.4),
        0 4px 12px rgba(0,0,0,0.5),
        0 12px 32px var(--accent-light, rgba(124,147,255,0.15)),
        inset 0 1px 0 rgba(255,255,255,0.06);
}

/* Карточки — двойная тень */
.card {
    box-shadow:
        0 1px 2px rgba(0,0,0,0.03),
        0 4px 12px rgba(0,0,0,0.05),
        0 10px 28px rgba(0,0,0,0.03),
        inset 0 1px 0 rgba(255,255,255,0.6);
}
[data-theme="dark"] .card,
[data-theme="cosmic"] .card {
    box-shadow:
        0 1px 2px rgba(0,0,0,0.4),
        0 4px 14px rgba(0,0,0,0.5),
        0 10px 28px rgba(0,0,0,0.4),
        inset 0 1px 0 rgba(255,255,255,0.06);
}
[data-theme="cosmic"] .card {
    box-shadow:
        0 1px 2px rgba(0,0,0,0.4),
        0 4px 14px rgba(120,60,220,0.3),
        0 12px 32px rgba(120,60,220,0.25),
        inset 0 1px 0 rgba(255,255,255,0.08);
}

/* Табы — красивее */
.tabs {
    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 4px 14px rgba(0,0,0,0.06);
}
.tab.active {
    box-shadow:
        0 2px 6px var(--accent-light, rgba(99,102,241,0.3)),
        0 6px 16px var(--accent-light, rgba(99,102,241,0.4)),
        inset 0 1px 0 rgba(255,255,255,0.3);
    font-weight: 900;
}
.tab:not(.active) {
    transition: background 0.15s, color 0.15s, transform 0.15s;
}
.tab:not(.active):hover {
    background: var(--accent-light, rgba(99,102,241,0.1));
}

/* Кнопка настроек — свечение */
.icon-btn {
    box-shadow:
        0 2px 6px rgba(0,0,0,0.06),
        0 6px 16px var(--accent-light, rgba(99,102,241,0.15)),
        inset 0 1px 0 rgba(255,255,255,0.5);
    transition: transform 0.15s, box-shadow 0.2s;
}
.icon-btn:active {
    transform: scale(0.9);
    box-shadow: 0 1px 3px rgba(0,0,0,0.15), inset 0 2px 6px rgba(0,0,0,0.15);
}

/* Бейдж 8Г — градиент */
.badge-class {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2, var(--accent)) 100%);
    color: #fff;
    box-shadow:
        0 2px 6px rgba(0,0,0,0.1),
        0 4px 14px var(--accent-light, rgba(99,102,241,0.3)),
        inset 0 1px 0 rgba(255,255,255,0.35);
    border: none !important;
    font-weight: 900;
}

/* Номера уроков — градиент */
.num {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2, var(--accent)) 100%);
    color: #fff;
    box-shadow:
        0 2px 6px rgba(0,0,0,0.1),
        0 4px 12px var(--accent-light, rgba(99,102,241,0.25)),
        inset 0 1px 0 rgba(255,255,255,0.4);
    font-weight: 900;
}

/* Кнопки тем — глубже */
.theme-btn {
    box-shadow: 0 1px 3px rgba(0,0,0,0.05), inset 0 1px 0 rgba(255,255,255,0.5);
}
.theme-btn.active {
    box-shadow:
        0 2px 6px var(--accent-light),
        0 6px 16px var(--accent-light),
        0 0 0 3px var(--accent),
        inset 0 1px 0 rgba(255,255,255,0.3);
}

/* Тумблер — со свечением */
.toggle.on {
    box-shadow: 0 2px 8px var(--accent-light, rgba(99,102,241,0.3));
}

/* Плавные появления */
.day-block.active .card {
    animation: cardIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) backwards;
}
@keyframes cardIn {
    from { opacity: 0; transform: translate3d(0, 12px, 0) scale(0.97); }
    to { opacity: 1; transform: none; }
}
.day-block.active .card:nth-child(2) { animation-delay: 0.04s; }
.day-block.active .card:nth-child(3) { animation-delay: 0.08s; }
.day-block.active .card:nth-child(4) { animation-delay: 0.12s; }
.day-block.active .card:nth-child(5) { animation-delay: 0.16s; }
.day-block.active .card:nth-child(6) { animation-delay: 0.2s; }
.day-block.active .card:nth-child(7) { animation-delay: 0.24s; }
.day-block.active .card:nth-child(8) { animation-delay: 0.28s; }

/* ===== КРАСИВЫЕ НАСТРОЙКИ ===== */
.settings-panel {
    border-radius: 22px !important;
    padding: 18px 20px !important;
    box-shadow: 0 20px 60px rgba(0,0,0,0.18), 0 8px 24px rgba(0,0,0,0.1), inset 0 1px 0 rgba(255,255,255,0.7) !important;
}
[data-theme="dark"] .settings-panel,
[data-theme="cosmic"] .settings-panel {
    box-shadow: 0 20px 60px rgba(0,0,0,0.6), 0 8px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06) !important;
}
.settings-preview {
    height: 6px; border-radius: 3px;
    background: linear-gradient(90deg, var(--accent), var(--accent2, var(--accent)));
    margin-bottom: 16px;
    box-shadow: 0 2px 8px var(--accent-light);
}
.settings-title {
    display:flex; align-items:center; gap:8px;
    font-size:0.72rem; letter-spacing:0.08em;
    padding:0 0 8px 0;
    border-bottom:1px dashed var(--border);
    margin-bottom:12px;
}
.settings-title::before {
    content:""; width:4px; height:4px; border-radius:50%;
    background:linear-gradient(135deg, var(--accent), var(--accent2, var(--accent)));
    box-shadow:0 0 8px var(--accent);
}
.toggle-row {
    padding:11px 12px;
    border-radius:12px;
    border-bottom:none !important;
    margin-bottom:4px;
    background: linear-gradient(180deg, rgba(255,255,255,0.3), transparent);
    transition: background 0.15s;
}
.toggle-label { display:flex; align-items:center; gap:8px; font-size:0.85rem; }
.toggle-label::before { content: attr(data-ico); font-size:1.05rem; width:20px; text-align:center; }
.toggle {
    width:46px; height:26px; border-radius:13px;
    background: linear-gradient(180deg, rgba(0,0,0,0.08), rgba(0,0,0,0.15));
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.15);
}
.toggle.on {
    background: linear-gradient(135deg, var(--accent), var(--accent2, var(--accent)));
    box-shadow: inset 0 -2px 4px rgba(0,0,0,0.2), 0 2px 8px var(--accent-light);
}
.theme-btn .emoji { font-size:1.5rem !important; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.15)); }

html.hide-past .card.past { display:none; }
html.round-nums .num { border-radius: 50% !important; }
html.round-nums .card.now .num { border-radius: 50% !important; }

/* ===== БОКОВЫЕ ДЕКОРАЦИИ ПО ТЕМАМ ===== */
.side-decor {
    position: fixed;
    bottom: 0;
    width: 140px;
    height: 260px;
    z-index: 0;
    pointer-events: none;
    background-repeat: no-repeat;
    background-size: contain;
    opacity: 0.85;
}
.side-left { left: 0; background-position: left bottom; }
.side-right { right: 0; background-position: right bottom; transform: scaleX(-1); }

/* По умолчанию скрыты */
.side-decor { display: none; }

/* 🌿 ЛЕС — ёлки с обоих сторон */
[data-theme="forest"] .side-decor { display: block; }
[data-theme="forest"] .side-decor {
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 260'><g fill='%232d5a1f' opacity='0.85'><path d='M70,260 L70,150 L40,150 L75,80 L110,150 L80,150 L80,260 Z'/><path d='M70,150 L20,150 L70,50 L120,150 L70,150 Z'/><path d='M70,90 L35,90 L70,20 L105,90 Z'/></g><g fill='%233d6b30' opacity='0.7'><path d='M40,260 L40,200 L20,200 L45,150 L70,200 L55,200 L55,260 Z'/><path d='M100,260 L100,210 L85,210 L105,170 L125,210 L112,210 L112,260 Z'/></g></svg>");
}

/* 🌸 САКУРА — ствол сакуры с ветками */
[data-theme="sakura"] .side-decor { display: block; }
[data-theme="sakura"] .side-decor {
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 260'><path d='M60,260 Q55,200 60,150 Q65,100 75,70' stroke='%238b5a2b' stroke-width='14' fill='none' stroke-linecap='round'/><path d='M60,180 Q40,160 25,140' stroke='%238b5a2b' stroke-width='10' fill='none' stroke-linecap='round'/><path d='M62,140 Q85,120 105,105' stroke='%238b5a2b' stroke-width='9' fill='none' stroke-linecap='round'/><path d='M70,100 Q90,80 100,60' stroke='%238b5a2b' stroke-width='7' fill='none' stroke-linecap='round'/><g fill='%23ffb8d0'><circle cx='25' cy='140' r='7'/><circle cx='35' cy='130' r='5'/><circle cx='15' cy='130' r='5'/><circle cx='105' cy='105' r='7'/><circle cx='115' cy='95' r='5'/><circle cx='95' cy='98' r='5'/><circle cx='100' cy='60' r='6'/><circle cx='110' cy='50' r='5'/><circle cx='88' cy='52' r='5'/><circle cx='75' cy='70' r='8'/><circle cx='60' cy='150' r='6'/><circle cx='48' cy='142' r='5'/></g><g fill='%23ec4899'><circle cx='28' cy='145' r='3'/><circle cx='110' cy='100' r='3'/><circle cx='104' cy='65' r='3'/><circle cx='80' cy='75' r='3'/></g></svg>");
}

/* 🌊 ОКЕАН — водоросли снизу */
[data-theme="ocean"] .side-decor { display: none !important; }
[data-theme="ocean"] .side-decor {
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 260'><path d='M30,260 Q20,220 35,180 Q50,140 30,100 Q15,70 30,30' stroke='%2310b981' stroke-width='10' fill='none' stroke-linecap='round' opacity='0.7'/><path d='M55,260 Q70,220 55,180 Q40,140 60,100 Q75,70 60,40' stroke='%23059669' stroke-width='9' fill='none' stroke-linecap='round' opacity='0.65'/><path d='M85,260 Q70,210 85,170 Q100,130 85,90' stroke='%230ea5e9' stroke-width='8' fill='none' stroke-linecap='round' opacity='0.6'/><path d='M110,260 Q120,220 110,180 Q95,150 115,110' stroke='%2314b8a6' stroke-width='8' fill='none' stroke-linecap='round' opacity='0.55'/><g fill='%23fb7185'><circle cx='30' cy='30' r='6'/><circle cx='60' cy='40' r='5'/><circle cx='85' cy='90' r='5'/><circle cx='115' cy='110' r='6'/></g><g fill='%23fbbf24'><circle cx='45' cy='55' r='3'/><circle cx='70' cy='30' r='3'/><circle cx='100' cy='75' r='3'/></g></svg>");
}

/* 🌅 ЗАКАТ — пальма */
[data-theme="sunset"] .side-decor { display: block; }
[data-theme="sunset"] .side-decor {
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 260'><path d='M50,260 Q55,200 60,140 Q62,100 65,60' stroke='%23431407' stroke-width='10' fill='none' stroke-linecap='round'/><path d='M65,60 Q45,40 25,55 Q40,42 65,60 Q55,30 40,15 Q58,32 65,60 Q75,25 95,15 Q80,35 65,60 Q90,45 110,50 Q90,50 65,60' fill='%2316634a' opacity='0.9'/><path d='M65,60 Q85,40 105,50 Q88,50 65,60' fill='%2315803d'/><path d='M65,60 Q50,45 35,42 Q52,48 65,60' fill='%2315803d'/></svg>");
}

/* 🌌 КОСМОС — планета */
[data-theme="cosmic"] .side-decor { display: block; }
[data-theme="cosmic"] .side-decor {
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 260'><defs><radialGradient id='p' cx='35%25' cy='30%25'><stop offset='0%25' stop-color='%23e0d4ff'/><stop offset='40%25' stop-color='%23b794f6'/><stop offset='100%25' stop-color='%234c1d95'/></radialGradient></defs><circle cx='70' cy='110' r='55' fill='url(%23p)'/><ellipse cx='70' cy='110' rx='95' ry='14' fill='none' stroke='%23fbbf24' stroke-width='3' opacity='0.7' transform='rotate(-20 70 110)'/><ellipse cx='70' cy='110' rx='95' ry='14' fill='none' stroke='%23fbbf24' stroke-width='2' opacity='0.4' transform='rotate(-20 70 110)' stroke-dasharray='3 4'/><circle cx='50' cy='95' r='8' fill='%23e0d4ff' opacity='0.5'/><circle cx='90' cy='130' r='6' fill='%23e0d4ff' opacity='0.4'/><circle cx='80' cy='85' r='5' fill='%23e0d4ff' opacity='0.5'/><circle cx='30' cy='40' r='2' fill='%23fff'/><circle cx='110' cy='30' r='1.5' fill='%23fff'/><circle cx='100' cy='220' r='2' fill='%237cf5c0'/><circle cx='20' cy='180' r='1.5' fill='%23fff'/></svg>");
}

/* ☀️ СВЕТЛАЯ — облака */
[data-theme="light"] .side-decor { display: block; }
[data-theme="light"] .side-decor {
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 260'><g fill='%23ffffff' opacity='0.9'><ellipse cx='70' cy='60' rx='55' ry='28'/><ellipse cx='45' cy='50' rx='30' ry='20'/><ellipse cx='95' cy='52' rx='35' ry='22'/></g><g fill='%23e0e7ff' opacity='0.5'><ellipse cx='70' cy='150' rx='40' ry='18'/><ellipse cx='50' cy='145' rx='22' ry='12'/><ellipse cx='92' cy='148' rx='25' ry='14'/></g></svg>");
}

/* 🌙 ТЁМНАЯ — луна и облака */
[data-theme="dark"] .side-decor { display: block; }
[data-theme="dark"] .side-decor {
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 140 260'><defs><radialGradient id='m' cx='35%25' cy='35%25'><stop offset='0%25' stop-color='%23fff'/><stop offset='70%25' stop-color='%23e2e8f0'/><stop offset='100%25' stop-color='%2394a3b8'/></radialGradient></defs><circle cx='75' cy='70' r='45' fill='url(%23m)'/><circle cx='60' cy='55' r='6' fill='%23cbd5e1' opacity='0.6'/><circle cx='88' cy='80' r='5' fill='%23cbd5e1' opacity='0.5'/><circle cx='70' cy='95' r='4' fill='%23cbd5e1' opacity='0.5'/><g fill='%231f2937' opacity='0.85'><ellipse cx='70' cy='180' rx='55' ry='22'/><ellipse cx='40' cy='172' rx='28' ry='16'/><ellipse cx='100' cy='176' rx='32' ry='18'/></g><g fill='%23374151' opacity='0.7'><ellipse cx='70' cy='230' rx='50' ry='18'/><ellipse cx='45' cy='225' rx='25' ry='13'/><ellipse cx='95' cy='228' rx='28' ry='14'/></g></svg>");
}

/* На мобильных — поменьше */
@media (max-width: 500px) {
    .side-decor { width: 100px; height: 200px; opacity: 0.75; }
}

/* Когда включен режим "компактный" — не мешать */
html.compact .side-decor { opacity: 0.5; }

/* ===== КРАСИВЫЕ НАСТРОЙКИ ПОД ТЕМУ ===== */

/* Превью-полоска сверху */
.settings-preview {
    height: 8px !important;
    border-radius: 4px !important;
    background: linear-gradient(90deg, var(--accent), var(--accent2, var(--accent)), var(--accent)) !important;
    margin-bottom: 16px !important;
    box-shadow: 0 3px 12px var(--accent-light, rgba(99,102,241,0.3)) !important;
}

/* Стилизация панели под каждую тему */
[data-theme="ocean"] .settings-panel {
    border: 2px solid rgba(34,211,238,0.35);
    box-shadow: 0 20px 60px rgba(8,145,178,0.3), inset 0 2px 12px rgba(255,255,255,0.8) !important;
}
[data-theme="sunset"] .settings-panel {
    border: 2px solid rgba(249,115,22,0.25);
    box-shadow: 0 20px 60px rgba(249,115,22,0.25), inset 0 2px 12px rgba(255,255,255,0.9) !important;
}
[data-theme="forest"] .settings-panel {
    border: 2px solid rgba(5,150,105,0.25);
    box-shadow: 0 20px 60px rgba(5,150,105,0.25), inset 0 2px 12px rgba(255,255,255,0.8) !important;
}
[data-theme="sakura"] .settings-panel {
    border: 2px solid rgba(236,72,153,0.25);
    box-shadow: 0 20px 60px rgba(236,72,153,0.25), inset 0 2px 12px rgba(255,255,255,0.85) !important;
}
[data-theme="cosmic"] .settings-panel {
    border: 1px solid rgba(183,148,246,0.4);
    box-shadow: 0 20px 60px rgba(120,60,220,0.5), 0 0 40px rgba(183,148,246,0.2), inset 0 2px 12px rgba(183,148,246,0.1) !important;
}
[data-theme="dark"] .settings-panel {
    border: 1px solid rgba(255,255,255,0.1);
}
[data-theme="light"] .settings-panel {
    border: 1px solid rgba(99,102,241,0.15);
}

/* Заголовок с градиентной точкой */
.settings-title {
    background: linear-gradient(90deg, var(--text-main), var(--accent));
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
}

/* Кнопка-раздел «Дополнительно» */
.settings-section-toggle {
    width: 100%;
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: linear-gradient(135deg, var(--accent-light, rgba(99,102,241,0.1)), transparent);
    color: var(--text-main);
    font-family: inherit;
    font-weight: 800;
    font-size: 0.85rem;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: background 0.15s, transform 0.1s;
}
.settings-section-toggle:active { transform: scale(0.98); }
.settings-section-toggle .sst-arrow {
    font-size: 1rem;
    transition: transform 0.2s ease;
    color: var(--accent);
}
.settings-section-toggle.open .sst-arrow { transform: rotate(180deg); }

/* Сворачиваемый блок настроек */
.advanced-section {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), margin-top 0.25s ease;
    margin-top: 0;
}
.advanced-section.open {
    max-height: 500px;
    margin-top: 10px;
}

/* Тумблеры внутри */
.advanced-section .toggle-row {
    padding: 10px 12px;
    border-radius: 10px;
    border-bottom: none !important;
    margin-bottom: 4px;
    background: linear-gradient(180deg, rgba(255,255,255,0.4), transparent);
    transition: background 0.15s;
}
.advanced-section .toggle-row:hover { background: var(--accent-light, rgba(99,102,241,0.08)); }
.advanced-section .toggle-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.83rem;
}
.advanced-section .toggle-label::before {
    content: attr(data-ico);
    font-size: 1rem;
    width: 18px;
    text-align: center;
}

/* Панель настроек — углы под тему */
[data-theme="ocean"] .settings-panel { border-radius: 22px 22px 22px 8px !important; }
[data-theme="sunset"] .settings-panel { border-radius: 22px 8px 22px 8px !important; }
[data-theme="forest"] .settings-panel { border-radius: 26px 10px 26px 10px !important; }
[data-theme="sakura"] .settings-panel { border-radius: 24px !important; }
[data-theme="cosmic"] .settings-panel { border-radius: 22px !important; }
</style>
</head>
<body>
<div id="particles"></div>
<div class="side-decor side-left"></div>
<div class="side-decor side-right"></div>
<div class="container">

<div class="header-card">
    <h2>📅 <span>Расписание</span></h2>
    <div class="header-right">
        <div class="badge-class">8Г</div>
        <button class="icon-btn" onclick="toggleSettings(event)" title="Настройки">⚙️</button>
    </div>

    <div class="settings-panel" id="settingsPanel">
        <div class="settings-preview"></div>
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
        <button class="settings-section-toggle" onclick="toggleAdvanced()">
            <span class="sst-title">🔧 Дополнительно</span>
            <span class="sst-arrow" id="advArrow">▾</span>
        </button>
        <div class="advanced-section" id="advancedSection">
        <div class="toggle-row">
            <div class="toggle-label" data-ico="📏">Компактный режим</div>
            <div class="toggle" id="tCompact" onclick="toggleCompact()"></div>
        </div>
        <div class="toggle-row">
            <div class="toggle-label" data-ico="⏱️">Скрыть время уроков</div>
            <div class="toggle" id="tHideTime" onclick="toggleHideTime()"></div>
        </div>
        <div class="toggle-row">
            <div class="toggle-label" data-ico="✂️">Скрывать прошедшие</div>
            <div class="toggle" id="tHidePast" onclick="toggleHidePast()"></div>
        </div>
        <div class="toggle-row">
            <div class="toggle-label" data-ico="🔢">Круглые номера</div>
            <div class="toggle" id="tRoundNums" onclick="toggleRoundNums()"></div>
        </div>
        <div class="toggle-row">
            <div class="toggle-label" data-ico="✨">Частицы фона</div>
            <div class="toggle" id="tParticles" onclick="toggleParticles()"></div>
        </div>
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
    if (localStorage.getItem('rs_hide_past') === '1') document.documentElement.classList.add('hide-past');
    if (localStorage.getItem('rs_round_nums') === '1') document.documentElement.classList.add('round-nums');
    document.getElementById('tCompact').classList.toggle('on', localStorage.getItem('rs_compact') === '1');
    document.getElementById('tHideTime').classList.toggle('on', localStorage.getItem('rs_hide_time') === '1');
    var _t3=document.getElementById('tHidePast'); if(_t3) _t3.classList.toggle('on', localStorage.getItem('rs_hide_past')==='1');
    var _t4=document.getElementById('tRoundNums'); if(_t4) _t4.classList.toggle('on', localStorage.getItem('rs_round_nums')==='1');
    var _t5=document.getElementById('tParticles'); if(_t5) _t5.classList.toggle('on', localStorage.getItem('rs_particles')!=='0');
})();

function toggleHidePast(){var on=document.documentElement.classList.toggle('hide-past');localStorage.setItem('rs_hide_past',on?'1':'0');var e=document.getElementById('tHidePast');if(e)e.classList.toggle('on',on);}
function toggleRoundNums(){var on=document.documentElement.classList.toggle('round-nums');localStorage.setItem('rs_round_nums',on?'1':'0');var e=document.getElementById('tRoundNums');if(e)e.classList.toggle('on',on);}
function toggleParticles(){var on=localStorage.getItem('rs_particles')!=='0';on=!on;localStorage.setItem('rs_particles',on?'1':'0');var e=document.getElementById('tParticles');if(e)e.classList.toggle('on',on);if(on){spawnParticles(document.documentElement.getAttribute('data-theme'));}else{var c=document.getElementById('particles');if(c)c.innerHTML='';}}

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
    spawnParticles(t);
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
    if (localStorage.getItem('rs_particles') === '0') return;
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


function toggleAdvanced() {
    var sec = document.getElementById('advancedSection');
    var btn = document.querySelector('.settings-section-toggle');
    if (!sec) return;
    sec.classList.toggle('open');
    if (btn) btn.classList.toggle('open');
    localStorage.setItem('rs_adv_open', sec.classList.contains('open') ? '1' : '0');
}
(function restoreAdvanced(){
    var sec = document.getElementById('advancedSection');
    var btn = document.querySelector('.settings-section-toggle');
    if (!sec) return;
    if (localStorage.getItem('rs_adv_open') === '1') {
        sec.classList.add('open');
        if (btn) btn.classList.add('open');
    }
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
                try:
                    _end = tv.split('-')[1]
                    _eh, _em = map(int, _end.split(':'))
                    _now = datetime.now(PERM_TZ)
                    if full == today_full and (_now.hour * 60 + _now.minute) >= _eh * 60 + _em:
                        cls += " past"
                except Exception: pass
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
