import threading, urllib.request, csv, io, time, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

SPREADSHEET_ID = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SELF_URL = "https://school-schedule-4ldw.onrender.com/"
PERM_TZ = timezone(timedelta(hours=5))
CLASS_CODE = "8г"

TIME_TO_NUM = {"8:00-8:40":1,"8:50-9:30":2,"9:45-10:25":3,"10:40-11:20":4,
    "11:35-12:15":5,"12:25-13:05":6,"13:15-13:55":7,"14:00-14:40":8}
DAY_SHORT = {"Понедельник":"Пн","Вторник":"Вт","Среда":"Ср","Четверг":"Чт","Пятница":"Пт","Суббота":"Сб"}
DAY_FULL = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота"]

cache = {"days_schedule": {}, "error_msg": "", "last_update": 0}
CACHE_TTL = 300

MANIFEST = '{"name":"Расписание 8Г","short_name":"8Г","start_url":"/","display":"standalone","background_color":"#0a0620","theme_color":"#6366f1","icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6366f1"/><stop offset="0.5" stop-color="#8b5cf6"/><stop offset="1" stop-color="#a855f7"/></linearGradient><linearGradient id="glow" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity="0.35"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient></defs><rect width="512" height="512" rx="118" fill="url(#bg)"/><rect width="512" height="512" rx="118" fill="url(#glow)"/><rect x="98" y="128" width="316" height="288" rx="36" fill="#ffffff"/><rect x="98" y="128" width="316" height="76" rx="36" fill="#1e1b4b"/><rect x="98" y="176" width="316" height="28" fill="#1e1b4b"/><circle cx="168" cy="166" r="12" fill="#ffffff"/><circle cx="344" cy="166" r="12" fill="#ffffff"/><rect x="152" y="86" width="22" height="72" rx="11" fill="#1e1b4b"/><rect x="338" y="86" width="22" height="72" rx="11" fill="#1e1b4b"/><text x="256" y="358" font-family="Arial,Helvetica,sans-serif" font-size="180" font-weight="900" fill="#1e1b4b" text-anchor="middle" letter-spacing="-8">8Г</text></svg>'''

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>self.clients.claim());self.addEventListener('fetch',e=>{e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});"


def get_schedule():
    now = time.time()
    if cache["days_schedule"] and (now - cache["last_update"] < CACHE_TTL):
        return cache["days_schedule"], cache["error_msg"]
    days_schedule = {}
    error_msg = ""
    try:
        req = urllib.request.urlopen(CSV_URL, timeout=6)
        data = req.read().decode('utf-8')
        reader = list(csv.reader(io.StringIO(data)))
        col_index = -1
        for row in reader:
            for c_idx, cell in enumerate(row):
                if cell.replace(" ", "").lower() == CLASS_CODE:
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
                    cell_clean = cell.strip()
                    if cell_clean in TIME_TO_NUM:
                        time_val = cell_clean; break
                if not time_val: continue
                if len(row) > col_index:
                    lesson_val = row[col_index].strip()
                    if not lesson_val or len(lesson_val) < 2 or ":" in lesson_val: continue
                    if lesson_val.lower() in ["урок","-","—",""]: continue
                    lesson_num = TIME_TO_NUM[time_val]
                    existing = [n for t,n,l in days_schedule[current_day]]
                    if lesson_num not in existing:
                        days_schedule[current_day].append((time_val, lesson_num, lesson_val))
            for d in days_schedule:
                days_schedule[d].sort(key=lambda x: x[1])
            cache["days_schedule"] = days_schedule
            cache["error_msg"] = ""
            cache["last_update"] = now
        else:
            error_msg = f"Класс {CLASS_CODE.upper()} не найден."
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
    for time_str, num, lesson in today_lessons:
        try:
            start, end = time_str.split("-")
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
<html lang="ru" data-theme="light" data-graphics="high">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#eef2f7" id="themeColorMeta">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="8Г">
{refresh_tag}
<title>Расписание 8Г</title>
<style>
:root, [data-theme="light"] {
    --bg:#eef2f7; --bg2:#e0e7f0; --card:#ffffff;
    --text:#0f172a; --muted:#64748b; --accent:#6366f1; --accent2:#a855f7;
    --accent-soft:rgba(99,102,241,0.10); --accent-soft2:rgba(168,85,247,0.10);
    --border:rgba(15,23,42,0.06); --shadow:0 4px 20px rgba(15,23,42,0.06);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
    --danger:#ef4444;
}
[data-theme="dark"] {
    --bg:#0b0d12; --bg2:#131720; --card:#1a1f2b;
    --text:#e8ecf3; --muted:#8b95a8; --accent:#818cf8; --accent2:#c084fc;
    --accent-soft:rgba(129,140,248,0.14); --accent-soft2:rgba(192,132,252,0.14);
    --border:rgba(255,255,255,0.06); --shadow:0 4px 20px rgba(0,0,0,0.4);
    --green:#34d399; --green-soft:rgba(52,211,153,0.14);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.14);
    --danger:#f87171; color-scheme:dark;
}
[data-theme="cosmic"] {
    --bg:#05021a; --bg2:#0f0730; --card:rgba(30,20,65,0.72);
    --text:#ece6ff; --muted:#a89cc7; --accent:#b794f6; --accent2:#7cf5c0;
    --accent-soft:rgba(183,148,246,0.16); --accent-soft2:rgba(124,245,192,0.12);
    --border:rgba(183,148,246,0.14); --shadow:0 8px 32px rgba(120,60,220,0.25);
    --green:#7cf5c0; --green-soft:rgba(124,245,192,0.14);
    --orange:#fbbf77; --orange-soft:rgba(251,191,119,0.14);
    --danger:#ff8ab5; color-scheme:dark;
}
[data-theme="ocean"] {
    --bg:#e6f4fb; --bg2:#cfe8f6; --card:#ffffff;
    --text:#062b3d; --muted:#5a7d92; --accent:#0891b2; --accent2:#22d3ee;
    --accent-soft:rgba(8,145,178,0.10); --accent-soft2:rgba(34,211,238,0.10);
    --border:rgba(6,43,61,0.06); --shadow:0 4px 20px rgba(8,145,178,0.10);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
    --danger:#ef4444;
}
[data-theme="sunset"] {
    --bg:#fff1e6; --bg2:#ffe1cc; --card:#ffffff;
    --text:#3d1a0a; --muted:#8a6550; --accent:#f97316; --accent2:#ec4899;
    --accent-soft:rgba(249,115,22,0.10); --accent-soft2:rgba(236,72,153,0.10);
    --border:rgba(61,26,10,0.06); --shadow:0 4px 20px rgba(249,115,22,0.12);
    --green:#059669; --green-soft:rgba(5,150,105,0.12);
    --orange:#d97706; --orange-soft:rgba(217,119,6,0.12);
    --danger:#dc2626;
}
[data-theme="forest"] {
    --bg:#eef7ee; --bg2:#d9ecd9; --card:#ffffff;
    --text:#0f2e1b; --muted:#5f7c68; --accent:#059669; --accent2:#84cc16;
    --accent-soft:rgba(5,150,105,0.10); --accent-soft2:rgba(132,204,22,0.10);
    --border:rgba(15,46,27,0.06); --shadow:0 4px 20px rgba(5,150,105,0.10);
    --green:#16a34a; --green-soft:rgba(22,163,74,0.12);
    --orange:#ca8a04; --orange-soft:rgba(202,138,4,0.12);
    --danger:#dc2626;
}
[data-theme="sakura"] {
    --bg:#fff5f8; --bg2:#ffe1ec; --card:#ffffff;
    --text:#3d1029; --muted:#9a6782; --accent:#ec4899; --accent2:#a855f7;
    --accent-soft:rgba(236,72,153,0.10); --accent-soft2:rgba(168,85,247,0.10);
    --border:rgba(61,16,41,0.06); --shadow:0 4px 20px rgba(236,72,153,0.10);
    --green:#059669; --green-soft:rgba(5,150,105,0.12);
    --orange:#ea580c; --orange-soft:rgba(234,88,12,0.12);
    --danger:#dc2626;
}

/* ГРАФИЧЕСКИЕ РЕЖИМЫ */
/* Картошка — убираем backdrop, свечения, декорации */
[data-graphics="potato"] .header,
[data-graphics="potato"] .settings,
[data-graphics="potato"] .card,
[data-graphics="potato"] .tabs,
[data-graphics="potato"] .live-banner {
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
}
[data-graphics="potato"] body::before { display: none !important; }
[data-graphics="potato"] #particles { display: none !important; }
[data-graphics="potato"] .particle { display: none !important; }

/* Средняя — статичные декорации, без частиц, без анимаций */
[data-graphics="medium"] #particles { display: none !important; }
[data-graphics="medium"] .particle { display: none !important; }
[data-graphics="medium"] body::before { animation: none !important; }
[data-graphics="medium"] .header,
[data-graphics="medium"] .badge-class,
[data-graphics="medium"] .icon-btn { animation: none !important; }
[data-graphics="medium"] .card,
[data-graphics="medium"] .tabs,
[data-graphics="medium"] .header,
[data-graphics="medium"] .settings {
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
}

/* Красивая — всё включено */

html { min-height:100%; background:var(--bg); }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body {
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:var(--bg); color:var(--text); margin:0;
    padding:20px 14px 40px;
    min-height:100vh; -webkit-font-smoothing:antialiased;
    transition:background 0.5s ease, color 0.3s ease;
    position:relative; overflow-x:hidden;
}

/* === ДЕКОРАТИВНЫЕ ФОНЫ (только medium и high) === */
[data-theme="ocean"] body::before {
    content:""; position:absolute; left:0; right:0; bottom:0;
    height:200px; z-index:0; pointer-events:none;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 220' preserveAspectRatio='none'><path d='M0,100 Q150,30 300,100 T600,100 T900,100 T1200,100 L1200,220 L0,220 Z' fill='%230891b2' opacity='0.28'/><path d='M0,140 Q200,80 400,140 T800,140 T1200,140 L1200,220 L0,220 Z' fill='%2306b6d4' opacity='0.38'/><path d='M0,180 Q250,140 500,180 T1000,180 T1200,180 L1200,220 L0,220 Z' fill='%230891b2' opacity='0.5'/></svg>");
    background-size:1200px 220px; background-repeat:repeat-x; background-position:bottom;
}
[data-graphics="high"][data-theme="ocean"] body::before {
    animation:oceanWave 22s linear infinite;
}
@keyframes oceanWave { from { transform:translate3d(0,0,0); } to { transform:translate3d(-600px,0,0); } }

[data-theme="sunset"] body::before {
    content:""; position:absolute; top:30px; right:20px;
    width:150px; height:150px; border-radius:50%;
    background:radial-gradient(circle, rgba(255,230,140,0.95), rgba(255,150,90,0.45) 55%, transparent 75%);
    pointer-events:none; z-index:0;
}
[data-graphics="high"][data-theme="sunset"] body::before {
    animation:sunPulse 8s ease-in-out infinite;
}
@keyframes sunPulse { 0%,100% { transform:scale(1); opacity:0.9; } 50% { transform:scale(1.08); opacity:1; } }

[data-theme="forest"] body::before {
    content:""; position:absolute; left:0; right:0; top:0;
    height:140px; z-index:0; pointer-events:none;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 140' preserveAspectRatio='none'><path d='M0,0 L0,70 Q100,100 200,70 Q300,40 400,70 Q500,100 600,70 Q700,40 800,70 Q900,100 1000,70 Q1100,40 1200,70 L1200,0 Z' fill='%23059669' opacity='0.24'/></svg>");
    background-size:1200px 140px; background-repeat:repeat-x;
}
[data-theme="sakura"] body::before {
    content:""; position:absolute; inset:0; pointer-events:none; z-index:0;
    background:radial-gradient(circle at 80% 15%, rgba(236,72,153,0.14), transparent 45%),
                radial-gradient(circle at 15% 75%, rgba(168,85,247,0.10), transparent 45%);
}
[data-theme="cosmic"] body::before {
    content:""; position:absolute; inset:0; pointer-events:none; z-index:0;
    background-image:
        radial-gradient(1.5px 1.5px at 24px 32px, rgba(255,255,255,0.9), transparent 60%),
        radial-gradient(1px 1px at 118px 88px, rgba(255,255,255,0.7), transparent 60%),
        radial-gradient(1.8px 1.8px at 210px 156px, rgba(183,148,246,0.95), transparent 60%),
        radial-gradient(1px 1px at 60px 200px, rgba(255,255,255,0.6), transparent 60%),
        radial-gradient(1.5px 1.5px at 260px 40px, rgba(124,245,192,0.9), transparent 60%),
        radial-gradient(1px 1px at 180px 240px, rgba(255,255,255,0.8), transparent 60%),
        radial-gradient(1.2px 1.2px at 320px 180px, rgba(255,255,255,0.7), transparent 60%),
        radial-gradient(1.5px 1.5px at 90px 130px, rgba(183,148,246,0.8), transparent 60%);
    background-size:380px 300px; background-repeat:repeat;
}

#particles { position:absolute; inset:0; pointer-events:none; z-index:0; overflow:hidden; }
.particle {
    position:absolute; top:-40px; user-select:none;
    animation-name:fall; animation-timing-function:linear; animation-iteration-count:infinite;
}
@keyframes fall {
    0% { transform:translate3d(0,-40px,0) rotate(0deg); opacity:0; }
    10% { opacity:0.85; }
    90% { opacity:0.85; }
    100% { transform:translate3d(30px,110vh,0) rotate(360deg); opacity:0; }
}

.container { width:100%; max-width:520px; margin:0 auto; position:relative; z-index:1; }

.header {
    background:var(--card); border:1px solid var(--border); border-radius:24px;
    padding:16px 20px; box-shadow:var(--shadow); margin-bottom:14px;
    display:flex; align-items:center; justify-content:space-between; gap:12px;
}
.brand { display:flex; align-items:center; gap:12px; min-width:0; }
.brand-logo {
    width:46px; height:46px; border-radius:14px; flex-shrink:0;
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    display:flex; align-items:center; justify-content:center;
    font-size:1.5rem;
    box-shadow:0 6px 20px var(--accent-soft);
}
.brand-title { font-size:1.05rem; font-weight:800; letter-spacing:-0.02em; line-height:1.1; }
.brand-sub { font-size:0.75rem; color:var(--muted); font-weight:600; margin-top:2px; }
.header-right { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.badge-class {
    background:linear-gradient(135deg,var(--accent-soft),var(--accent-soft2));
    color:var(--accent); padding:7px 13px; border-radius:12px;
    font-weight:800; font-size:0.95rem; letter-spacing:0.02em;
    border:1px solid var(--border);
}
.icon-btn {
    background:var(--card); color:var(--muted); border:1px solid var(--border);
    width:42px; height:42px; border-radius:13px; font-size:1.15rem;
    cursor:pointer; display:flex; align-items:center; justify-content:center;
}
.icon-btn:active { color:var(--accent); background:var(--accent-soft); }

.settings {
    background:var(--card); border:1px solid var(--border); border-radius:20px;
    padding:0 18px; margin-bottom:0; box-shadow:none;
    display:grid; grid-template-rows:0fr;
    transition:grid-template-rows 0.3s cubic-bezier(0.4,0,0.2,1),
               margin-bottom 0.3s cubic-bezier(0.4,0,0.2,1),
               box-shadow 0.3s cubic-bezier(0.4,0,0.2,1);
}
.settings.open { grid-template-rows:1fr; margin-bottom:14px; box-shadow:var(--shadow); }
.settings-inner {
    overflow:hidden; min-height:0; padding:0 18px;
    transition:padding 0.3s cubic-bezier(0.4,0,0.2,1);
}
.settings.open .settings-inner { padding:18px; }
.settings-title { font-weight:800; font-size:0.8rem; color:var(--muted);
    text-transform:uppercase; letter-spacing:0.06em; margin-bottom:10px; }
.settings-title:not(:first-child) { margin-top:18px; }
.theme-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
.theme-btn {
    padding:10px 2px; border-radius:12px; border:2px solid transparent;
    background:var(--bg2); color:var(--text); font-weight:700; font-size:0.62rem;
    cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:4px;
    transition:background 0.15s, border-color 0.15s; font-family:inherit;
}
.theme-btn .emoji { font-size:1.25rem; line-height:1; }
.theme-btn.active { border-color:var(--accent); background:var(--accent-soft); }
[data-graphics="potato"] .theme-btn[data-theme-btn="ocean"],
[data-graphics="potato"] .theme-btn[data-theme-btn="sunset"],
[data-graphics="potato"] .theme-btn[data-theme-btn="forest"],
[data-graphics="potato"] .theme-btn[data-theme-btn="sakura"] { display:none; }
.graphics-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; }
.graphics-btn {
    padding:10px 4px; border-radius:12px; border:2px solid transparent;
    background:var(--bg2); color:var(--text); font-weight:700; font-size:0.62rem;
    cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:4px;
    transition:background 0.15s, border-color 0.15s; font-family:inherit;
}
.graphics-btn .emoji { font-size:1.25rem; line-height:1; }
.graphics-btn.active { border-color:var(--accent); background:var(--accent-soft); }
.size-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
.size-btn {
    padding:11px; border-radius:12px; border:2px solid var(--border);
    background:var(--bg2); color:var(--text); font-weight:800; cursor:pointer;
    font-family:inherit; transition:background 0.15s, border-color 0.15s;
}
.size-btn[data-size-btn="small"] { font-size:0.85rem; }
.size-btn[data-size-btn="normal"] { font-size:1.05rem; }
.size-btn[data-size-btn="large"] { font-size:1.25rem; }
.size-btn.active { border-color:var(--accent); background:var(--accent-soft); }
.toggle-row { display:flex; justify-content:space-between; align-items:center;
    padding:10px 0; border-bottom:1px solid var(--border); }
.toggle-row:last-child { border-bottom:none; }
.toggle-label { font-weight:700; font-size:0.9rem; }
.toggle {
    position:relative; width:48px; height:28px; background:var(--bg2); border-radius:14px;
    cursor:pointer; transition:background 0.25s; border:1px solid var(--border); flex-shrink:0;
}
.toggle::after {
    content:""; position:absolute; top:2px; left:2px; width:22px; height:22px;
    background:var(--card); border-radius:50%; transition:transform 0.25s;
    box-shadow:0 2px 6px rgba(0,0,0,0.15);
}
.toggle.on { background:linear-gradient(135deg,var(--accent),var(--accent2)); border-color:transparent; }
.toggle.on::after { transform:translateX(20px); background:white; }
.install-btn {
    width:100%; padding:13px; border-radius:14px; border:none;
    background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white;
    font-weight:800; font-size:0.9rem; cursor:pointer; font-family:inherit;
}
.install-btn:active { opacity:0.85; }
.link-btn {
    background:none; border:none; color:var(--muted); font-weight:600;
    font-size:0.82rem; cursor:pointer; padding:8px 4px; text-decoration:underline;
    font-family:inherit; display:inline-block;
}
.installed-badge { color:var(--green); font-weight:700; font-size:0.9rem;
    padding:10px 0; display:flex; align-items:center; gap:6px; }
.hint-text { color:var(--muted); font-size:0.82rem; line-height:1.5; margin-bottom:6px; }

.live-banner {
    border-radius:20px; padding:16px 18px; margin-bottom:14px;
    display:flex; align-items:center; gap:14px; box-shadow:var(--shadow);
    border:1px solid var(--border);
}
.live-banner.now { background:linear-gradient(135deg,var(--green-soft),var(--accent-soft)); }
.live-banner.before { background:linear-gradient(135deg,var(--orange-soft),var(--accent-soft)); }
.live-dot { width:10px; height:10px; border-radius:50%; background:var(--green); flex-shrink:0; }
.live-banner.before .live-dot { background:var(--orange); }
.live-info { flex:1; min-width:0; }
.live-label { font-size:0.72rem; font-weight:800; text-transform:uppercase;
    letter-spacing:0.08em; color:var(--green); margin-bottom:3px; }
.live-banner.before .live-label { color:var(--orange); }
.live-lesson { font-size:1.05rem; font-weight:800;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.live-time { font-size:0.78rem; color:var(--muted); font-weight:700; margin-top:2px; }
.progress-bar { height:5px; border-radius:3px; background:var(--border); overflow:hidden; margin-top:8px; }
.progress-fill { height:100%; background:linear-gradient(90deg,var(--green),var(--accent2)); border-radius:3px; }

.tabs {
    display:flex; gap:6px; margin-bottom:16px; overflow-x:auto;
    padding:4px; scrollbar-width:none; -ms-overflow-style:none;
    background:var(--card); border-radius:18px; border:1px solid var(--border);
    box-shadow:var(--shadow);
}
.tabs::-webkit-scrollbar { display:none; }
.tab {
    flex:1; min-width:52px; padding:11px 8px; border-radius:13px; border:none;
    background:transparent; color:var(--muted); font-weight:800; font-size:0.88rem;
    cursor:pointer; font-family:inherit; transition:background 0.15s, color 0.15s;
    display:flex; flex-direction:column; align-items:center; gap:3px; position:relative;
}
.tab .tab-day { font-size:0.68rem; font-weight:700; opacity:0.7; }
.tab.active { background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white; }
.tab.active .tab-day { opacity:0.9; }
.tab.today:not(.active)::after {
    content:""; position:absolute; bottom:4px; left:50%; transform:translateX(-50%);
    width:5px; height:5px; border-radius:50%; background:var(--accent);
}
.day-block { display:none; }
.day-block.active { display:block; }
.day-title {
    font-size:1.15rem; font-weight:800; color:var(--text);
    margin:4px 4px 12px; display:flex; justify-content:space-between; align-items:center;
}
.today-pill {
    font-size:0.68rem; background:linear-gradient(135deg,var(--accent-soft),var(--accent-soft2));
    color:var(--accent); padding:5px 11px; border-radius:20px;
    font-weight:800; text-transform:uppercase; letter-spacing:0.06em;
    border:1px solid var(--border);
}
.card {
    background:var(--card); padding:14px 16px; margin-bottom:9px; border-radius:18px;
    box-shadow:var(--shadow); display:flex; align-items:center; gap:14px;
    border:1px solid var(--border); position:relative; overflow:hidden;
}
.card.now { box-shadow:0 8px 28px var(--green-soft),0 0 0 1px var(--green);
    background:linear-gradient(135deg,var(--green-soft),var(--card)); }
.card.now::before {
    content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
    background:linear-gradient(180deg,var(--green),var(--accent2));
}
.card.next-up { box-shadow:0 6px 22px var(--orange-soft),0 0 0 1px var(--orange); }
.num {
    min-width:40px; height:40px; border-radius:12px;
    background:linear-gradient(135deg,var(--accent-soft),var(--accent-soft2));
    color:var(--accent); display:flex; align-items:center; justify-content:center;
    font-weight:800; font-size:1rem; flex-shrink:0; border:1px solid var(--border);
}
.card.now .num { background:linear-gradient(135deg,var(--green),var(--accent2)); color:white; border-color:transparent; }
.left-side { display:flex; flex-direction:column; gap:2px; flex-grow:1; min-width:0; }
.time { font-size:0.78rem; color:var(--muted); font-weight:700; }
.lesson { font-size:1rem; font-weight:800; color:var(--text); word-wrap:break-word; }
.now-pill {
    font-size:0.62rem; background:var(--green); color:white; padding:3px 8px;
    border-radius:20px; font-weight:800; text-transform:uppercase; letter-spacing:0.08em;
    margin-left:auto; flex-shrink:0;
}
html.compact .card { padding:10px 14px; margin-bottom:6px; }
html.compact .num { min-width:34px; height:34px; font-size:0.9rem; border-radius:10px; }
html.hide-time .time { display:none; }
html.font-small .lesson { font-size:0.9rem; }
html.font-small .live-lesson { font-size:0.95rem; }
html.font-large .lesson { font-size:1.15rem; }
html.font-large .live-lesson { font-size:1.2rem; }
html.font-large .day-title { font-size:1.3rem; }

.info-box {
    background:var(--card); padding:32px 20px; border-radius:20px;
    box-shadow:var(--shadow); text-align:center; font-size:1rem; font-weight:700;
    color:var(--muted); border:1px solid var(--border); line-height:1.5;
}
.info-box .big { font-size:2.2rem; display:block; margin-bottom:8px; }
.error { background:linear-gradient(135deg,rgba(239,68,68,0.1),var(--card));
    color:var(--danger); padding:20px; border-radius:18px; font-weight:700;
    text-align:center; border:1px solid var(--border); }

.sheet-link {
    display:flex; align-items:center; justify-content:center; gap:6px;
    margin-top:20px; padding:13px; color:var(--muted); text-decoration:none;
    font-size:0.82rem; font-weight:700; border-radius:14px;
    border:1px dashed var(--border); background:var(--card);
}
</style>
</head>
<body>
<div id="particles"></div>
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
        <div class="settings-title">⚡ Графика</div>
        <div class="graphics-grid">
            <button class="graphics-btn" data-graphics-btn="potato" onclick="setGraphics('potato')"><span class="emoji">🥔</span>Картошка</button>
            <button class="graphics-btn" data-graphics-btn="medium" onclick="setGraphics('medium')"><span class="emoji">⚖️</span>Средняя</button>
            <button class="graphics-btn" data-graphics-btn="high" onclick="setGraphics('high')"><span class="emoji">✨</span>Красивая</button>
        </div>

        <div class="settings-title">🎨 Тема</div>
        <div class="theme-grid">
            <button class="theme-btn" data-theme-btn="light" onclick="setTheme('light')"><span class="emoji">☀️</span>Светлая</button>
            <button class="theme-btn" data-theme-btn="dark" onclick="setTheme('dark')"><span class="emoji">🌙</span>Тёмная</button>
            <button class="theme-btn" data-theme-btn="cosmic" onclick="setTheme('cosmic')"><span class="emoji">🌌</span>Космос</button>
            <button class="theme-btn" data-theme-btn="ocean" onclick="setTheme('ocean')"><span class="emoji">🌊</span>Океан</button>
            <button class="theme-btn" data-theme-btn="sunset" onclick="setTheme('sunset')"><span class="emoji">🌅</span>Закат</button>
            <button class="theme-btn" data-theme-btn="forest" onclick="setTheme('forest')"><span class="emoji">🌿</span>Лес</button>
            <button class="theme-btn" data-theme-btn="sakura" onclick="setTheme('sakura')"><span class="emoji">🌸</span>Сакура</button>
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
            <div class="toggle" id="toggleCompact" onclick="toggleCompact()"></div>
        </div>
        <div class="toggle-row">
            <div class="toggle-label">Скрыть время уроков</div>
            <div class="toggle" id="toggleHideTime" onclick="toggleHideTime()"></div>
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
var THEME_COLORS = {light:'#eef2f7',dark:'#0b0d12',cosmic:'#05021a',ocean:'#e6f4fb',sunset:'#fff1e6',forest:'#eef7ee',sakura:'#fff5f8'};
var ALLOWED_POTATO = ['light','dark','cosmic'];

(function init() {
    var savedTheme = localStorage.getItem('rs_theme') || 'light';
    var savedGraphics = localStorage.getItem('rs_graphics') || 'high';

    document.documentElement.setAttribute('data-theme', savedTheme);
    document.documentElement.setAttribute('data-graphics', savedGraphics);

    // Если картошка и тема недоступна — переключаем на светлую
    if (savedGraphics === 'potato' && ALLOWED_POTATO.indexOf(savedTheme) === -1) {
        savedTheme = 'light';
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('rs_theme', 'light');
    }

    var meta = document.getElementById('themeColorMeta');
    if (meta) meta.setAttribute('content', THEME_COLORS[savedTheme] || '#eef2f7');

    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-theme-btn') === savedTheme);
    });
    document.querySelectorAll('[data-graphics-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-graphics-btn') === savedGraphics);
    });

    if (localStorage.getItem('rs_compact') === '1') document.documentElement.classList.add('compact');
    if (localStorage.getItem('rs_hide_time') === '1') document.documentElement.classList.add('hide-time');

    var size = localStorage.getItem('rs_size') || 'normal';
    if (size === 'small') document.documentElement.classList.add('font-small');
    if (size === 'large') document.documentElement.classList.add('font-large');
    document.querySelectorAll('[data-size-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-size-btn') === size);
    });

    document.getElementById('toggleCompact').classList.toggle('on', localStorage.getItem('rs_compact') === '1');
    document.getElementById('toggleHideTime').classList.toggle('on', localStorage.getItem('rs_hide_time') === '1');

    if (savedGraphics === 'high') spawnParticles(savedTheme);
})();

function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('rs_theme', t);
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-theme-btn') === t);
    });
    var meta = document.getElementById('themeColorMeta');
    if (meta) meta.setAttribute('content', THEME_COLORS[t] || '#eef2f7');
    var g = document.documentElement.getAttribute('data-graphics');
    if (g === 'high') spawnParticles(t);
    else document.getElementById('particles').innerHTML = '';
}

function setGraphics(g) {
    document.documentElement.setAttribute('data-graphics', g);
    localStorage.setItem('rs_graphics', g);
    document.querySelectorAll('[data-graphics-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-graphics-btn') === g);
    });
    // Проверка темы
    var cur = document.documentElement.getAttribute('data-theme');
    if (g === 'potato' && ALLOWED_POTATO.indexOf(cur) === -1) {
        setTheme('light');
    }
    // Частицы
    if (g === 'high') spawnParticles(cur);
    else document.getElementById('particles').innerHTML = '';
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
    document.getElementById('toggleCompact').classList.toggle('on', on);
}
function toggleHideTime() {
    var on = document.documentElement.classList.toggle('hide-time');
    localStorage.setItem('rs_hide_time', on ? '1' : '0');
    document.getElementById('toggleHideTime').classList.toggle('on', on);
}
function spawnParticles(theme) {
    var container = document.getElementById('particles');
    if (!container) return;
    container.innerHTML = '';
    if (document.documentElement.getAttribute('data-graphics') !== 'high') return;
    if (window.innerWidth < 300) return;
    var configs = {
        cosmic: { chars: ['✦','✧','·','+'], colors: ['#ffffff','#b794f6','#7cf5c0','#e0d4ff'], count: 20, sizes: [10,18], dur: [15,28] },
        sakura: { chars: ['🌸','🌸','🌸','❀'], colors: ['#ec4899','#f9a8d4','#fbcfe8'], count: 16, sizes: [14,22], dur: [11,20] },
        forest: { chars: ['🍃','🌿','🍃'], colors: ['#059669','#16a34a','#84cc16'], count: 14, sizes: [14,22], dur: [13,24] },
        ocean:  { chars: ['●','○','·'], colors: ['rgba(34,211,238,0.75)','rgba(8,145,178,0.65)','rgba(255,255,255,0.55)'], count: 14, sizes: [8,16], dur: [11,20] },
        sunset: { chars: ['✨','·','✦'], colors: ['#f97316','#ec4899','#fbbf24'], count: 12, sizes: [10,18], dur: [13,22] }
    };
    var cfg = configs[theme];
    if (!cfg) return;
    var isMobile = window.innerWidth < 820;
    var n = isMobile ? Math.max(8, Math.round(cfg.count * 0.6)) : cfg.count;
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
function toggleSettings() {
    document.getElementById('settingsPanel').classList.toggle('open');
}
function showDay(day) {
    document.querySelectorAll('.day-block').forEach(function(el) { el.classList.remove('active'); });
    var target = document.getElementById('day-' + day);
    if (target) target.classList.add('active');
    document.querySelectorAll('.tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-day') === day);
    });
}
document.addEventListener('visibilitychange', function() {
    var ps = document.hidden ? 'paused' : 'running';
    document.querySelectorAll('.particle').forEach(function(p) { p.style.animationPlayState = ps; });
});

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
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>';
        return;
    }
    if (deferredPrompt) {
        el.innerHTML = '<button class="install-btn" onclick="doInstall()">📲 Установить приложение</button>';
        return;
    }
    var plat = detectPlatform();
    var hint = '';
    if (plat === 'ios') hint = '📱 <b>iPhone:</b> открой в <b>Safari</b> → «Поделиться» → «На экран Домой».';
    else if (plat === 'android') hint = '📱 <b>Android:</b> открой в <b>Chrome</b> → меню <b>⋮</b> → «Установить приложение».';
    else hint = '💻 <b>ПК:</b> открой в Chrome — иконка установки появится в адресной строке.';
    el.innerHTML = '<div class="hint-text">' + hint + '</div>';
}
function doInstall() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(function(choice) {
        if (choice.outcome === 'accepted') localStorage.setItem('rs_installed', '1');
        deferredPrompt = null; renderInstallSection();
    });
}
renderInstallSection();
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js').catch(function() {});
    });
}
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


def build_content(days_schedule, active_day, error_msg, live_status):
    if error_msg and not days_schedule:
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
            for time_str, num, lesson in lessons:
                card_cls = "card"
                now_pill = ""
                if full == today_full and live_status and live_status["type"] == "now" and num == live_status["num"]:
                    card_cls += " now"; now_pill = '<span class="now-pill">сейчас</span>'
                elif full == today_full and live_status and live_status["type"] == "before" and num == live_status["num"]:
                    card_cls += " next-up"
                html += f'<div class="{card_cls}"><div class="num">{num}</div>'
                html += f'<div class="left-side"><div class="time">{time_str}</div>'
                html += f'<div class="lesson">{lesson}</div></div>'
                html += now_pill + '</div>'
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
            hour, minute = now_perm.hour, now_perm.minute
            weekday_idx = now_perm.weekday()
            current_day_name = DAY_FULL[weekday_idx] if weekday_idx < 6 else "Суббота"
            is_weekend = (weekday_idx >= 5)
            refresh_tag = "<meta http-equiv='refresh' content='900'>" if not (1 <= hour < 5) else ""

            days_schedule, error_msg = get_schedule()
            months = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"]
            header_date = f"{current_day_name}, {now_perm.day} {months[now_perm.month-1]}"

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
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()
