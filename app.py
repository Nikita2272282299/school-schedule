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

MANIFEST = '{"name":"Расписание 8Г","short_name":"8Г","start_url":"/","display":"standalone","background_color":"#0a0620","theme_color":"#6366f1","icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'
ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6366f1"/><stop offset="1" stop-color="#7950f2"/></linearGradient></defs><rect width="512" height="512" rx="110" fill="url(#g)"/><rect x="130" y="110" width="252" height="46" rx="23" fill="#fff" opacity="0.25"/><text x="256" y="360" font-family="Arial,sans-serif" font-size="230" font-weight="900" fill="#fff" text-anchor="middle">8Г</text></svg>'''
SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>self.clients.claim());self.addEventListener('fetch',e=>{e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});"


def get_schedule():
    now = time.time()
    if cache["days_schedule"] and (now - cache["last_update"] < CACHE_TTL):
        return cache["days_schedule"], cache["error_msg"]
    days = {}; err = ""
    try:
        req = urllib.request.urlopen(CSV_URL, timeout=6)
        data = req.read().decode('utf-8')
        reader = list(csv.reader(io.StringIO(data)))
        col = -1
        for row in reader:
            for i, c in enumerate(row):
                if c.replace(" ", "").lower() == "8г":
                    col = i; break
            if col != -1: break
        if col != -1:
            cur_day = ""
            days_list = ["понедельник","вторник","среда","четверг","пятница","суббота"]
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
                    if lv.lower() in ["урок","-","—",""]: continue
                    n = TIME_TO_NUM[tv]
                    if n not in [x[1] for x in days[cur_day]]:
                        days[cur_day].append((tv, n, lv))
            for d in days: days[d].sort(key=lambda x: x[1])
            cache["days_schedule"] = days; cache["error_msg"] = ""; cache["last_update"] = now
        else:
            err = "Класс 8Г не найден."; cache["error_msg"] = err
    except Exception:
        if cache["days_schedule"]: return cache["days_schedule"], ""
        cache["error_msg"] = "Офлайн-режим"
    return cache["days_schedule"], cache["error_msg"]


def get_live_status(today_lessons):
    if not today_lessons: return None
    now = datetime.now(PERM_TZ)
    cur = now.hour * 60 + now.minute
    for tv, num, lesson in today_lessons:
        try:
            start, end = tv.split("-")
            sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":"))
        except Exception: continue
        s = sh*60+sm; e = eh*60+em
        if s <= cur < e:
            prog = int((cur - s) / max(e - s, 1) * 100)
            return {"type":"now","num":num,"lesson":lesson,"progress":prog,
                    "left":e-cur,"until":end,
                    "end_unix": int(now.replace(hour=eh,minute=em,second=0,microsecond=0).timestamp())}
        if cur < s:
            return {"type":"before","num":num,"lesson":lesson,"wait":s-cur,"start":start,
                    "start_unix": int(now.replace(hour=sh,minute=sm,second=0,microsecond=0).timestamp())}
    return None


PAGE = """<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f0f4f8" id="tcMeta">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="8Г">
{refresh_tag}
<title>Расписание 8Г</title>
<style>
:root, [data-theme="light"] {
    --bg:#f0f4f8; --card:#ffffff; --text:#1a202c; --muted:#4a5568;
    --accent:#4c6ef5; --accent2:#7950f2; --accent-light:#edf2ff;
    --border:rgba(15,23,42,0.06); --shadow:0 4px 16px rgba(15,23,42,0.06);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
}
[data-theme="dark"] {
    --bg:#0f1115; --card:#1a1d24; --text:#e6e8ec; --muted:#9aa3b2;
    --accent:#7c93ff; --accent2:#c084fc; --accent-light:#232741;
    --border:rgba(255,255,255,0.07); --shadow:0 4px 16px rgba(0,0,0,0.4);
    --green:#34d399; --green-soft:rgba(52,211,153,0.14);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.14);
    color-scheme:dark;
}
[data-theme="cosmic"] {
    --bg:#05021a; --card:rgba(30,20,60,0.72); --text:#eae4ff; --muted:#b3a8d9;
    --accent:#b794f6; --accent2:#7cf5c0; --accent-light:rgba(183,148,246,0.15);
    --border:rgba(183,148,246,0.2); --shadow:0 8px 30px rgba(140,80,255,0.25);
    --green:#7cf5c0; --green-soft:rgba(124,245,192,0.15);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.15);
    color-scheme:dark;
}
[data-theme="ocean"] {
    --bg:#e6f4fb; --card:#ffffff; --text:#062b3d; --muted:#5a7d92;
    --accent:#0891b2; --accent2:#22d3ee; --accent-light:rgba(8,145,178,0.1);
    --border:rgba(6,43,61,0.06); --shadow:0 4px 16px rgba(8,145,178,0.1);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
}
[data-theme="sunset"] {
    --bg:#fff1e6; --card:#ffffff; --text:#3d1a0a; --muted:#8a6550;
    --accent:#f97316; --accent2:#ec4899; --accent-light:rgba(249,115,22,0.1);
    --border:rgba(61,26,10,0.06); --shadow:0 4px 16px rgba(249,115,22,0.12);
    --green:#059669; --green-soft:rgba(5,150,105,0.12);
    --orange:#d97706; --orange-soft:rgba(217,119,6,0.12);
}
[data-theme="forest"] {
    --bg:#eef7ee; --card:#ffffff; --text:#0f2e1b; --muted:#5f7c68;
    --accent:#059669; --accent2:#84cc16; --accent-light:rgba(5,150,105,0.1);
    --border:rgba(15,46,27,0.06); --shadow:0 4px 16px rgba(5,150,105,0.1);
    --green:#16a34a; --green-soft:rgba(22,163,74,0.12);
    --orange:#ca8a04; --orange-soft:rgba(202,138,4,0.12);
}
[data-theme="sakura"] {
    --bg:#fff5f8; --card:#ffffff; --text:#3d1029; --muted:#9a6782;
    --accent:#ec4899; --accent2:#a855f7; --accent-light:rgba(236,72,153,0.1);
    --border:rgba(61,16,41,0.06); --shadow:0 4px 16px rgba(236,72,153,0.1);
    --green:#059669; --green-soft:rgba(5,150,105,0.12);
    --orange:#ea580c; --orange-soft:rgba(234,88,12,0.12);
}
html { min-height:100%; }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body {
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:var(--bg); color:var(--text); margin:0;
    padding:20px 14px 30px; display:flex; justify-content:center;
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
        linear-gradient(180deg,#0a0424 0%,#05021a 55%,#01000a 100%);
}
[data-theme="cosmic"] [data-theme="ocean"] body { background-image:linear-gradient(180deg,#c7e8f5 0%,#94d0e6 45%,#5aafd0 100%); }
[data-theme="sunset"] body { background-image:linear-gradient(180deg,#ffe0a8 0%,#ffb572 40%,#e88898 100%); }
[data-theme="forest"] body { background-image:linear-gradient(180deg,#dff0d0 0%,#b8dfa8 40%,#7abb6c 100%); }
[data-theme="sakura"] body { background-image:linear-gradient(180deg,#ffeaf0 0%,#ffd0dd 50%,#ffb0c8 100%); }

#particles { position:fixed; inset:0; pointer-events:none; z-index:0; overflow:hidden; }
.particle { position:absolute; top:-40px; user-select:none;
    animation-name:fall; animation-timing-function:linear; animation-iteration-count:infinite; }
@keyframes fall {
    0% { transform:translateY(0) rotate(0deg); opacity:0; }
    10% { opacity:0.85; }
    90% { opacity:0.85; }
    100% { transform:translateY(110vh) rotate(360deg); opacity:0; }
}
.container { width:100%; max-width:500px; position:relative; z-index:1; }

.header-card {
    background:var(--card); border:1px solid var(--border); border-radius:22px;
    padding:16px 20px; box-shadow:var(--shadow); margin-bottom:14px;
    display:flex; align-items:center; justify-content:space-between; gap:10px;
}
h2 { margin:0; font-size:1.4rem; font-weight:800; display:flex; align-items:center; gap:10px; }
h2 span { background:linear-gradient(135deg,var(--accent),var(--accent2));
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.header-right { display:flex; align-items:center; gap:8px; }
.badge-class { background:var(--accent-light); color:var(--accent);
    padding:7px 14px; border-radius:12px; font-weight:800; font-size:1rem; }
.icon-btn { background:var(--accent-light); color:var(--accent); border:none;
    width:40px; height:40px; border-radius:12px; font-size:1.15rem;
    cursor:pointer; display:flex; align-items:center; justify-content:center; }
.icon-btn:active { transform:scale(0.92); }

.header-card { position:relative; }
.settings-panel {
    position:absolute;
    top:100%;
    right:0;
    margin-top:8px;
    width:320px;
    max-width:calc(100vw - 44px);
    background:var(--card);
    border:1px solid var(--border);
    border-radius:16px;
    box-shadow:0 14px 44px rgba(0,0,0,0.16), 0 4px 12px rgba(0,0,0,0.08);
    padding:16px 18px;
    z-index:50;
    transform-origin:top right;
    transform:scale(0.94) translateY(-6px);
    opacity:0;
    pointer-events:none;
    transition:transform 0.11s cubic-bezier(0.4,0,0.2,1), opacity 0.09s ease;
    will-change:transform, opacity;
}
.settings-panel.open {
    transform:scale(1) translateY(0);
    opacity:1;
    pointer-events:auto;
}
[data-theme="cosmic"] .settings-panel {
    box-shadow:0 14px 44px rgba(120,60,220,0.35), inset 0 1px 0 rgba(255,255,255,0.06);
}
.settings-title { font-weight:800; font-size:0.9rem; margin-bottom:10px; }
.settings-title:not(:first-child) { margin-top:16px; }
.theme-options { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-bottom:6px; }
.theme-btn {
    padding:10px 2px; border-radius:12px; border:2px solid transparent;
    background:var(--accent-light); color:var(--text); font-weight:700; font-size:0.62rem;
    cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:4px;
    font-family:inherit;
}
.theme-btn.active { border-color:var(--accent); background:var(--accent-light); }
.theme-btn .emoji { font-size:1.25rem; line-height:1; }
.size-options { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:6px; }
.size-btn {
    padding:11px; border-radius:12px; border:2px solid var(--border);
    background:var(--accent-light); color:var(--text); font-weight:800;
    cursor:pointer; font-family:inherit;
}
.size-btn[data-size="small"] { font-size:0.85rem; }
.size-btn[data-size="normal"] { font-size:1.05rem; }
.size-btn[data-size="large"] { font-size:1.25rem; }
.size-btn.active { border-color:var(--accent); }
.toggle-row { display:flex; justify-content:space-between; align-items:center;
    padding:10px 0; border-bottom:1px solid var(--border); }
.toggle-row:last-child { border-bottom:none; }
.toggle-label { font-weight:700; font-size:0.9rem; }
.toggle { position:relative; width:48px; height:28px; background:var(--border);
    border-radius:14px; cursor:pointer; transition:background 0.2s; flex-shrink:0; }
.toggle::after { content:""; position:absolute; top:2px; left:2px; width:22px; height:22px;
    background:#fff; border-radius:50%; transition:transform 0.22s;
    box-shadow:0 1px 3px rgba(0,0,0,0.15); }
.toggle.on { background:linear-gradient(135deg,var(--accent),var(--accent2)); }
.toggle.on::after { transform:translateX(20px); }
.install-btn { width:100%; padding:13px; border-radius:12px; border:none;
    background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white;
    font-weight:800; font-size:0.9rem; cursor:pointer; font-family:inherit; }
.installed-badge { color:var(--green); font-weight:700; font-size:0.9rem; padding:8px 0; }
.hint-text { color:var(--muted); font-size:0.82rem; line-height:1.4; }

.live-banner { border-radius:18px; padding:14px 16px; margin-bottom:14px;
    display:flex; align-items:center; gap:12px; box-shadow:var(--shadow);
    border:1px solid var(--border);
    background:linear-gradient(135deg,var(--green-soft),var(--accent-light)); }
.live-banner.before { background:linear-gradient(135deg,var(--orange-soft),var(--accent-light)); }
.live-dot { width:10px; height:10px; border-radius:50%; background:var(--green); flex-shrink:0; }
.live-banner.before .live-dot { background:var(--orange); }
.live-info { flex:1; min-width:0; }
.live-label { font-size:0.7rem; font-weight:800; text-transform:uppercase;
    letter-spacing:0.08em; color:var(--green); margin-bottom:3px; }
.live-banner.before .live-label { color:var(--orange); }
.live-lesson { font-size:1.05rem; font-weight:800;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.live-time { font-size:0.78rem; color:var(--muted); font-weight:700; margin-top:2px; }
.progress-bar { height:4px; border-radius:2px; background:var(--border); overflow:hidden; margin-top:8px; }
.progress-fill { height:100%; background:linear-gradient(90deg,var(--green),var(--accent2)); border-radius:2px; }

.tabs { display:flex; gap:6px; margin-bottom:16px; overflow-x:auto;
    padding:4px; scrollbar-width:none;
    background:var(--card); border-radius:18px; border:1px solid var(--border);
    box-shadow:var(--shadow); }
.tabs::-webkit-scrollbar { display:none; }
.tab { flex:1; min-width:52px; padding:11px 8px; border-radius:13px; border:none;
    background:transparent; color:var(--muted); font-weight:800; font-size:0.88rem;
    cursor:pointer; font-family:inherit;
    display:flex; flex-direction:column; align-items:center; gap:3px; position:relative; }
.tab .tab-day { font-size:0.68rem; font-weight:700; opacity:0.7; }
.tab.active { background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white; }
.tab.today:not(.active)::after { content:""; position:absolute; bottom:4px; left:50%;
    transform:translateX(-50%); width:5px; height:5px; border-radius:50%; background:var(--accent); }

.day-block { display:none; }
.day-block.active { display:block; }
.day-title { font-size:1.15rem; font-weight:800; color:var(--muted); margin-bottom:12px;
    padding-left:6px; display:flex; justify-content:space-between; align-items:center; }
.day-title.today { color:var(--text); }
.today-pill { font-size:0.7rem; background:var(--accent-light); color:var(--green);
    padding:5px 12px; border-radius:20px; font-weight:800; text-transform:uppercase; }
.card { background:var(--card); padding:16px 18px; margin-bottom:10px; border-radius:16px;
    box-shadow:var(--shadow); display:flex; align-items:center; gap:14px;
    border:1px solid var(--border); }
.card.now { box-shadow:0 8px 28px var(--green-soft),0 0 0 1px var(--green);
    background:linear-gradient(135deg,var(--green-soft),var(--card)); }
.card.next-up { box-shadow:0 6px 22px var(--orange-soft),0 0 0 1px var(--orange); }
.num { background:var(--accent-light); color:var(--accent); min-width:38px; height:38px;
    border-radius:11px; display:flex; align-items:center; justify-content:center;
    font-weight:800; font-size:1.05rem; flex-shrink:0; }
.card.now .num { background:linear-gradient(135deg,var(--green),var(--accent2)); color:white; }
.left-side { display:flex; flex-direction:column; gap:3px; flex-grow:1; min-width:0; }
.time { font-size:0.8rem; color:var(--muted); font-weight:700; }
.lesson { font-size:1.05rem; font-weight:800; color:var(--text); word-wrap:break-word; }
.now-pill { font-size:0.6rem; background:var(--green); color:white; padding:3px 8px;
    border-radius:20px; font-weight:800; text-transform:uppercase; letter-spacing:0.06em;
    margin-left:auto; flex-shrink:0; }
.error { background:rgba(224,49,49,0.1); color:#e03131; padding:16px;
    border-radius:16px; font-weight:700; text-align:center; }
.info-box { background:var(--card); padding:28px 20px; border-radius:18px;
    box-shadow:var(--shadow); text-align:center; font-size:1.05rem; font-weight:700;
    color:var(--muted); border:1px solid var(--border); }
.sheet-link { display:flex; align-items:center; justify-content:center; gap:6px;
    margin-top:22px; padding:13px; color:var(--accent); text-decoration:none;
    font-size:0.85rem; font-weight:800; border-radius:14px;
    border:1.5px solid var(--accent); background:var(--accent-light); }
html.font-small .lesson { font-size:0.9rem; }
html.font-small .live-lesson { font-size:0.95rem; }
html.font-large .lesson { font-size:1.15rem; }
html.font-large .live-lesson { font-size:1.2rem; }
html.font-large .day-title { font-size:1.3rem; }
html.compact .card { padding:11px 14px; margin-bottom:7px; }
html.compact .num { min-width:34px; height:34px; font-size:0.9rem; }
html.hide-time .time { display:none; }

/* ===== КРАСИВЫЕ КАРТОЧКИ ===== */
[data-theme="light"] .card {
    background:
        radial-gradient(circle, rgba(99,102,241,0.08) 1px, transparent 1.5px),
        linear-gradient(180deg, #ffffff 0%, #f7fafd 100%);
    background-size: 16px 16px, 100% 100%;
    border:1px solid rgba(99,102,241,0.12);
    box-shadow:0 2px 6px rgba(99,102,241,0.06), 0 6px 18px rgba(99,102,241,0.06), inset 0 1px 0 #fff;
}
[data-theme="light"] .num { background:linear-gradient(135deg,#e0e7ff,#c7d2fe); color:#4338ca;
    box-shadow:0 2px 6px rgba(99,102,241,0.15), inset 0 1px 0 rgba(255,255,255,0.9); }

[data-theme="dark"] .card {
    background:
        radial-gradient(1px 1px at 15% 25%, rgba(255,255,255,0.5), transparent 70%),
        radial-gradient(1px 1px at 55% 65%, rgba(199,210,254,0.6), transparent 70%),
        radial-gradient(1px 1px at 85% 35%, rgba(255,255,255,0.4), transparent 70%),
        linear-gradient(135deg,#232733 0%,#1a1d24 55%,#12141b 100%);
    border:1px solid rgba(255,255,255,0.1);
    box-shadow:0 2px 6px rgba(0,0,0,0.5), 0 8px 22px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06);
}
[data-theme="dark"] .num { background:linear-gradient(135deg,#2d3142,#232741); color:#c7d2fe;
    box-shadow:inset 0 1px 0 rgba(255,255,255,0.08), 0 1px 4px rgba(0,0,0,0.4); }

[data-theme="cosmic"] .card {
    background:
        radial-gradient(1px 1px at 12% 20%, rgba(255,255,255,0.95), transparent 65%),
        radial-gradient(1.5px 1.5px at 78% 25%, rgba(124,245,192,0.9), transparent 65%),
        radial-gradient(1px 1px at 35% 75%, rgba(183,148,246,0.9), transparent 65%),
        radial-gradient(1.5px 1.5px at 88% 80%, rgba(255,255,255,0.9), transparent 65%),
        linear-gradient(135deg,rgba(50,30,100,0.92) 0%,rgba(25,15,60,0.96) 100%);
    border:1px solid rgba(183,148,246,0.32);
    box-shadow:0 3px 10px rgba(120,60,220,0.3), 0 10px 28px rgba(120,60,220,0.2), inset 0 1px 0 rgba(255,255,255,0.08);
}

[data-theme="ocean"] .card {
    background:
        radial-gradient(ellipse at 15% 20%, rgba(255,255,255,0.75), transparent 45%),
        radial-gradient(ellipse at 90% 85%, rgba(34,211,238,0.2), transparent 40%),
        linear-gradient(180deg,rgba(255,255,255,0.96) 0%,rgba(220,245,252,0.92) 50%,rgba(180,230,245,0.88) 100%);
    border:1px solid rgba(34,211,238,0.4);
    box-shadow:0 3px 10px rgba(8,145,178,0.15), 0 6px 22px rgba(8,145,178,0.22),
        inset 0 2px 8px rgba(255,255,255,0.9), inset 0 -4px 8px rgba(8,145,178,0.12);
}
[data-theme="ocean"] .num { background:radial-gradient(circle at 30% 25%,#fff,#22d3ee 55%,#0891b2);
    color:#fff; border-radius:50%; border:2px solid rgba(255,255,255,0.9);
    box-shadow:0 3px 10px rgba(8,145,178,0.4), inset -3px -4px 8px rgba(8,145,178,0.3), inset 3px 3px 10px rgba(255,255,255,0.7); }

[data-theme="sunset"] .card {
    background:
        radial-gradient(ellipse at 90% 15%, rgba(255,220,150,0.5), transparent 40%),
        linear-gradient(180deg,#fff8ec 0%,#ffe9cc 60%,#ffd9b0 100%);
    border:1px solid rgba(249,115,22,0.3);
    box-shadow:0 3px 10px rgba(249,115,22,0.15), 0 6px 22px rgba(249,115,22,0.22), inset 0 1px 0 rgba(255,255,255,0.9);
}
[data-theme="sunset"] .num { background:linear-gradient(135deg,#f97316,#ec4899); color:#fff;
    border-radius:14px 4px 14px 4px; box-shadow:0 3px 10px rgba(249,115,22,0.4), inset 0 1px 0 rgba(255,255,255,0.4); }

[data-theme="forest"] .card {
    background:
        linear-gradient(180deg,rgba(140,100,60,0.15) 0%,rgba(90,60,30,0.05) 100%),
        linear-gradient(90deg, rgba(180,140,90,0.12) 0%,transparent 3%,transparent 10%,rgba(140,100,60,0.08) 12%,transparent 15%,transparent 45%,rgba(140,100,60,0.06) 47%,transparent 50%,transparent 82%,rgba(140,100,60,0.08) 84%,transparent 88%,rgba(180,140,90,0.1) 100%),
        linear-gradient(180deg,#f5ecd8 0%,#e8d9b8 40%,#d8c498 100%);
    border:1px solid rgba(90,60,30,0.3);
    border-radius:10px 6px 10px 6px;
    box-shadow:0 3px 10px rgba(60,40,20,0.2), inset 0 1px 0 rgba(255,240,210,0.6), inset 0 -2px 4px rgba(90,60,30,0.12);
    position:relative; overflow:hidden;
}
[data-theme="forest"] .card::before {
    content:""; position:absolute; inset:0; pointer-events:none;
    background:repeating-linear-gradient(90deg,transparent 0,transparent 28px,rgba(90,60,30,0.06) 28px,rgba(90,60,30,0.06) 29px);
    opacity:0.7;
}
[data-theme="forest"] .num { background:linear-gradient(180deg,#c9a86a,#a8874a 50%,#8a6a2f);
    color:#fffbf0; border-radius:8px 4px 8px 4px; border:1px solid rgba(90,60,20,0.4);
    box-shadow:0 2px 6px rgba(60,40,10,0.3), inset 0 1px 0 rgba(255,240,200,0.5); font-family:Georgia,serif; }

[data-theme="sakura"] .card {
    background:
        radial-gradient(ellipse at 80% 15%, rgba(255,220,235,0.7), transparent 45%),
        radial-gradient(ellipse at 15% 85%, rgba(255,200,225,0.6), transparent 40%),
        linear-gradient(180deg,#fffafc 0%,#ffe8f0 50%,#ffd0dd 100%);
    border:1px solid rgba(236,72,153,0.22);
    border-radius:20px 20px 20px 8px;
    box-shadow:0 3px 10px rgba(236,72,153,0.15), 0 5px 18px rgba(236,72,153,0.2), inset 0 1px 0 rgba(255,255,255,0.9);
}
[data-theme="sakura"] .num { background:radial-gradient(circle at 30% 25%,#fff 0%,#f9a8d4 50%,#ec4899 100%);
    color:#fff; border-radius:50% 50% 50% 14px;
    box-shadow:0 3px 10px rgba(236,72,153,0.35), inset 0 1px 0 rgba(255,255,255,0.6); }

/* ===== КРАСИВЫЕ КНОПКИ ===== */
.theme-btn {
    padding:16px 6px 14px !important;
    border-radius:14px !important;
    position:relative; overflow:hidden;
    box-shadow:0 3px 8px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06),
        inset 0 1px 0 rgba(255,255,255,0.85), inset 0 -2px 4px rgba(0,0,0,0.06);
    transition:transform 0.1s, box-shadow 0.12s;
}
.theme-btn::before {
    content:""; position:absolute; top:0; left:10%; right:10%; height:40%;
    border-radius:14px 14px 50% 50%;
    background:linear-gradient(180deg, rgba(255,255,255,0.5), transparent);
    pointer-events:none;
}
.theme-btn:active { transform:scale(0.94); }
.theme-btn .emoji { font-size:1.5rem; filter:drop-shadow(0 2px 3px rgba(0,0,0,0.15)); position:relative; z-index:1; }
.theme-btn.active {
    box-shadow:0 0 0 3px var(--accent), 0 6px 18px var(--accent-light),
        inset 0 1px 0 rgba(255,255,255,0.4), inset 0 -2px 6px rgba(0,0,0,0.12) !important;
    transform:translateY(-2px);
}
.size-btn {
    padding:13px !important;
    border-radius:12px !important;
    box-shadow:0 3px 8px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.8), inset 0 -2px 4px rgba(0,0,0,0.06);
    transition:transform 0.1s;
}
.size-btn:active { transform:scale(0.95); }
.size-btn.active {
    box-shadow:0 0 0 3px var(--accent), 0 6px 18px var(--accent-light),
        inset 0 1px 0 rgba(255,255,255,0.4) !important;
    transform:translateY(-2px);
}
.toggle {
    box-shadow:inset 0 3px 6px rgba(0,0,0,0.15), inset 0 -1px 2px rgba(255,255,255,0.5), 0 1px 0 rgba(255,255,255,0.6);
}
.toggle::after {
    box-shadow:0 3px 6px rgba(0,0,0,0.22), 0 1px 2px rgba(0,0,0,0.15),
        inset 0 -1px 2px rgba(0,0,0,0.08), inset 0 1px 0 #fff;
}
</style>
</head>
<body>
<div id="particles"></div>
<div class="container">
<div class="header-card">
    <h2><span id="brandEmoji">📅</span> Расписание</h2>
    <div class="header-right">
        <div class="badge-class">8Г</div>
        <button class="icon-btn" onclick="toggleSettings()">⚙️</button>
    </div>
</div>

<div class="settings-panel" id="settingsPanel">
    <div class="settings-title">🎨 Тема оформления</div>
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
    <div class="toggle-row">
        <div class="toggle-label">✨ Частицы фона</div>
        <div class="toggle" id="tParticles" onclick="toggleParticles()"></div>
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
var THEME_COLORS = {light:'#f0f4f8',dark:'#0f1115',cosmic:'#05021a',ocean:'#e6f4fb',sunset:'#fff1e6',forest:'#eef7ee',sakura:'#fff5f8'};
var THEME_ICONS = {light:'☀️',dark:'🌙',cosmic:'🌌',ocean:'🌊',sunset:'🌅',forest:'🌿',sakura:'🌸'};

(function init(){
    var s = localStorage.getItem('rs_theme') || 'light';
    document.documentElement.setAttribute('data-theme', s);
    var meta = document.getElementById('tcMeta');
    if (meta) meta.setAttribute('content', THEME_COLORS[s] || '#f0f4f8');
    document.querySelectorAll('[data-theme-btn]').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-theme-btn')===s);
    });
    var emoji = document.getElementById('brandEmoji');
    if (emoji) emoji.textContent = '📅';
    var size = localStorage.getItem('rs_size') || 'normal';
    if (size==='small') document.documentElement.classList.add('font-small');
    if (size==='large') document.documentElement.classList.add('font-large');
    document.querySelectorAll('[data-size]').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-size')===size);
    });
    if (localStorage.getItem('rs_compact')==='1') document.documentElement.classList.add('compact');
    if (localStorage.getItem('rs_hide_time')==='1') document.documentElement.classList.add('hide-time');
    document.getElementById('tCompact').classList.toggle('on', localStorage.getItem('rs_compact')==='1');
    document.getElementById('tHideTime').classList.toggle('on', localStorage.getItem('rs_hide_time')==='1');
    document.getElementById('tParticles').classList.toggle('on', localStorage.getItem('rs_particles')!=='0');
    spawnParticles(s);
})();

function setTheme(t){
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('rs_theme', t);
    document.querySelectorAll('[data-theme-btn]').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-theme-btn')===t);
    });
    var meta = document.getElementById('tcMeta');
    if (meta) meta.setAttribute('content', THEME_COLORS[t] || '#f0f4f8');
    var emoji = document.getElementById('brandEmoji');
    if (emoji) emoji.textContent = '📅';
    spawnParticles(t);
}
function setSize(s){
    document.documentElement.classList.remove('font-small','font-large');
    if (s==='small') document.documentElement.classList.add('font-small');
    if (s==='large') document.documentElement.classList.add('font-large');
    localStorage.setItem('rs_size', s);
    document.querySelectorAll('[data-size]').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-size')===s);
    });
}
function toggleCompact(){
    var on = document.documentElement.classList.toggle('compact');
    localStorage.setItem('rs_compact', on?'1':'0');
    document.getElementById('tCompact').classList.toggle('on', on);
}
function toggleHideTime(){
    var on = document.documentElement.classList.toggle('hide-time');
    localStorage.setItem('rs_hide_time', on?'1':'0');
    document.getElementById('tHideTime').classList.toggle('on', on);
}
function toggleParticles(){
    var on = localStorage.getItem('rs_particles')!=='0';
    on = !on;
    localStorage.setItem('rs_particles', on?'1':'0');
    document.getElementById('tParticles').classList.toggle('on', on);
    if (on) spawnParticles(document.documentElement.getAttribute('data-theme'));
    else { var c = document.getElementById('particles'); if (c) c.innerHTML=''; }
}
function spawnParticles(theme){
    var c = document.getElementById('particles');
    if (!c) return;
    c.innerHTML = '';
    if (localStorage.getItem('rs_particles')==='0') return;
    if (window.innerWidth < 320) return;
    var cfg = {
        cosmic:{chars:['✦','✧','·','+'],colors:['#fff','#b794f6','#7cf5c0','#e0d4ff'],count:18,sizes:[10,18],dur:[15,28]},
        sakura:{chars:['🌸','🌸','❀','✿'],colors:['#ec4899','#f9a8d4','#fbcfe8'],count:14,sizes:[14,22],dur:[11,20]},
        forest:{chars:['🍃','🌿','🍂'],colors:['#059669','#16a34a','#84cc16'],count:12,sizes:[14,22],dur:[13,24]},
        ocean:{chars:['●','○','·','◦'],colors:['rgba(34,211,238,0.85)','rgba(8,145,178,0.75)','rgba(255,255,255,0.7)'],count:12,sizes:[8,16],dur:[11,20]},
        sunset:{chars:['✨','·','✦'],colors:['#f97316','#ec4899','#fbbf24'],count:10,sizes:[10,18],dur:[13,22]}
    }[theme];
    if (!cfg) return;
    var mobile = window.innerWidth < 820;
    var n = mobile ? Math.max(6, Math.round(cfg.count*0.65)) : cfg.count;
    var frag = document.createDocumentFragment();
    for (var i=0;i<n;i++){
        var el = document.createElement('span');
        el.className = 'particle';
        el.textContent = cfg.chars[Math.floor(Math.random()*cfg.chars.length)];
        el.style.left = (Math.random()*100)+'%';
        var sz = cfg.sizes[0]+Math.random()*(cfg.sizes[1]-cfg.sizes[0]);
        el.style.fontSize = sz+'px';
        el.style.color = cfg.colors[Math.floor(Math.random()*cfg.colors.length)];
        var d = cfg.dur[0]+Math.random()*(cfg.dur[1]-cfg.dur[0]);
        el.style.animationDuration = d+'s';
        el.style.animationDelay = (-Math.random()*d)+'s';
        frag.appendChild(el);
    }
    c.appendChild(frag);
}
function toggleSettings(){ document.getElementById('settingsPanel').classList.toggle('open'); }
function showDay(day){
    document.querySelectorAll('.day-block').forEach(function(el){el.classList.remove('active');});
    var t = document.getElementById('day-'+day);
    if (t) t.classList.add('active');
    document.querySelectorAll('.tab').forEach(function(x){
        x.classList.toggle('active', x.getAttribute('data-day')===day);
    });
}
document.addEventListener('visibilitychange', function(){
    var ps = document.hidden ? 'paused' : 'running';
    document.querySelectorAll('.particle').forEach(function(p){p.style.animationPlayState = ps;});
});

/* ТАЙМЕР */
(function(){
    function tick(){
        var nowSec = Math.floor(Date.now()/1000);
        var nEl = document.querySelector('.live-banner.now');
        if (nEl) {
            var end = parseInt(nEl.getAttribute('data-end-unix'),10);
            var until = nEl.getAttribute('data-until')||'';
            var tEl = nEl.querySelector('.live-timer');
            if (end && tEl) {
                var left = Math.max(0, Math.ceil((end-nowSec)/60));
                tEl.textContent = 'до '+until+' · осталось '+left+' мин';
            }
        }
        var bEl = document.querySelector('.live-banner.before');
        if (bEl) {
            var st = parseInt(bEl.getAttribute('data-start-unix'),10);
            var start = bEl.getAttribute('data-start')||'';
            var tEl2 = bEl.querySelector('.live-timer');
            if (st && tEl2) {
                var wait = Math.max(0, Math.ceil((st-nowSec)/60));
                tEl2.textContent = 'в '+start+' · через '+wait+' мин';
            }
        }
    }
    tick();
    setInterval(tick, 10000);
    document.addEventListener('visibilitychange', function(){ if (!document.hidden) tick(); });
})();

var deferredPrompt = null;
var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e){ e.preventDefault(); deferredPrompt = e; renderInstall(); });
window.addEventListener('appinstalled', function(){ deferredPrompt = null; localStorage.setItem('rs_installed','1'); renderInstall(); });
function renderInstall(){
    var el = document.getElementById('installSection');
    if (!el) return;
    if (isStandalone || localStorage.getItem('rs_installed')==='1') {
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>'; return;
    }
    if (deferredPrompt) {
        el.innerHTML = '<button class="install-btn" onclick="doInstall()">📲 Установить приложение</button>'; return;
    }
    var ua = navigator.userAgent, hint;
    if (/iPhone|iPad|iPod/i.test(ua)) hint = '📱 iPhone: Safari → «Поделиться» → «На экран Домой».';
    else if (/Android/i.test(ua)) hint = '📱 Android: Chrome → ⋮ → «Установить приложение».';
    else hint = '💻 ПК: в Chrome — иконка в адресной строке.';
    el.innerHTML = '<div class="hint-text">'+hint+'</div>';
}
function doInstall(){
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(function(c){
        if (c.outcome === 'accepted') localStorage.setItem('rs_installed','1');
        deferredPrompt = null; renderInstall();
    });
}
renderInstall();
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function(){
        navigator.serviceWorker.register('/sw.js').catch(function(){});
    });
}
</script>
</body>
</html>"""


def build_tabs(active, days):
    today_idx = datetime.now(PERM_TZ).weekday()
    html = '<div class="tabs">'
    for i, full in enumerate(DAY_FULL):
        short = DAY_SHORT[full]
        has = full in days and len(days[full])>0
        cls = "tab"
        if full == active: cls += " active"
        if i == today_idx: cls += " today"
        html += f'<button class="{cls}" data-day="{full}" onclick="showDay(\'{full}\')">'
        html += f'{short}<span class="tab-day">{"•" if has else "—"}</span></button>'
    html += '</div>'
    return html


def build_live(st):
    if not st: return ""
    if st["type"] == "now":
        return ('<div class="live-banner now" data-end-unix="' + str(st["end_unix"]) + '" data-until="' + st["until"] + '">'
            '<div class="live-dot"></div><div class="live-info">'
            '<div class="live-label">Сейчас идёт</div>'
            f'<div class="live-lesson">{st["lesson"]}</div>'
            f'<div class="live-time"><span class="live-timer">до {st["until"]}</span></div>'
            f'<div class="progress-bar"><div class="progress-fill" style="width:{st["progress"]}%"></div></div>'
            '</div></div>')
    if st["type"] == "before":
        return ('<div class="live-banner before" data-start-unix="' + str(st["start_unix"]) + '" data-start="' + st["start"] + '">'
            '<div class="live-dot"></div><div class="live-info">'
            '<div class="live-label">Скоро урок</div>'
            f'<div class="live-lesson">{st["lesson"]}</div>'
            f'<div class="live-time"><span class="live-timer">в {st["start"]}</span></div>'
            '</div></div>')
    return ""


def build_content(days, active, err, st):
    if err and not days:
        return f"<div class='error'>{err}</div>"
    today_idx = datetime.now(PERM_TZ).weekday()
    today_full = DAY_FULL[today_idx] if today_idx < 6 else ""
    html = ""
    for full in DAY_FULL:
        lessons = days.get(full, [])
        cls = " active" if full == active else ""
        html += f'<div class="day-block{cls}" id="day-{full}">'
        if full == today_full:
            html += f'<div class="day-title today">{full}<span class="today-pill">✨ Сегодня</span></div>'
        else:
            html += f'<div class="day-title">{full}</div>'
        if not lessons:
            html += '<div class="info-box">📭 Нет уроков на этот день</div>'
        else:
            for tv, num, lesson in lessons:
                cc = "card"; pill = ""
                if full == today_full and st and st["type"]=="now" and num==st["num"]:
                    cc += " now"; pill = '<span class="now-pill">сейчас</span>'
                elif full == today_full and st and st["type"]=="before" and num==st["num"]:
                    cc += " next-up"
                html += f'<div class="{cc}"><div class="num">{num}</div>'
                html += f'<div class="left-side"><div class="time">{tv}</div>'
                html += f'<div class="lesson">{lesson}</div></div>{pill}</div>'
        html += '</div>'
    return html


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, ct, body):
        self.send_response(200); self.send_header("Content-type", ct)
        self.send_header("Cache-Control","public, max-age=3600"); self.end_headers()
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
            cur_day = DAY_FULL[wi] if wi<6 else "Суббота"
            is_weekend = wi >= 5
            refresh = "<meta http-equiv='refresh' content='90'>" if not (1<=hour<5) else ""
            days, err = get_schedule()

            today_lessons = days.get(cur_day, [])
            school_over = (hour>14 or (hour==14 and minute>=40) or is_weekend or not today_lessons)
            if school_over and wi<5:
                ni = wi+1
                if ni<6:
                    tmr = DAY_FULL[ni]
                    active = tmr if days.get(tmr) else cur_day
                else:
                    active = cur_day
            else:
                active = cur_day
            if active not in DAY_FULL: active = cur_day
            if not days.get(active) and days.get(cur_day): active = cur_day

            st = get_live_status(today_lessons) if not is_weekend else None
            live = build_live(st)
            tabs = build_tabs(active, days)
            content = build_content(days, active, err, st)

            html = PAGE
            html = html.replace("{refresh_tag}", refresh)
            html = html.replace("{live_banner}", live)
            html = html.replace("{tabs}", tabs)
            html = html.replace("{content}", content)
            html = html.replace("{sheet_url}", SHEET_URL)

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Cache-Control","no-cache, no-store, must-revalidate")
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
