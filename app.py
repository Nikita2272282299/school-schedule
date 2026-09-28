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
DAY_FULL = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота"]

cache = {"days_schedule": {}, "error_msg": "", "last_update": 0}
CACHE_TTL = 300

MANIFEST = '{"name":"Расписание 8Г","short_name":"8Г","start_url":"/","display":"standalone","background_color":"#0a0620","theme_color":"#6366f1","icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6366f1"/><stop offset="0.5" stop-color="#8b5cf6"/><stop offset="1" stop-color="#a855f7"/></linearGradient></defs><rect width="512" height="512" rx="118" fill="url(#bg)"/><rect x="98" y="128" width="316" height="288" rx="36" fill="#ffffff"/><rect x="98" y="128" width="316" height="76" rx="36" fill="#1e1b4b"/><rect x="98" y="176" width="316" height="28" fill="#1e1b4b"/><circle cx="168" cy="166" r="12" fill="#ffffff"/><circle cx="344" cy="166" r="12" fill="#ffffff"/><rect x="152" y="86" width="22" height="72" rx="11" fill="#1e1b4b"/><rect x="338" y="86" width="22" height="72" rx="11" fill="#1e1b4b"/><text x="256" y="358" font-family="Arial,Helvetica,sans-serif" font-size="180" font-weight="900" fill="#1e1b4b" text-anchor="middle" letter-spacing="-8">8Г</text></svg>'''

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>{self.registration.unregister();caches.keys().then(k=>k.forEach(x=>caches.delete(x)));self.clients.claim();});"


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
    --bg:#eef2f7; --bg2:#e0e7f0; --card:#ffffff;
    --text:#0f172a; --muted:#64748b; --accent:#6366f1; --accent2:#a855f7;
    --accent-soft:rgba(99,102,241,0.10); --accent-soft2:rgba(168,85,247,0.10);
    --border:rgba(15,23,42,0.06); --shadow:0 2px 12px rgba(15,23,42,0.06);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
}
[data-theme="dark"] {
    --bg:#0b0d12; --bg2:#131720; --card:#1a1f2b;
    --text:#e8ecf3; --muted:#8b95a8; --accent:#818cf8; --accent2:#c084fc;
    --accent-soft:rgba(129,140,248,0.14); --accent-soft2:rgba(192,132,252,0.14);
    --border:rgba(255,255,255,0.06); --shadow:0 2px 12px rgba(0,0,0,0.4);
    --green:#34d399; --green-soft:rgba(52,211,153,0.14);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.14);
    color-scheme:dark;
}
[data-theme="cosmic"] {
    --bg:#05021a; --bg2:#0f0730; --card:#18103a;
    --text:#ece6ff; --muted:#a89cc7; --accent:#b794f6; --accent2:#7cf5c0;
    --accent-soft:rgba(183,148,246,0.16); --accent-soft2:rgba(124,245,192,0.12);
    --border:rgba(183,148,246,0.14); --shadow:0 4px 20px rgba(120,60,220,0.25);
    --green:#7cf5c0; --green-soft:rgba(124,245,192,0.14);
    --orange:#fbbf77; --orange-soft:rgba(251,191,119,0.14);
    color-scheme:dark;
}
html { min-height:100%; background:var(--bg); }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body {
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:var(--bg); color:var(--text); margin:0;
    padding:20px 14px 30px; min-height:100vh; -webkit-font-smoothing:antialiased;
    transition:background 0.3s ease, color 0.3s ease;
}
[data-theme="light"] body { background-image:linear-gradient(180deg,#f1f5fa 0%,#e4ebf3 100%); }
[data-theme="dark"] body { background-image:linear-gradient(180deg,#10131a 0%,#0b0d12 100%); }
[data-theme="cosmic"] body {
    background-image:
        radial-gradient(1.5px 1.5px at 24px 32px, rgba(255,255,255,0.9), transparent 60%),
        radial-gradient(1px 1px at 118px 88px, rgba(255,255,255,0.7), transparent 60%),
        radial-gradient(1.8px 1.8px at 210px 156px, rgba(183,148,246,0.95), transparent 60%),
        radial-gradient(1px 1px at 60px 200px, rgba(255,255,255,0.6), transparent 60%),
        radial-gradient(1.5px 1.5px at 260px 40px, rgba(124,245,192,0.9), transparent 60%),
        radial-gradient(1px 1px at 180px 240px, rgba(255,255,255,0.8), transparent 60%),
        linear-gradient(180deg,#0a0424 0%,#05021a 55%,#01000a 100%);
    background-size:380px 300px, 380px 300px, 380px 300px, 380px 300px, 380px 300px, 380px 300px, 100% 100%;
    background-repeat:repeat, repeat, repeat, repeat, repeat, repeat, no-repeat;
}
.container { width:100%; max-width:520px; margin:0 auto; }

.header {
    background:var(--card); border:1px solid var(--border); border-radius:22px;
    padding:16px 20px; box-shadow:var(--shadow); margin-bottom:14px;
    display:flex; align-items:center; justify-content:space-between; gap:12px;
}
.brand { display:flex; align-items:center; gap:12px; min-width:0; }
.brand-logo {
    width:46px; height:46px; border-radius:14px; flex-shrink:0;
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    display:flex; align-items:center; justify-content:center; font-size:1.5rem;
}
.brand-title { font-size:1.05rem; font-weight:800; line-height:1.1; }
.brand-sub { font-size:0.75rem; color:var(--muted); font-weight:600; margin-top:2px; }
.header-right { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.badge-class {
    background:linear-gradient(135deg,var(--accent-soft),var(--accent-soft2));
    color:var(--accent); padding:7px 13px; border-radius:12px;
    font-weight:800; font-size:0.95rem; border:1px solid var(--border);
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
    transition:grid-template-rows 0.3s ease, margin-bottom 0.3s ease, box-shadow 0.3s ease;
}
.settings.open { grid-template-rows:1fr; margin-bottom:14px; box-shadow:var(--shadow); }
.settings-inner { overflow:hidden; min-height:0; padding:0 18px; transition:padding 0.3s ease; }
.settings.open .settings-inner { padding:18px; }
.settings-title { font-weight:800; font-size:0.8rem; color:var(--muted);
    text-transform:uppercase; letter-spacing:0.06em; margin-bottom:10px; }
.settings-title:not(:first-child) { margin-top:16px; }
.theme-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
.theme-btn {
    padding:14px 6px; border-radius:12px; border:2px solid transparent;
    background:var(--bg2); color:var(--text); font-weight:700; font-size:0.75rem;
    cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:6px;
    font-family:inherit;
}
.theme-btn .emoji { font-size:1.4rem; line-height:1; }
.theme-btn.active { border-color:var(--accent); background:var(--accent-soft); }
.install-btn {
    width:100%; padding:13px; border-radius:14px; border:none;
    background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white;
    font-weight:800; font-size:0.9rem; cursor:pointer; font-family:inherit;
}
.install-btn:active { opacity:0.85; }
.installed-badge { color:var(--green); font-weight:700; font-size:0.9rem;
    padding:10px 0; display:flex; align-items:center; gap:6px; }
.hint-text { color:var(--muted); font-size:0.82rem; line-height:1.5; }

.switcher {
    display:flex; gap:6px; margin-bottom:14px; padding:4px;
    background:var(--card); border-radius:16px; border:1px solid var(--border);
    box-shadow:var(--shadow);
}
.switch-btn {
    flex:1; padding:11px; border-radius:12px; border:none;
    background:transparent; color:var(--muted); font-weight:800; font-size:0.88rem;
    cursor:pointer; font-family:inherit;
}
.switch-btn.active { background:linear-gradient(135deg,var(--accent),var(--accent2)); color:white; }

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
    border:1px solid var(--border);
}
.card.now { box-shadow:0 8px 28px var(--green-soft),0 0 0 1px var(--green);
    background:linear-gradient(135deg,var(--green-soft),var(--card)); }
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
.info-box {
    background:var(--card); padding:32px 20px; border-radius:20px;
    box-shadow:var(--shadow); text-align:center; font-size:1rem; font-weight:700;
    color:var(--muted); border:1px solid var(--border); line-height:1.5;
}
.info-box .big { font-size:2.2rem; display:block; margin-bottom:8px; }
.error { background:linear-gradient(135deg,rgba(239,68,68,0.1),var(--card));
    color:#ef4444; padding:20px; border-radius:18px; font-weight:700;
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
        </div>
        <div class="settings-title">📱 Приложение</div>
        <div id="installSection"></div>
    </div>
</div>

{live_banner}
{switcher}
{content}

<a class="sheet-link" href="{sheet_url}" target="_blank" rel="noopener">
    <span>📊</span> Открыть таблицу в Google Sheets
</a>
</div>

<script>
var THEME_COLORS = {light:'#eef2f7',dark:'#0b0d12',cosmic:'#05021a'};
(function init() {
    var s = localStorage.getItem('rs_theme') || 'light';
    if (['light','dark','cosmic'].indexOf(s) === -1) { s = 'light'; localStorage.setItem('rs_theme','light'); }
    document.documentElement.setAttribute('data-theme', s);
    var m = document.getElementById('tcMeta');
    if (m) m.setAttribute('content', THEME_COLORS[s] || '#eef2f7');
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-theme-btn') === s);
    });
})();
function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('rs_theme', t);
    document.querySelectorAll('[data-theme-btn]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-theme-btn') === t);
    });
    var m = document.getElementById('tcMeta');
    if (m) m.setAttribute('content', THEME_COLORS[t] || '#eef2f7');
}
function toggleSettings() { document.getElementById('settingsPanel').classList.toggle('open'); }
var deferredPrompt = null;
var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e) { e.preventDefault(); deferredPrompt = e; renderInstall(); });
window.addEventListener('appinstalled', function() { deferredPrompt = null; localStorage.setItem('rs_installed','1'); renderInstall(); });
function renderInstall() {
    var el = document.getElementById('installSection');
    if (!el) return;
    if (isStandalone || localStorage.getItem('rs_installed') === '1') {
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>'; return;
    }
    if (deferredPrompt) {
        el.innerHTML = '<button class="install-btn" onclick="doInstall()">📲 Установить приложение</button>'; return;
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
        deferredPrompt = null; renderInstall();
    });
}
renderInstall();
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(function(r){r.forEach(function(x){x.unregister();});});
    if (window.caches) caches.keys().then(function(k){k.forEach(function(x){caches.delete(x);});});
}
</script>
</body>
</html>"""


def build_switcher(today_name, tomorrow_name, show_tomorrow):
    t1 = ' active' if not show_tomorrow else ''
    t2 = ' active' if show_tomorrow else ''
    h = '<div class="switcher">'
    h += f'<button class="switch-btn{t1}" onclick="switchDay(false)">Сегодня · {today_name[:2]}</button>'
    h += f'<button class="switch-btn{t2}" onclick="switchDay(true)">Завтра · {tomorrow_name[:2]}</button>'
    h += '</div>'
    return h


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


def build_day_block(day_name, lessons, is_today, live_status):
    h = f'<div class="day-block active" id="day-block">'
    pill = '<span class="today-pill">✨ Сегодня</span>' if is_today else ''
    h += f'<div class="day-title">{day_name}{pill}</div>'
    if not lessons:
        h += '<div class="info-box"><span class="big">📭</span>Нет уроков</div>'
    else:
        for tv, num, lesson in lessons:
            cc = "card"; np = ""
            if is_today and live_status and live_status["type"] == "now" and num == live_status["num"]:
                cc += " now"; np = '<span class="now-pill">сейчас</span>'
            elif is_today and live_status and live_status["type"] == "before" and num == live_status["num"]:
                cc += " next-up"
            h += f'<div class="{cc}"><div class="num">{num}</div>'
            h += f'<div class="left-side"><div class="time">{tv}</div>'
            h += f'<div class="lesson">{lesson}</div></div>{np}</div>'
    h += '</div>'
    return h


class SimpleHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): return
    def _send(self, ct, body):
        self.send_response(200); self.send_header("Content-type", ct)
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers(); self.wfile.write(body)

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
            today_name = DAY_FULL[wi] if wi < 6 else "Суббота"
            is_weekend = wi >= 5
            refresh_tag = "<meta http-equiv='refresh' content='900'>" if not (1 <= hour < 5) else ""
            days_schedule, error_msg = get_schedule()

            months = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"]
            header_date = f"{today_name}, {now.day} {months[now.month-1]}"

            tomorrow_idx = (wi + 1) % 6
            tomorrow_name = DAY_FULL[tomorrow_idx] if wi < 5 else "Понедельник"
            if wi == 5: tomorrow_name = "Понедельник"

            today_lessons = days_schedule.get(today_name, [])
            tomorrow_lessons = days_schedule.get(tomorrow_name, [])
            school_over = (hour > 14 or (hour == 14 and minute >= 40) or is_weekend or not today_lessons)
            show_tomorrow = school_over and bool(tomorrow_lessons)

            live_status = get_live_status(today_lessons) if not is_weekend else None
            live_banner = build_live_banner(live_status)
            switcher = build_switcher(today_name, tomorrow_name, show_tomorrow)

            # Оба блока — показываем сразу, JS переключает
            content = '<div id="dayToday" style="display:%s">' % ('none' if show_tomorrow else 'block')
            content += build_day_block(today_name, today_lessons, True, live_status).replace(' active','') 
            content += '</div>'
            content += '<div id="dayTomorrow" style="display:%s">' % ('block' if show_tomorrow else 'none')
            content += build_day_block(tomorrow_name, tomorrow_lessons, False, None).replace(' active','')
            content += '</div>'

            html = PAGE_TEMPLATE
            html = html.replace("{refresh_tag}", refresh_tag)
            html = html.replace("{header_date}", header_date)
            html = html.replace("{live_banner}", live_banner)
            html = html.replace("{switcher}", switcher)
            html = html.replace("{content}", content)
            html = html.replace("{sheet_url}", SHEET_URL)

            # Добавляем switchDay в JS
            js_add = '''
function switchDay(tmr) {
    document.querySelectorAll('.switch-btn').forEach(function(b,i){
        b.classList.toggle('active', (i===1)===tmr);
    });
    document.getElementById('dayToday').style.display = tmr ? 'none' : 'block';
    document.getElementById('dayTomorrow').style.display = tmr ? 'block' : 'none';
}
'''
            html = html.replace("function toggleSettings()", js_add + "function toggleSettings()")

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
