import threading, urllib.request, csv, io, time, os, json, uuid, hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# ============ CONFIG ============
SPREADSHEET_ID = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SELF_URL = "https://school-schedule-4ldw.onrender.com/"
PERM_TZ = timezone(timedelta(hours=5))
CLASS_CODE = "8г"
ADMIN_KEY = "nikita_admin_2026"

TIME_TO_NUM = {"8:00-8:40":1,"8:50-9:30":2,"9:45-10:25":3,"10:40-11:20":4,
    "11:35-12:15":5,"12:25-13:05":6,"13:15-13:55":7,"14:00-14:40":8}
DAY_SHORT = {"Понедельник":"Пн","Вторник":"Вт","Среда":"Ср","Четверг":"Чт","Пятница":"Пт",}
DAY_FULL = ["Понедельник","Вторник","Среда","Четверг","Пятница"]

VISITORS_FILE = "visitors.json"
MESSAGES_FILE = "messages.json"
BLOCKED_FILE = "blocked.json"
CHANGE_FILE = "last_change.json"
FILLED_FILE = "filled_days.json"
CACHE_FILE = "schedule_cache.json"

cache = {"days_schedule": {}, "error_msg": "", "last_update": 0}
CACHE_TTL = 300
change_tracker = {"prev_hash": "", "ts": 0}
new_days_for_render = []
_lock = threading.Lock()

MANIFEST = '{"name":"Расписание 8Г","short_name":"8Г","start_url":"/","display":"standalone","background_color":"#0a0620","theme_color":"#6366f1","icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any maskable"}]}'

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6366f1"/><stop offset="1" stop-color="#7950f2"/></linearGradient></defs><rect width="512" height="512" rx="110" fill="url(#g)"/><text x="256" y="360" font-family="Arial,sans-serif" font-size="230" font-weight="900" fill="#fff" text-anchor="middle">8Г</text></svg>'''

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>self.clients.claim());self.addEventListener('fetch',function(e){if(e.request.method!=='GET')return;e.respondWith(caches.open('school-v5').then(function(cache){return fetch(e.request).then(function(resp){if(resp&&resp.status===200)cache.put(e.request,resp.clone());return resp;}).catch(function(){return cache.match(e.request).then(function(r){return r||cache.match('/');});});}));});"

# ============ HELPERS ============
def _ld(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _sv(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

def _week_key():
    n = datetime.now(PERM_TZ)
    iso = n.isocalendar()
    return f"{iso[0]}-W{iso[1]}"

def _sched_hash(s):
    try:
        return hashlib.md5(json.dumps(s, sort_keys=True, default=list).encode()).hexdigest()
    except Exception:
        return ""

def load_disk_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("week") != _week_key(): return None
        days = {k: [tuple(x) for x in v] for k, v in d.get("days", {}).items()}
        return days
    except Exception:
        return None

def save_disk_cache(days):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"week": _week_key(), "days": {k: [list(x) for x in v] for k, v in days.items()}}, f, ensure_ascii=False)
    except Exception:
        pass

def load_change():
    d = _ld(CHANGE_FILE, {})
    change_tracker["prev_hash"] = d.get("prev_hash", "")
    change_tracker["ts"] = int(d.get("ts", 0))

def save_change():
    _sv(CHANGE_FILE, {"prev_hash": change_tracker["prev_hash"], "ts": change_tracker["ts"]})

def check_new_days(days):
    global new_days_for_render
    try:
        data = _ld(FILLED_FILE, {})
        wk = _week_key()
        if data.get("week") != wk: data = {"week": wk, "filled": []}
        prev = set(data.get("filled", []))
        cur = set(d for d, v in days.items() if v)
        new_days_for_render = sorted(cur - prev)
        data["filled"] = sorted(cur)
        _sv(FILLED_FILE, data)
    except Exception:
        new_days_for_render = []

def log_visit(vid, ip, ua):
    if not vid: return
    with _lock:
        d = _ld(VISITORS_FILE, {})
        now = int(time.time())
        if vid in d:
            d[vid]["last"] = now
            d[vid]["count"] = d[vid].get("count", 0) + 1
            d[vid]["ip"] = ip
        else:
            d[vid] = {"ip": ip, "ua": (ua or "")[:200], "first": now, "last": now, "count": 1, "name": ""}
        _sv(VISITORS_FILE, d)

def get_pending(vid):
    if not vid: return None
    with _lock:
        d = _ld(MESSAGES_FILE, {})
        for m in d.get(vid, []):
            if not m.get("read"): return m
        return None

def mark_read(vid, mid):
    with _lock:
        d = _ld(MESSAGES_FILE, {})
        for m in d.get(vid, []):
            if m.get("id") == mid: m["read"] = True
        _sv(MESSAGES_FILE, d)

def send_msg(vid, text):
    if not vid or not text: return
    with _lock:
        d = _ld(MESSAGES_FILE, {})
        d.setdefault(vid, []).append({"id": uuid.uuid4().hex[:8], "text": text, "ts": int(time.time()), "read": False})
        _sv(MESSAGES_FILE, d)

def send_all(text):
    v = _ld(VISITORS_FILE, {})
    for vid in list(v.keys()): send_msg(vid, text)

def is_blocked(vid):
    if not vid: return False
    with _lock:
        d = _ld(BLOCKED_FILE, {})
        return bool(d.get(vid))

def block_v(vid):
    if not vid: return
    with _lock:
        d = _ld(BLOCKED_FILE, {}); d[vid] = int(time.time()); _sv(BLOCKED_FILE, d)

def unblock_v(vid):
    if not vid: return
    with _lock:
        d = _ld(BLOCKED_FILE, {})
        if vid in d: del d[vid]
        _sv(BLOCKED_FILE, d)

def rename_v(vid, name):
    if not vid: return
    with _lock:
        d = _ld(VISITORS_FILE, {})
        if vid in d:
            d[vid]["name"] = (name or "")[:30]
            _sv(VISITORS_FILE, d)

# ============ SCHEDULE ============
def get_schedule():
    now = time.time()
    if cache["days_schedule"] and (now - cache["last_update"] < CACHE_TTL):
        return cache["days_schedule"], cache["error_msg"]
    days = {}; err = ""
    try:
        req = urllib.request.urlopen(CSV_URL, timeout=6)
        data = req.read().decode("utf-8")
        reader = list(csv.reader(io.StringIO(data)))
        col = -1
        for row in reader:
            for i, c in enumerate(row):
                if c.replace(" ", "").lower() == CLASS_CODE:
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
            _h = _sched_hash(days)
            if change_tracker["prev_hash"] and _h and _h != change_tracker["prev_hash"]:
                change_tracker["ts"] = int(time.time())
            change_tracker["prev_hash"] = _h
            save_change()
            save_disk_cache(days)
            check_new_days(days)
        else:
            err = f"Класс {CLASS_CODE.upper()} не найден."; cache["error_msg"] = err
    except Exception:
        if cache["days_schedule"]: return cache["days_schedule"], ""
        disk = load_disk_cache()
        if disk:
            cache["days_schedule"] = disk; cache["last_update"] = now
            return disk, ""
        cache["error_msg"] = "Офлайн-режим"
    return cache["days_schedule"], cache["error_msg"]

def get_live_status(lessons):
    if not lessons: return None
    now = datetime.now(PERM_TZ)
    cur = now.hour * 60 + now.minute
    if cur < 6*60 + 30: return None
    for tv, num, lesson in lessons:
        try:
            s, e = tv.split("-")
            sh, sm = map(int, s.split(":")); eh, em = map(int, e.split(":"))
        except Exception: continue
        ss = sh*60+sm; ee = eh*60+em
        if ss <= cur < ee:
            prog = int((cur - ss) / max(ee - ss, 1) * 100)
            return {"type":"now","num":num,"lesson":lesson,"progress":prog,
                    "left":ee-cur,"until":e,"end_unix":int(now.replace(hour=eh,minute=em,second=0,microsecond=0).timestamp())}
        if cur < ss:
            return {"type":"before","num":num,"lesson":lesson,"wait":ss-cur,"start":s,
                    "start_unix":int(now.replace(hour=sh,minute=sm,second=0,microsecond=0).timestamp())}
    return None

# ============ HTML ============
PAGE = """<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#f0f4f8" id="tcMeta">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="8Г">
<title>Расписание 8Г</title>
<style>
:root, [data-theme="light"] {
    --bg:#f0f4f8; --card-bg:#ffffff; --card:#ffffff;
    --text-main:#1a202c; --text:#1a202c; --text-muted:#4a5568; --muted:#4a5568;
    --accent:#4c6ef5; --accent2:#7950f2; --accent-light:rgba(76,110,245,0.12);
    --border:rgba(15,23,42,0.08); --shadow:0 4px 16px rgba(15,23,42,0.06);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
    --num-bg:var(--accent); --num-color:#fff; --num-shadow:0 3px 10px var(--accent-light);
}
[data-theme="dark"] {
    --bg:#0f1115; --card-bg:#1a1d24; --card:#1a1d24;
    --text-main:#e6e8ec; --text:#e6e8ec; --text-muted:#9aa3b2; --muted:#9aa3b2;
    --accent:#7c93ff; --accent2:#c084fc; --accent-light:rgba(124,147,255,0.15);
    --border:rgba(255,255,255,0.07); --shadow:0 4px 16px rgba(0,0,0,0.4);
    --green:#34d399; --green-soft:rgba(52,211,153,0.14);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.14);
    --num-bg:var(--accent); --num-color:#fff; --num-shadow:0 3px 10px var(--accent-light);
    color-scheme:dark;
}
[data-theme="cosmic"] {
    --bg:#05021a; --card-bg:rgba(30,20,60,0.72); --card:rgba(30,20,60,0.72);
    --text-main:#eae4ff; --text:#eae4ff; --text-muted:#b3a8d9; --muted:#b3a8d9;
    --accent:#b794f6; --accent2:#7cf5c0; --accent-light:rgba(183,148,246,0.18);
    --border:rgba(183,148,246,0.2); --shadow:0 8px 30px rgba(140,80,255,0.25);
    --green:#7cf5c0; --green-soft:rgba(124,245,192,0.15);
    --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.15);
    --num-bg:var(--accent); --num-color:#1a1030; --num-shadow:0 0 12px rgba(183,148,246,0.5);
    color-scheme:dark;
}
[data-theme="ocean"] {
    --bg:#c7e8f5; --card-bg:#ffffff; --card:#ffffff;
    --text-main:#062b3d; --text:#062b3d; --text-muted:#5a7d92; --muted:#5a7d92;
    --accent:#0891b2; --accent2:#22d3ee; --accent-light:rgba(8,145,178,0.12);
    --border:rgba(6,43,61,0.08); --shadow:0 4px 16px rgba(8,145,178,0.1);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
    --num-bg:var(--accent); --num-color:#fff; --num-shadow:0 3px 10px var(--accent-light);
}
[data-theme="sunset"] {
    --bg:#ffd9b0; --card-bg:#fffbf5; --card:#fffbf5;
    --text-main:#3d1a0a; --text:#3d1a0a; --text-muted:#8a6550; --muted:#8a6550;
    --accent:#f97316; --accent2:#ec4899; --accent-light:rgba(249,115,22,0.12);
    --border:rgba(61,26,10,0.08); --shadow:0 4px 16px rgba(249,115,22,0.14);
    --green:#059669; --green-soft:rgba(5,150,105,0.12);
    --orange:#d97706; --orange-soft:rgba(217,119,6,0.12);
    --num-bg:var(--accent); --num-color:#fff; --num-shadow:0 3px 10px var(--accent-light);
}
[data-theme="forest"] {
    --bg:#d4e8c8; --card-bg:#ffffff; --card:#ffffff;
    --text-main:#0f2e1b; --text:#0f2e1b; --text-muted:#5f7c68; --muted:#5f7c68;
    --accent:#059669; --accent2:#84cc16; --accent-light:rgba(5,150,105,0.12);
    --border:rgba(15,46,27,0.08); --shadow:0 4px 16px rgba(5,150,105,0.1);
    --green:#16a34a; --green-soft:rgba(22,163,74,0.12);
    --orange:#ca8a04; --orange-soft:rgba(202,138,4,0.12);
    --num-bg:var(--accent); --num-color:#fff; --num-shadow:0 3px 10px var(--accent-light);
}
[data-theme="sakura"] {
    --bg:#ffd6e4; --card-bg:#ffffff; --card:#ffffff;
    --text-main:#3d1029; --text:#3d1029; --text-muted:#9a6782; --muted:#9a6782;
    --accent:#ec4899; --accent2:#a855f7; --accent-light:rgba(236,72,153,0.12);
    --border:rgba(61,16,41,0.08); --shadow:0 4px 16px rgba(236,72,153,0.1);
    --green:#059669; --green-soft:rgba(5,150,105,0.12);
    --orange:#ea580c; --orange-soft:rgba(234,88,12,0.12);
    --num-bg:var(--accent); --num-color:#fff; --num-shadow:0 3px 10px var(--accent-light);
}
[data-theme="custom"] {
    --bg: var(--cu-bg,#eef2f7); --card-bg: var(--cu-card,#ffffff); --card: var(--cu-card,#ffffff);
    --text-main: var(--cu-text,#0f172a); --text: var(--cu-text,#0f172a);
    --text-muted: var(--cu-muted,#64748b); --muted: var(--cu-muted,#64748b);
    --accent: var(--cu-accent,#6366f1); --accent2: var(--cu-accent2,#a855f7);
    --accent-light: var(--cu-accent-light,rgba(99,102,241,0.12));
    --border: rgba(127,127,127,0.15); --shadow: 0 4px 20px rgba(0,0,0,0.08);
    --green:#10b981; --green-soft:rgba(16,185,129,0.12);
    --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
    --num-bg:var(--accent); --num-color:#fff; --num-shadow:0 3px 10px var(--accent-light);
}
html { min-height:100%; background: var(--bg); }
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body {
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background: var(--bg); color: var(--text-main); margin:0;
    padding:20px 14px 30px;
    min-height:100vh; -webkit-font-smoothing:antialiased;
    transition: background 0.3s ease, color 0.3s ease;
    overflow-x: hidden;
}
[data-theme="light"] body { background-image: linear-gradient(180deg,#f1f5fa,#e4ebf3); }
[data-theme="dark"] body { background-image: linear-gradient(180deg,#10131a,#0b0d12); }
[data-theme="cosmic"] body { background-image: radial-gradient(ellipse at 20% 15%, rgba(139,92,246,0.3), transparent 50%), radial-gradient(ellipse at 85% 75%, rgba(56,189,248,0.2), transparent 55%), linear-gradient(180deg,#0a0424,#05021a 55%,#01000a); }
[data-theme="ocean"] body { background-image: linear-gradient(180deg,#c7e8f5,#94d0e6 45%,#5aafd0); }
[data-theme="sunset"] body { background-image: linear-gradient(180deg,#ffe0a8,#ffb572 40%,#e88898); }
[data-theme="forest"] body { background-image: linear-gradient(180deg,#dff0d0,#b8dfa8 40%,#7abb6c); }
[data-theme="sakura"] body { background-image: linear-gradient(180deg,#ffeaf0,#ffd0dd 50%,#ffb0c8); }
.container { width:100%; max-width:500px; margin:0 auto; position:relative; z-index:1; }

#particles { position:fixed; inset:0; pointer-events:none; z-index:0; overflow:hidden; }
.particle { position:absolute; top:-40px; user-select:none; animation-name:fall; animation-timing-function:linear; animation-iteration-count:infinite; }
@keyframes fall { 0%{transform:translate3d(0,-40px,0) rotate(0);opacity:0} 10%{opacity:.85} 90%{opacity:.85} 100%{transform:translate3d(30px,110vh,0) rotate(360deg);opacity:0} }

.header-card { background: var(--card-bg); border:1px solid var(--border); border-radius:22px; padding:16px 20px; box-shadow: var(--shadow); margin-bottom:14px; display:flex; align-items:center; justify-content:space-between; gap:10px; position:relative; }
h2 { margin:0; font-size:1.4rem; font-weight:800; display:flex; align-items:center; gap:10px; }
h2 span:not(#adminTap):not(.brand-emoji) { background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
#adminTap, #brandEmoji { background:none !important; -webkit-text-fill-color:initial !important; color:initial !important; font-size:1.4rem; }
#adminTap.hidden { display:none !important; }
#adminTap { cursor:pointer; user-select:none; -webkit-tap-highlight-color:transparent; }
.header-right { display:flex; align-items:center; gap:8px; }
.badge-class { background: var(--accent-light); color: var(--accent); padding:7px 14px; border-radius:12px; font-weight:800; font-size:1rem; }
.icon-btn { background: var(--accent-light); color: var(--accent); border:none; width:40px; height:40px; border-radius:12px; font-size:1.15rem; cursor:pointer; display:flex; align-items:center; justify-content:center; font-family:inherit; }
.icon-btn:active { transform:scale(0.92); }

.settings-title { font-weight:800; font-size:0.9rem; margin-bottom:10px; display:flex; align-items:center; gap:8px; }
.settings-title:not(:first-child) { margin-top:18px; }
.settings-title::before { content:""; width:4px; height:4px; border-radius:50%; background: var(--accent); box-shadow: 0 0 6px var(--accent); }
.theme-options { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-bottom:8px; }
.theme-btn { padding:10px 4px; border-radius:12px; border:2px solid transparent; background: var(--accent-light); color: var(--text-main); font-weight:700; font-size:0.62rem; cursor:pointer; display:flex; flex-direction:column; align-items:center; gap:4px; font-family:inherit; }
.theme-btn.active { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); }
.theme-btn .emoji { font-size:1.25rem; line-height:1; }
.size-options { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:8px; }
.size-btn { padding:11px; border-radius:12px; border:2px solid var(--border); background: var(--accent-light); color: var(--text-main); font-weight:800; cursor:pointer; font-family:inherit; }
.size-btn[data-size="small"] { font-size:0.85rem; } .size-btn[data-size="normal"] { font-size:1.05rem; } .size-btn[data-size="large"] { font-size:1.25rem; }
.size-btn.active { border-color: var(--accent); }

.custom-picker { display:none; margin:8px 0; padding:12px; border-radius:14px; background: var(--accent-light); border:1px solid var(--border); }
[data-theme="custom"] .custom-picker { display:block; }
.custom-picker label { display:flex; justify-content:space-between; align-items:center; padding:7px 0; font-weight:700; font-size:0.85rem; color: var(--text-main); }
.custom-picker input[type="color"] { width:48px; height:34px; padding:2px; border:2px solid var(--border); border-radius:8px; background:transparent; cursor:pointer; }
.link-btn { background:none; border:none; color: var(--text-muted); font-weight:700; font-size:0.85rem; cursor:pointer; padding:8px; text-decoration:underline; font-family:inherit; }

.open-sub { display:flex; justify-content:space-between; align-items:center; width:100%; padding:14px 16px; margin-bottom:8px; border-radius:14px; background: var(--accent-light); border:1px solid var(--border); color: var(--text-main); font-weight:800; font-size:0.9rem; cursor:pointer; font-family:inherit; text-align:left; }
.open-sub:active { opacity:0.9; }
.open-sub > span:first-child { display:flex; align-items:center; gap:10px; }
.open-sub .ico { font-size:1.15rem; }
.open-sub .srow-arrow { color: var(--text-muted); font-size:1.3rem; font-weight:800; }

.subscreen { position:fixed; inset:0; background: var(--bg); z-index:9999; transform:translateX(100%); transition: transform 0.28s cubic-bezier(0.4,0,0.2,1); overflow-y:auto; padding:0 16px 40px; overscroll-behavior:contain; }
.subscreen.open { transform:translateX(0); }
[data-theme="light"] .subscreen { background:#f1f5fa; }
[data-theme="dark"] .subscreen { background:#10131a; }
[data-theme="cosmic"] .subscreen { background:#05021a; }
[data-theme="ocean"] .subscreen { background:#c7e8f5; }
[data-theme="sunset"] .subscreen { background:#ffd9b0; }
[data-theme="forest"] .subscreen { background:#dff0d0; }
[data-theme="sakura"] .subscreen { background:#ffeaf0; }
[data-theme="custom"] .subscreen { background: var(--cu-bg,#eef2f7); }
.subscreen-header { display:flex; align-items:center; gap:12px; padding:16px 0 14px; position:sticky; top:0; background:inherit; z-index:10; border-bottom:1px solid var(--border); margin:0 -16px; padding-left:16px; padding-right:16px; }
.subscreen-back { background: var(--accent-light); color: var(--accent); border:none; width:40px; height:40px; border-radius:12px; font-size:1.2rem; font-weight:800; cursor:pointer; flex-shrink:0; font-family:inherit; }
.subscreen-back:active { transform:scale(0.92); }
.subscreen-title { font-size:1.1rem; font-weight:800; color: var(--text-main); }
.subscreen-body { padding-top:16px; }

.srow { display:flex; justify-content:space-between; align-items:center; padding:14px 16px; margin-bottom:8px; border-radius:14px; background: var(--card-bg); border:1px solid var(--border); cursor:pointer; }
.srow:active { background: var(--accent-light); }
.srow-label { display:flex; align-items:center; gap:10px; font-weight:800; font-size:0.9rem; color: var(--text-main); }
.srow-label::before { content: attr(data-ico); font-size:1.15rem; }
.srow-value { color: var(--text-muted); font-size:0.82rem; font-weight:800; }
.srow-value.on { color: var(--accent); }

.acc-sub { font-size:0.72rem; font-weight:800; letter-spacing:0.08em; color: var(--text-muted); text-transform:uppercase; margin:14px 0 8px; padding-bottom:6px; border-bottom:1px dashed var(--border); }
.acc-slider { padding:10px 12px; margin-bottom:6px; border-radius:10px; background: var(--accent-light); }
.acc-slider label { display:flex; justify-content:space-between; align-items:center; font-weight:700; font-size:0.82rem; color: var(--text-main); margin-bottom:6px; }
.acc-slider output { color: var(--accent); font-weight:800; }
.acc-slider input[type="range"] { width:100%; height:5px; background: var(--border); border-radius:3px; outline:none; -webkit-appearance:none; }
.acc-slider input[type="range"]::-webkit-slider-thumb { -webkit-appearance:none; width:20px; height:20px; background: linear-gradient(135deg, var(--accent), var(--accent2)); border-radius:50%; cursor:pointer; box-shadow: 0 2px 6px var(--accent-light); }

.tab, .tabs { user-select:none; }
.tabs { display:flex; gap:6px; margin-bottom:14px; overflow-x:auto; padding:4px; scrollbar-width:none; background: var(--card-bg); border-radius:16px; border:1px solid var(--border); box-shadow: var(--shadow); }
.tabs::-webkit-scrollbar { display:none; }
.tab { flex:1; min-width:48px; padding:10px 6px; border-radius:11px; border:none; background:transparent; color: var(--text-muted); font-weight:800; font-size:0.85rem; cursor:pointer; font-family:inherit; display:flex; flex-direction:column; align-items:center; gap:2px; position:relative; }
.tab .tab-day { font-size:0.65rem; font-weight:700; opacity:0.7; }
.tab.active { background: linear-gradient(135deg, var(--accent), var(--accent2)); color:white; box-shadow: 0 3px 10px var(--accent-light); }
.tab.active .tab-day { opacity:0.9; }
.tab.today:not(.active)::after { content:""; position:absolute; bottom:3px; left:50%; transform:translateX(-50%); width:4px; height:4px; border-radius:50%; background: var(--accent); }

.live-banner { border-radius:16px; padding:14px 16px; margin-bottom:14px; display:flex; align-items:center; gap:12px; box-shadow: var(--shadow); border:1px solid var(--border); background: var(--card-bg); }
.live-banner.now, .live-banner.before { background: linear-gradient(135deg, var(--accent-light), var(--card-bg)); border:1.5px solid var(--accent); }
.live-dot { width:10px; height:10px; border-radius:50%; background: var(--accent); flex-shrink:0; animation: pulseDot 1.6s infinite; }
@keyframes pulseDot { 0%,100%{box-shadow:0 0 0 0 var(--accent)} 70%{box-shadow:0 0 0 10px transparent} }
.live-info { flex:1; min-width:0; }
.live-label { font-size:0.7rem; font-weight:800; text-transform:uppercase; letter-spacing:0.08em; color: var(--accent); margin-bottom:3px; }
.live-lesson { font-size:1.02rem; font-weight:800; color: var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.live-time { font-size:0.76rem; color: var(--text-muted); font-weight:700; margin-top:2px; }
.live-timer { color: var(--accent); font-weight:800; }
.progress-bar { height:4px; border-radius:2px; background: var(--border); overflow:hidden; margin-top:7px; }
.progress-fill { height:100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); border-radius:2px; }

.day-block { display:none; }
.day-block.active-day { display:block; }
.day-title { font-size:1.12rem; font-weight:800; color: var(--text-muted); margin-bottom:12px; padding-left:6px; display:flex; justify-content:space-between; align-items:center; }
.day-title.today { color: var(--text-main); }
.today-pill { font-size:0.68rem; background: var(--accent-light); color: var(--accent); padding:5px 11px; border-radius:20px; font-weight:800; text-transform:uppercase; }
.card { background: var(--card-bg); padding:16px 18px; margin-bottom:10px; border-radius:16px; box-shadow: var(--shadow); display:flex; align-items:center; gap:14px; border:1px solid var(--border); }
.card.now { box-shadow: 0 6px 24px var(--accent-light), 0 0 0 1.5px var(--accent); background: linear-gradient(135deg, var(--accent-light), var(--card-bg)); }
.card.next-up { box-shadow: 0 6px 20px var(--orange-soft), 0 0 0 1px var(--orange); }
.num { min-width:40px; height:40px; border-radius:11px; background: var(--num-bg); color: var(--num-color); display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.05rem; flex-shrink:0; box-shadow: var(--num-shadow); }
.card.now .num { background: linear-gradient(135deg, var(--accent), var(--accent2)); color:#fff; }
.left-side { display:flex; flex-direction:column; gap:3px; flex-grow:1; min-width:0; }
.time { font-size:0.8rem; color: var(--text-muted); font-weight:700; }
.lesson { font-size:1.05rem; font-weight:800; color: var(--text-main); word-wrap:break-word; }
.now-pill { font-size:0.6rem; background: var(--accent); color:#fff; padding:3px 8px; border-radius:20px; font-weight:800; text-transform:uppercase; margin-left:auto; flex-shrink:0; }
.info-box { background: var(--card-bg); padding:28px 20px; border-radius:18px; box-shadow: var(--shadow); text-align:center; font-size:1.02rem; font-weight:700; color: var(--text-muted); border:1px solid var(--border); }
.error { background: rgba(224,49,49,0.1); color:#e03131; padding:16px; border-radius:16px; font-weight:700; text-align:center; }
.sheet-link { display:flex; align-items:center; justify-content:center; gap:8px; margin-top:20px; padding:13px 16px; color: var(--accent); text-decoration:none; font-size:0.85rem; font-weight:800; border-radius:14px; border:1.5px solid var(--accent); background: var(--accent-light); }

html.font-small .lesson { font-size:0.9rem; } html.font-small .live-lesson { font-size:0.92rem; }
html.font-large .lesson { font-size:1.18rem; } html.font-large .live-lesson { font-size:1.16rem; } html.font-large .day-title { font-size:1.28rem; }
html.compact .card { padding:11px 14px; margin-bottom:7px; } html.compact .num { min-width:34px; height:34px; font-size:0.9rem; }
html.hide-time .time { display:none; }
html.round-nums .num { border-radius:50% !important; }
html.hide-weekend .tab[data-day="Суббота"] { display:none; }
html.no-live .live-banner { display:none !important; }
html.no-progress .progress-bar { display:none !important; }
html.no-glow .card.now { box-shadow: 0 2px 10px rgba(0,0,0,0.1) !important; }
html.no-today-pill .today-pill { display:none !important; }
html.no-weekday .brand-sub { display:none !important; }

.ap-inner { background: var(--card-bg); border-radius:20px; padding:20px; border:1.5px solid var(--accent); }
.ap-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; font-weight:800; font-size:1.1rem; color: var(--text-main); }
.ap-close { background: var(--accent-light); color: var(--accent); border:none; width:38px; height:38px; border-radius:10px; font-size:1rem; cursor:pointer; font-family:inherit; font-weight:800; }
.ap-visitor { background: var(--accent-light); border:1px solid var(--border); border-radius:14px; padding:14px; margin-bottom:10px; }
.ap-visitor.blocked { border-color:#ef4444; background: rgba(239,68,68,0.08); }
.ap-visitor.is-me { border-color: var(--accent); background: linear-gradient(135deg, var(--accent-light), transparent); box-shadow: 0 4px 16px var(--accent-light); }
.ap-badge { display:inline-block; background: linear-gradient(135deg, var(--accent), var(--accent2)); color:#fff; font-size:0.65rem; font-weight:800; padding:3px 8px; border-radius:8px; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.05em; }
.ap-vid { font-weight:800; color: var(--accent); font-size:0.85rem; word-break:break-all; }
.ap-info { color: var(--text-muted); font-size:0.78rem; margin-top:4px; }
.ap-ago { color:#10b981; font-weight:700; font-size:0.78rem; margin-top:4px; }
.ap-actions { display:flex; gap:6px; margin-top:10px; flex-wrap:wrap; }
.ap-input { flex:1; min-width:120px; padding:9px; border-radius:10px; border:1px solid var(--border); background: var(--bg); color: var(--text-main); font-family:inherit; font-size:0.85rem; }
.ap-btn { padding:9px 14px; border-radius:10px; border:none; background: linear-gradient(135deg, var(--accent), var(--accent2)); color:#fff; font-weight:800; font-size:0.82rem; cursor:pointer; font-family:inherit; }
.ap-btn.danger { background:#ef4444; } .ap-btn.success { background:#10b981; }
.ap-rename { background:transparent; border:1px solid var(--border); width:34px; height:34px; border-radius:10px; font-size:0.9rem; cursor:pointer; color: var(--text-muted); font-family:inherit; }

.admin-tabs { display:flex; gap:4px; margin-bottom:14px; padding:4px; background: var(--accent-light); border-radius:12px; }
.admin-tab { flex:1; padding:10px 8px; background:transparent; border:none; color: var(--text-muted); font-weight:800; font-size:0.82rem; cursor:pointer; font-family:inherit; border-radius:9px; }
.admin-tab.active { background: linear-gradient(135deg, var(--accent), var(--accent2)); color:#fff; }
.admin-pane { display:none; } .admin-pane.active { display:block; }
.admin-block { padding:14px 16px; margin-bottom:12px; border-radius:14px; background: var(--card-bg); border:1px solid var(--border); }
.admin-block-title { font-weight:800; font-size:0.88rem; color: var(--text-main); margin-bottom:10px; }
.admin-textarea { width:100%; box-sizing:border-box; padding:12px; border-radius:10px; border:1px solid var(--border); background: var(--bg); color: var(--text-main); font-family:inherit; font-size:0.9rem; min-height:80px; margin-bottom:10px; }

.acc-emoji { display:flex; flex-wrap:wrap; gap:6px; padding:10px; border-radius:10px; background: var(--accent-light); margin-bottom:10px; }
.emoji-opt { width:44px; height:44px; border-radius:10px; border:2px solid transparent; background: var(--card-bg); font-size:1.3rem; cursor:pointer; display:flex; align-items:center; justify-content:center; }
.emoji-opt.active { border-color: var(--accent); background: var(--accent-light); }
.emoji-opt:active { transform:scale(0.92); }

html.hide-logo #adminTap { display:none !important; }
html.hide-header .header-card { display:none !important; }
html.hide-tabs .tabs { display:none !important; }
html.hide-numbers .num { display:none !important; }
html.hide-sheet-link .sheet-link { display:none !important; }
html.hide-day-title .day-title { display:none !important; }
html.mirror-on body { transform: scaleX(-1); }
html.uppercase-on .lesson, html.uppercase-on .live-lesson { text-transform: uppercase; }
html.bold-all .lesson, html.bold-all .live-lesson, html.bold-all .time, html.bold-all .day-title { font-weight: 900 !important; }
html.italic-on .lesson, html.italic-on .live-lesson { font-style: italic; }
html.underline-on .lesson, html.underline-on .live-lesson { text-decoration: underline; }
html.colorblind-on body { filter: saturate(0) contrast(1.2); }
html.no-radius-all .card, html.no-radius-all .num, html.no-radius-all .header-card, html.no-radius-all .tabs, html.no-radius-all .tab, html.no-radius-all .theme-btn, html.no-radius-all .live-banner { border-radius: 0 !important; }
html.grayscale-all body { filter: grayscale(100%); }
html.reduce-motion *, html.reduce-motion *::before, html.reduce-motion *::after { animation: none !important; transition: none !important; }

html.corners-circle .num { border-radius:50% !important; }
html.corners-circle .theme-btn { border-radius:50% !important; aspect-ratio:1; }
html.corners-pill .card { border-radius: 100px !important; }
html.corners-pill .tab { border-radius: 100px !important; }
html.corners-pill .theme-btn { border-radius: 100px !important; }
html.corners-sharp .card, html.corners-sharp .num, html.corners-sharp .theme-btn, html.corners-sharp .tab, html.corners-sharp .header-card { border-radius: 4px !important; }

/* Переменные для новых слайдеров */
.card { padding: var(--card-pad, 16px) !important; }
.header-card { padding: var(--header-pad, 16px) 20px !important; border-radius: var(--header-radius, 22px) !important; }
.live-banner { padding: var(--live-pad, 14px) 16px !important; }
.lesson { font-size: var(--lesson-size, 1.05rem) !important; }
.time { font-size: var(--time-size, 0.8rem) !important; }
.day-title { font-size: var(--dtitle-size, 1.12rem) !important; }
.live-lesson { font-size: var(--live-size, 1.02rem) !important; }
h2 { font-size: var(--header-size, 1.4rem) !important; }
.num { min-width: var(--num-size, 40px) !important; height: var(--num-size, 40px) !important; }
.icon-btn { width: var(--icon-size, 40px) !important; height: var(--icon-size, 40px) !important; }
.tab { font-size: var(--tab-size, 0.85rem) !important; }
.card { border-radius: var(--card-radius, 16px) !important; margin-bottom: var(--card-gap, 10px) !important; }
.ap-btn, .theme-btn, .size-btn, .open-sub, .srow { border-radius: var(--btn-radius, 12px) !important; }
.container { padding: 0 var(--page-pad, 14px) !important; max-width: var(--page-maxw, 500px) !important; }
.card, .header-card, .tabs, .live-banner { border-width: var(--border-w, 1px) !important; }
.card { box-shadow: 0 calc(var(--card-shadow, 4px) * 1px) calc(var(--card-shadow, 4px) * 4px) rgba(0,0,0,0.08) !important; }
.card.now { box-shadow: 0 6px 24px var(--accent-light), 0 0 0 1.5px var(--accent) !important; }

/* ===== ПАНЕЛЬ НАСТРОЕК — вытекает плавно ===== */




/* ===== ПАНЕЛЬ НАСТРОЕК — мгновенно ===== */




/* ===== ПАНЕЛЬ НАСТРОЕК — струйка из центра ===== */
.settings-panel {
    display: block !important;
    background: var(--card-bg) !important;
    border: 1px solid var(--border) !important;
    border-radius: 16px !important;
    margin-bottom: 0 !important;
    padding: 0 !important;
    box-shadow: none !important;
    overflow: hidden !important;
    max-height: 0 !important;
    opacity: 0 !important;
    transform-origin: top center !important;
    transition:
        max-height 0.14s cubic-bezier(0.22, 1, 0.36, 1),
        opacity 0.1s ease,
        margin-bottom 0.14s cubic-bezier(0.22, 1, 0.36, 1),
        padding 0.14s cubic-bezier(0.22, 1, 0.36, 1),
        box-shadow 0.14s ease !important;
}
.settings-panel.open {
    max-height: 2000px !important;
    opacity: 1 !important;
    margin-bottom: 14px !important;
    padding: 16px 18px !important;
    box-shadow: var(--shadow) !important;
}
.settings-inner {
    display: contents !important;
}
/* Тонкая струйка сверху */
.settings-panel::before {
    content: "" !important;
    position: absolute !important;
    top: 0 !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    width: 0 !important;
    height: 2px !important;
    background: linear-gradient(90deg, transparent, var(--accent), transparent) !important;
    transition: width 0.14s cubic-bezier(0.22, 1, 0.36, 1) !important;
    pointer-events: none !important;
}
.settings-panel.open::before {
    width: 100% !important;
}
.settings-panel {
    position: relative !important;
}
</style>
</head>
<body data-changed-at="{changed_at}">
<div id="particles"></div>
<div class="container">
<div class="header-card">
    <h2><span id="adminTap">📅</span> <span>Расписание</span></h2>
<script>(function(){var e=localStorage.getItem('rs_emoji');if(e){var t=document.getElementById('adminTap');if(t)t.textContent=e;}})();</script>
    <div class="header-right">
        <div class="badge-class">8Г</div>
        <button class="icon-btn" onclick="toggleSettings()">⚙️</button>
    </div>
</div>

<div class="settings-panel" id="settingsPanel"><div class="settings-inner">
    <div class="settings-title">🎨 Тема</div>
    <div class="theme-options">
        <button class="theme-btn" data-theme-btn="light" onclick="setTheme('light')"><span class="emoji">☀️</span>Светлая</button>
        <button class="theme-btn" data-theme-btn="dark" onclick="setTheme('dark')"><span class="emoji">🌙</span>Тёмная</button>
        <button class="theme-btn" data-theme-btn="cosmic" onclick="setTheme('cosmic')"><span class="emoji">🌌</span>Космос</button>
        <button class="theme-btn" data-theme-btn="ocean" onclick="setTheme('ocean')"><span class="emoji">🌊</span>Океан</button>
        <button class="theme-btn" data-theme-btn="sunset" onclick="setTheme('sunset')"><span class="emoji">🌅</span>Закат</button>
        <button class="theme-btn" data-theme-btn="forest" onclick="setTheme('forest')"><span class="emoji">🌿</span>Лес</button>
        <button class="theme-btn" data-theme-btn="sakura" onclick="setTheme('sakura')"><span class="emoji">🌸</span>Сакура</button>
        <button class="theme-btn" data-theme-btn="custom" onclick="setTheme('custom')"><span class="emoji">🎨</span>Кастом</button>
    </div>
    <div class="custom-picker">
        <label>Основной <input type="color" id="cuAccent" value="#6366f1" onchange="applyCustom()"></label>
        <label>Второй <input type="color" id="cuAccent2" value="#a855f7" onchange="applyCustom()"></label>
        <label>Фон <input type="color" id="cuBg" value="#eef2f7" onchange="applyCustom()"></label>
        <label>Карточки <input type="color" id="cuCard" value="#ffffff" onchange="applyCustom()"></label>
        <label>Текст <input type="color" id="cuText" value="#0f172a" onchange="applyCustom()"></label>
        <label>Доп. текст <input type="color" id="cuMuted" value="#64748b" onchange="applyCustom()"></label>
        <button onclick="resetCustom()" class="link-btn" style="width:100%;margin-top:8px;">🔄 Сбросить</button>
    </div>

    <div class="settings-title">🔤 Размер текста</div>
    <div class="size-options">
        <button class="size-btn" data-size="small" onclick="setSize('small')">A</button>
        <button class="size-btn" data-size="normal" onclick="setSize('normal')">A</button>
        <button class="size-btn" data-size="large" onclick="setSize('large')">A</button>
    </div>

    <div class="settings-title">⚙️ Разделы</div>
    <button class="open-sub" onclick="openSub('interface')"><span><span class="ico">🎨</span> Интерфейс</span><span class="srow-arrow">›</span></button>
    <button class="open-sub" onclick="openSub('advanced')"><span><span class="ico">🔧</span> Дополнительно</span><span class="srow-arrow">›</span></button>
    <button class="open-sub" onclick="openSub('app')"><span><span class="ico">📱</span> Приложение</span><span class="srow-arrow">›</span></button>
</div></div>

{live_banner}
{tabs}
{content}

<a class="sheet-link" href="{sheet_url}" target="_blank" rel="noopener">📊 Открыть таблицу в Google Sheets</a>
</div>

<div class="subscreen" id="sub-interface">
    <div class="subscreen-header"><button class="subscreen-back" onclick="closeSub('interface')">←</button><div class="subscreen-title">🎨 Интерфейс</div></div>
    <div class="subscreen-body">
        <div class="srow" onclick="toggleOpt('particles')"><span class="srow-label" data-ico="✨">Частицы фона</span><span class="srow-value" id="val-particles">вкл</span></div>
        <div class="srow" onclick="toggleOpt('round_nums')"><span class="srow-label" data-ico="🔢">Круглые номера</span><span class="srow-value" id="val-round_nums">выкл</span></div>
        <div class="srow" onclick="toggleOpt('compact')"><span class="srow-label" data-ico="📏">Компактный режим</span><span class="srow-value" id="val-compact">выкл</span></div>
        <div class="srow" onclick="toggleOpt('show_time')"><span class="srow-label" data-ico="⏱️">Показывать время</span><span class="srow-value" id="val-show_time">вкл</span></div>
        <div class="srow" onclick="toggleOpt('live_banner')"><span class="srow-label" data-ico="📢">Баннер «Сейчас идёт»</span><span class="srow-value" id="val-live_banner">вкл</span></div>
        <div class="srow" onclick="toggleOpt('progress_bar')"><span class="srow-label" data-ico="📊">Прогресс-бар урока</span><span class="srow-value" id="val-progress_bar">вкл</span></div>
        <div class="srow" onclick="toggleOpt('glow')"><span class="srow-label" data-ico="💡">Свечение акцента</span><span class="srow-value" id="val-glow">вкл</span></div>
        <div class="srow" onclick="toggleOpt('big_text')"><span class="srow-label" data-ico="🔠">Крупный шрифт</span><span class="srow-value" id="val-big_text">выкл</span></div>
        <div class="srow" onclick="toggleOpt('show_weekday')"><span class="srow-label" data-ico="📅">День недели в шапке</span><span class="srow-value" id="val-show_weekday">вкл</span></div>
        <div class="srow" onclick="toggleOpt('today_pill')"><span class="srow-label" data-ico="🏷️">Плашка «Сегодня»</span><span class="srow-value" id="val-today_pill">вкл</span></div>

        <div class="acc-sub">📅 Иконка в шапке</div>
        <div class="acc-emoji">
            <button class="emoji-opt" data-em="📅" onclick="setEmoji('📅')">📅</button>
            <button class="emoji-opt" data-em="📆" onclick="setEmoji('📆')">📆</button>
            <button class="emoji-opt" data-em="🗓️" onclick="setEmoji('🗓️')">🗓️</button>
            <button class="emoji-opt" data-em="⏰" onclick="setEmoji('⏰')">⏰</button>
            <button class="emoji-opt" data-em="📚" onclick="setEmoji('📚')">📚</button>
            <button class="emoji-opt" data-em="🎓" onclick="setEmoji('🎓')">🎓</button>
            <button class="emoji-opt" data-em="🏫" onclick="setEmoji('🏫')">🏫</button>
            <button class="emoji-opt" data-em="✏️" onclick="setEmoji('✏️')">✏️</button>
            <button class="emoji-opt" data-em="⭐" onclick="setEmoji('⭐')">⭐</button>
            <button class="emoji-opt" data-em="🔥" onclick="setEmoji('🔥')">🔥</button>
            <button class="emoji-opt" data-em="💜" onclick="setEmoji('💜')">💜</button>
            <button class="emoji-opt" data-em="⚡" onclick="setEmoji('⚡')">⚡</button>
            <button class="emoji-opt" data-em="🌟" onclick="setEmoji('🌟')">🌟</button>
            <button class="emoji-opt" data-em="🎒" onclick="setEmoji('🎒')">🎒</button>
            <button class="emoji-opt" data-em="📝" onclick="setEmoji('📝')">📝</button>
        </div>
    </div>
</div>

<div class="subscreen" id="sub-advanced">
    <div class="subscreen-header"><button class="subscreen-back" onclick="closeSub('advanced')">←</button><div class="subscreen-title">🔧 Дополнительно</div></div>
    <div class="subscreen-body">
        <div class="acc-sub">📐 Размеры</div>
        <div class="acc-slider"><label>Шрифт уроков <output id="o-lesson_size">1.05</output>rem</label><input type="range" min="0.85" max="1.35" step="0.05" id="s-lesson_size" oninput="setVar('lesson_size',this.value,'rem')"></div>
        <div class="acc-slider"><label>Размер номеров <output id="o-num_size">40</output>px</label><input type="range" min="30" max="56" step="2" id="s-num_size" oninput="setVar('num_size',this.value,'px')"></div>
        <div class="acc-slider"><label>Радиус карточек <output id="o-card_radius">16</output>px</label><input type="range" min="0" max="30" step="2" id="s-card_radius" oninput="setVar('card_radius',this.value,'px')"></div>
        <div class="acc-slider"><label>Промежутки карточек <output id="o-card_gap">10</output>px</label><input type="range" min="4" max="24" step="2" id="s-card_gap" oninput="setVar('card_gap',this.value,'px')"></div>
        <div class="acc-sub">🎨 Цвета</div>
        <div class="acc-slider"><label>Насыщенность <output id="o-saturate">100</output>%</label><input type="range" min="0" max="200" step="5" id="s-saturate" oninput="setFilter('saturate',this.value)"></div>
        <div class="acc-slider"><label>Яркость <output id="o-brightness">100</output>%</label><input type="range" min="60" max="140" step="5" id="s-brightness" oninput="setFilter('brightness',this.value)"></div>
        <div class="acc-slider"><label>Оттенок <output id="o-hue">0</output>°</label><input type="range" min="-180" max="180" step="5" id="s-hue" oninput="setFilter('hue-rotate',this.value,'deg')"></div>
        <div class="acc-sub">⚡ Производительность</div>
        <div class="acc-sub">📐 Размеры и шрифты</div>
        <div class="acc-slider"><label>Шрифт урока <output id="o-lesson_size">1.05</output>rem</label><input type="range" min="0.7" max="1.6" step="0.05" id="s-lesson_size" oninput="setVar('lesson_size',this.value,'rem')"></div>
        <div class="acc-slider"><label>Шрифт времени <output id="o-time_size">0.8</output>rem</label><input type="range" min="0.6" max="1.2" step="0.05" id="s-time_size" oninput="setVar('time_size',this.value,'rem')"></div>
        <div class="acc-slider"><label>Шрифт дня <output id="o-dtitle_size">1.12</output>rem</label><input type="range" min="0.8" max="1.6" step="0.05" id="s-dtitle_size" oninput="setVar('dtitle_size',this.value,'rem')"></div>
        <div class="acc-slider"><label>Шрифт баннера <output id="o-live_size">1.02</output>rem</label><input type="range" min="0.8" max="1.5" step="0.05" id="s-live_size" oninput="setVar('live_size',this.value,'rem')"></div>
        <div class="acc-slider"><label>Шрифт шапки <output id="o-header_size">1.4</output>rem</label><input type="range" min="1" max="2" step="0.05" id="s-header_size" oninput="setVar('header_size',this.value,'rem')"></div>
        <div class="acc-slider"><label>Размер номера <output id="o-num_size">40</output>px</label><input type="range" min="24" max="64" step="2" id="s-num_size" oninput="setVar('num_size',this.value,'px')"></div>
        <div class="acc-slider"><label>Размер значков <output id="o-icon_size">40</output>px</label><input type="range" min="30" max="56" step="2" id="s-icon_size" oninput="setVar('icon_size',this.value,'px')"></div>
        <div class="acc-slider"><label>Размер таба <output id="o-tab_size">0.85</output>rem</label><input type="range" min="0.7" max="1.2" step="0.05" id="s-tab_size" oninput="setVar('tab_size',this.value,'rem')"></div>
        <div class="acc-slider"><label>Радиус карточек <output id="o-card_radius">16</output>px</label><input type="range" min="0" max="40" step="2" id="s-card_radius" oninput="setVar('card_radius',this.value,'px')"></div>
        <div class="acc-slider"><label>Радиус кнопок <output id="o-btn_radius">12</output>px</label><input type="range" min="0" max="40" step="2" id="s-btn_radius" oninput="setVar('btn_radius',this.value,'px')"></div>
        <div class="acc-slider"><label>Радиус шапки <output id="o-header_radius">22</output>px</label><input type="range" min="0" max="40" step="2" id="s-header_radius" oninput="setVar('header_radius',this.value,'px')"></div>
        <div class="acc-slider"><label>Промежутки карточек <output id="o-card_gap">10</output>px</label><input type="range" min="0" max="30" step="2" id="s-card_gap" oninput="setVar('card_gap',this.value,'px')"></div>
        <div class="acc-slider"><label>Отступ страницы <output id="o-page_pad">14</output>px</label><input type="range" min="0" max="40" step="2" id="s-page_pad" oninput="setVar('page_pad',this.value,'px')"></div>
        <div class="acc-slider"><label>Толщина границ <output id="o-border_w">1</output>px</label><input type="range" min="0" max="4" step="1" id="s-border_w" oninput="setVar('border_w',this.value,'px')"></div>
        <div class="acc-slider"><label>Мин. ширина страницы <output id="o-page_maxw">500</output>px</label><input type="range" min="300" max="800" step="10" id="s-page_maxw" oninput="setVar('page_maxw',this.value,'px')"></div>

        <div class="acc-sub">🎨 Цвета и эффекты</div>
        <div class="acc-slider"><label>Насыщенность <output id="o-saturate">100</output>%</label><input type="range" min="0" max="200" step="5" id="s-saturate" oninput="setFilter('saturate',this.value)"></div>
        <div class="acc-slider"><label>Яркость <output id="o-brightness">100</output>%</label><input type="range" min="50" max="150" step="5" id="s-brightness" oninput="setFilter('brightness',this.value)"></div>
        <div class="acc-slider"><label>Контраст <output id="o-contrast">100</output>%</label><input type="range" min="50" max="150" step="5" id="s-contrast" oninput="setFilter('contrast',this.value)"></div>
        <div class="acc-slider"><label>Оттенок <output id="o-hue">0</output>°</label><input type="range" min="-180" max="180" step="5" id="s-hue" oninput="setFilter('hue-rotate',this.value,'deg')"></div>
        <div class="acc-slider"><label>Сепия <output id="o-sepia">0</output>%</label><input type="range" min="0" max="100" step="5" id="s-sepia" oninput="setFilter('sepia',this.value)"></div>
        <div class="acc-slider"><label>Инверсия <output id="o-invert">0</output>%</label><input type="range" min="0" max="100" step="5" id="s-invert" oninput="setFilter('invert',this.value)"></div>
        <div class="acc-slider"><label>Оттенки серого <output id="o-grayscale">0</output>%</label><input type="range" min="0" max="100" step="5" id="s-grayscale" oninput="setFilter('grayscale',this.value)"></div>
        <div class="acc-slider"><label>Прозрачность фона <output id="o-bg_opacity">100</output>%</label><input type="range" min="20" max="100" step="5" id="s-bg_opacity" oninput="setBgOpacity(this.value)"></div>
        <div class="acc-slider"><label>Прозрачность карточек <output id="o-card_opacity">100</output>%</label><input type="range" min="30" max="100" step="5" id="s-card_opacity" oninput="setCardOpacity(this.value)"></div>
        <div class="acc-slider"><label>Размытие карточек <output id="o-card_blur">0</output>px</label><input type="range" min="0" max="20" step="1" id="s-card_blur" oninput="setCardBlur(this.value)"></div>
        <div class="acc-slider"><label>Тень карточек <output id="o-card_shadow">4</output></label><input type="range" min="0" max="30" step="1" id="s-card_shadow" oninput="setCardShadow(this.value)"></div>
        <div class="acc-slider"><label>Свечение акцента <output id="o-glow_pow">4</output></label><input type="range" min="0" max="30" step="1" id="s-glow_pow" oninput="setGlowPow(this.value)"></div>

        <div class="acc-sub">⚡ Анимации</div>
        <div class="acc-slider"><label>Общая скорость <output id="o-anim_speed">1</output>x</label><input type="range" min="0" max="3" step="0.1" id="s-anim_speed" oninput="setAnimSpeed(this.value)"></div>
        <div class="acc-slider"><label>Скорость переходов <output id="o-transition">0.15</output>с</label><input type="range" min="0" max="1" step="0.05" id="s-transition" oninput="setTransition(this.value)"></div>
        <div class="acc-slider"><label>Скорость частиц <output id="o-particle_speed">1</output>x</label><input type="range" min="0.3" max="3" step="0.1" id="s-particle_speed" oninput="setParticleSpeed(this.value)"></div>

        <div class="acc-sub">✨ Частицы</div>
        <div class="acc-slider"><label>Количество <output id="o-particle_count">18</output></label><input type="range" min="0" max="60" step="1" id="s-particle_count" oninput="setParticleCount(this.value)"></div>
        <div class="acc-slider"><label>Размер <output id="o-particle_size">1</output>x</label><input type="range" min="0.3" max="3" step="0.1" id="s-particle_size" oninput="setParticleSize(this.value)"></div>
        <div class="acc-slider"><label>Прозрачность <output id="o-particle_opacity">85</output>%</label><input type="range" min="10" max="100" step="5" id="s-particle_opacity" oninput="setParticleOpacity(this.value)"></div>

        <div class="acc-sub">📐 Отступы внутри</div>
        <div class="acc-slider"><label>Padding карточки <output id="o-card_pad">16</output>px</label><input type="range" min="6" max="30" step="2" id="s-card_pad" oninput="setVar('card_pad',this.value,'px')"></div>
        <div class="acc-slider"><label>Padding шапки <output id="o-header_pad">16</output>px</label><input type="range" min="8" max="30" step="2" id="s-header_pad" oninput="setVar('header_pad',this.value,'px')"></div>
        <div class="acc-slider"><label>Отступ баннера <output id="o-live_pad">14</output>px</label><input type="range" min="6" max="26" step="2" id="s-live_pad" oninput="setVar('live_pad',this.value,'px')"></div>

        <div class="acc-sub">🔲 Форма углов</div>
        <div class="srow" onclick="setCorners('rounded')"><span class="srow-label" data-ico="⬜">Мягкие</span><span class="srow-value" id="val-c-round"></span></div>
        <div class="srow" onclick="setCorners('sharp')"><span class="srow-label" data-ico="🔲">Острые</span><span class="srow-value" id="val-c-sharp"></span></div>
        <div class="srow" onclick="setCorners('circle')"><span class="srow-label" data-ico="⚪">Круглые</span><span class="srow-value" id="val-c-circle"></span></div>
        <div class="srow" onclick="setCorners('pill')"><span class="srow-label" data-ico="💊">Таблетки</span><span class="srow-value" id="val-c-pill"></span></div>

        <div class="acc-sub">📱 Показ элементов</div>
        <div class="srow" onclick="toggleOpt('show_logo')"><span class="srow-label" data-ico="📅">Иконка в шапке</span><span class="srow-value" id="val-show_logo">вкл</span></div>
        <div class="srow" onclick="toggleOpt('show_header')"><span class="srow-label" data-ico="📋">Шапка</span><span class="srow-value" id="val-show_header">вкл</span></div>
        <div class="srow" onclick="toggleOpt('show_tabs')"><span class="srow-label" data-ico="📑">Табы дней</span><span class="srow-value" id="val-show_tabs">вкл</span></div>
        <div class="srow" onclick="toggleOpt('show_numbers')"><span class="srow-label" data-ico="🔢">Номера уроков</span><span class="srow-value" id="val-show_numbers">вкл</span></div>
        <div class="srow" onclick="toggleOpt('show_classroom')"><span class="srow-label" data-ico="🚪">Показывать кабинет</span><span class="srow-value" id="val-show_classroom">вкл</span></div>
        <div class="srow" onclick="toggleOpt('show_sheet_link')"><span class="srow-label" data-ico="🔗">Ссылка на таблицу</span><span class="srow-value" id="val-show_sheet_link">вкл</span></div>
        <div class="srow" onclick="toggleOpt('show_day_title')"><span class="srow-label" data-ico="📆">Заголовок дня</span><span class="srow-value" id="val-show_day_title">вкл</span></div>

        <div class="acc-sub">🎛 Прочее</div>
        <div class="srow" onclick="toggleOpt('mirror')"><span class="srow-label" data-ico="🔁">Зеркалирование</span><span class="srow-value" id="val-mirror">выкл</span></div>
        <div class="srow" onclick="toggleOpt('uppercase')"><span class="srow-label" data-ico="🅰️">ВЕРХНИЙ РЕГИСТР</span><span class="srow-value" id="val-uppercase">выкл</span></div>
        <div class="srow" onclick="toggleOpt('bold_all')"><span class="srow-label" data-ico="🅱️">Жирный текст</span><span class="srow-value" id="val-bold_all">выкл</span></div>
        <div class="srow" onclick="toggleOpt('italic')"><span class="srow-label" data-ico="𝘐">Курсив</span><span class="srow-value" id="val-italic">выкл</span></div>
        <div class="srow" onclick="toggleOpt('underline')"><span class="srow-label" data-ico="〰️">Подчёркивание</span><span class="srow-value" id="val-underline">выкл</span></div>
        <div class="srow" onclick="toggleOpt('colorblind')"><span class="srow-label" data-ico="🎨">Дальтонизм-режим</span><span class="srow-value" id="val-colorblind">выкл</span></div>
        <div class="srow" onclick="toggleOpt('no_radius')"><span class="srow-label" data-ico="⬛">Прямые углы везде</span><span class="srow-value" id="val-no_radius">выкл</span></div>
        <div class="srow" onclick="toggleOpt('grayscale_all')"><span class="srow-label" data-ico="⚫">Ч/Б режим</span><span class="srow-value" id="val-grayscale_all">выкл</span></div>
        <div class="srow" onclick="toggleOpt('reduce_motion')"><span class="srow-label" data-ico="🛑">Уменьшить движение</span><span class="srow-value" id="val-reduce_motion">выкл</span></div>

        <div class="acc-sub">🔬 Тонкая настройка (вставь свой CSS)</div>
        <div class="acc-slider"><label>Свой CSS-код</label><textarea id="customCss" placeholder=".card { color: red; }" style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--border);background:var(--bg);color:var(--text-main);font-family:monospace;font-size:0.8rem;min-height:80px;margin-top:6px;resize:vertical;" onchange="applyCustomCss(this.value)"></textarea></div>

        <button class="link-btn" style="width:100%;padding:14px;margin-top:14px;" onclick="resetAllOpts()">🔄 Сбросить все настройки</button>
    </div>
</div>

<div class="subscreen" id="sub-app">
    <div class="subscreen-header"><button class="subscreen-back" onclick="closeSub('app')">←</button><div class="subscreen-title">📱 Приложение</div></div>
    <div class="subscreen-body"><div id="installSection"></div></div>
</div>

<div class="subscreen" id="sub-admin">
    <div class="subscreen-header"><button class="subscreen-back" onclick="closeSub('admin')">←</button><div class="subscreen-title">👑 Админ</div></div>
    <div class="subscreen-body">
        <div class="admin-tabs">
            <button class="admin-tab active" data-atab="visitors" onclick="switchAdminTab('visitors')">👥</button>
            <button class="admin-tab" data-atab="broadcast" onclick="switchAdminTab('broadcast')">📢</button>
            <button class="admin-tab" data-atab="blocked" onclick="switchAdminTab('blocked')">🚫</button>
        </div>
        <div class="admin-pane active" id="atab-visitors"><div id="apList">Загрузка…</div></div>
        <div class="admin-pane" id="atab-broadcast">
            <div class="admin-block">
                <div class="admin-block-title">📢 Отправить всем</div>
                <textarea class="admin-textarea" id="broadcastText" placeholder="Текст..."></textarea>
                <button class="ap-btn" onclick="sendBroadcast()">Отправить всем</button>
            </div>
        </div>
        <div class="admin-pane" id="atab-blocked"><div id="blockedList">Загрузка…</div></div>
    </div>
</div>

<script>
var THEME_COLORS = {light:'#f0f4f8',dark:'#0f1115',cosmic:'#05021a',ocean:'#c7e8f5',sunset:'#ffd9b0',forest:'#d4e8c8',sakura:'#ffd6e4',custom:'#eef2f7'};

function _optIsOn(key){
    var cur = localStorage.getItem('rs_opt_' + key);
    if (['particles','show_time','live_banner','progress_bar','glow','show_weekday','today_pill','show_logo','show_header','show_tabs','show_numbers','show_classroom','show_sheet_link','show_day_title'].indexOf(key) >= 0) return cur !== '0';
    return cur === '1';
}

function applyOpt(key, on){
    var h = document.documentElement;
    if (key === 'particles') { var c=document.getElementById('particles'); if(c){ if(on) spawnParticles(h.getAttribute('data-theme')); else c.innerHTML=''; } }
    else if (key === 'round_nums') h.classList.toggle('round-nums', on);
    else if (key === 'compact') h.classList.toggle('compact', on);
    else if (key === 'big_text') h.classList.toggle('font-large', on);
    else if (key === 'hide_weekend') h.classList.toggle('hide-weekend', on);
    else if (key === 'show_time') h.classList.toggle('hide-time', !on);
    else if (key === 'live_banner') h.classList.toggle('no-live', !on);
    else if (key === 'progress_bar') h.classList.toggle('no-progress', !on);
    else if (key === 'glow') h.classList.toggle('no-glow', !on);
    else if (key === 'today_pill') h.classList.toggle('no-today-pill', !on);
    else if (key === 'show_weekday') h.classList.toggle('no-weekday', !on);
    else if (key === 'show_logo') h.classList.toggle('hide-logo', !on);
    else if (key === 'show_header') h.classList.toggle('hide-header', !on);
    else if (key === 'show_tabs') h.classList.toggle('hide-tabs', !on);
    else if (key === 'show_numbers') h.classList.toggle('hide-numbers', !on);
    else if (key === 'show_sheet_link') h.classList.toggle('hide-sheet-link', !on);
    else if (key === 'show_day_title') h.classList.toggle('hide-day-title', !on);
    else if (key === 'mirror') h.classList.toggle('mirror-on', on);
    else if (key === 'uppercase') h.classList.toggle('uppercase-on', on);
    else if (key === 'bold_all') h.classList.toggle('bold-all', on);
    else if (key === 'italic') h.classList.toggle('italic-on', on);
    else if (key === 'underline') h.classList.toggle('underline-on', on);
    else if (key === 'colorblind') h.classList.toggle('colorblind-on', on);
    else if (key === 'no_radius') h.classList.toggle('no-radius-all', on);
    else if (key === 'grayscale_all') h.classList.toggle('grayscale-all', on);
    else if (key === 'reduce_motion') h.classList.toggle('reduce-motion', on);
    else if (key === 'show_classroom') h.classList.toggle('hide-classroom', !on);
}

function toggleOpt(key){
    var on = _optIsOn(key);
    localStorage.setItem('rs_opt_' + key, !on ? '1' : '0');
    applyOpt(key, !on);
    updateOptUI();
}

function updateOptUI(){
    document.querySelectorAll('.srow-value').forEach(function(el){
        var key = el.id.replace('val-','');
        var on = _optIsOn(key);
        el.textContent = on ? 'вкл' : 'выкл';
        el.className = 'srow-value' + (on ? ' on' : '');
    });
}

function setVar(name, val, unit){
    document.documentElement.style.setProperty('--u-' + name, val + (unit||''));
    var o = document.getElementById('o-' + name); if (o) o.textContent = val;
    localStorage.setItem('rs_u_' + name, val);
    applyVars();
}
function applyVars(){
    var h = document.documentElement, v;
    if ((v = localStorage.getItem('rs_u_lesson_size'))) h.style.setProperty('--lesson-size', v + 'rem');
    if ((v = localStorage.getItem('rs_u_num_size'))) h.style.setProperty('--num-size', v + 'px');
    if ((v = localStorage.getItem('rs_u_card_radius'))) h.style.setProperty('--card-radius', v + 'px');
    if ((v = localStorage.getItem('rs_u_card_gap'))) h.style.setProperty('--card-gap', v + 'px');
    if ((v = localStorage.getItem('rs_u_num_size'))) {
        document.querySelectorAll('.num').forEach(function(n){ n.style.minWidth = v + 'px'; n.style.height = v + 'px'; });
    }
    if ((v = localStorage.getItem('rs_u_card_radius'))) {
        document.querySelectorAll('.card').forEach(function(c){ c.style.borderRadius = v + 'px'; });
    }
    if ((v = localStorage.getItem('rs_u_card_gap'))) {
        document.querySelectorAll('.card').forEach(function(c){ c.style.marginBottom = v + 'px'; });
    }
    if ((v = localStorage.getItem('rs_u_lesson_size'))) {
        document.querySelectorAll('.lesson').forEach(function(l){ l.style.fontSize = v + 'rem'; });
    }
}
function setFilter(name, val, unit){
    var o = document.getElementById('o-' + name.replace('-rotate','')); if (o) o.textContent = val;
    localStorage.setItem('rs_f_' + name, val);
    applyFilters();
}
function applyFilters(){
    var h = document.documentElement;
    var s = localStorage.getItem('rs_f_saturate') || '100';
    var b = localStorage.getItem('rs_f_brightness') || '100';
    var hu = localStorage.getItem('rs_f_hue-rotate') || '0';
    h.style.setProperty('--global-filter', 'saturate('+s+'%) brightness('+b+'%) hue-rotate('+hu+'deg)');
    document.querySelectorAll('.card, .num, .lesson, .header-card').forEach(function(el){
        el.style.filter = 'saturate('+s+'%) brightness('+b+'%) hue-rotate('+hu+'deg)';
    });
}
function setParticleCount(v){ localStorage.setItem('rs_particle_count', v); var o=document.getElementById('o-particle_count'); if(o)o.textContent=v; spawnParticles(document.documentElement.getAttribute('data-theme')); }
function setAnimSpeed(v){ localStorage.setItem('rs_anim_speed', v); var o=document.getElementById('o-anim_speed'); if(o)o.textContent=v; }
function resetAllOpts(){ if(!confirm('Сбросить все настройки?'))return; Object.keys(localStorage).forEach(function(k){ if(k.indexOf('rs_opt_')===0||k.indexOf('rs_u_')===0||k.indexOf('rs_f_')===0) localStorage.removeItem(k); }); location.reload(); }

function hex2rgb(h){ h=h.replace('#',''); if(h.length===3)h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2]; return parseInt(h.substr(0,2),16)+','+parseInt(h.substr(2,2),16)+','+parseInt(h.substr(4,2),16); }
function applyCustom(){
    var map = {cuAccent:'rs_cu_accent',cuAccent2:'rs_cu_accent2',cuBg:'rs_cu_bg',cuCard:'rs_cu_card',cuText:'rs_cu_text',cuMuted:'rs_cu_muted'};
    for (var elId in map) { var el=document.getElementById(elId); if(el) localStorage.setItem(map[elId], el.value); }
    var h = document.documentElement;
    var c1 = localStorage.getItem('rs_cu_accent') || '#6366f1';
    var c2 = localStorage.getItem('rs_cu_accent2') || '#a855f7';
    var bg = localStorage.getItem('rs_cu_bg') || '#eef2f7';
    var card = localStorage.getItem('rs_cu_card') || '#ffffff';
    var txt = localStorage.getItem('rs_cu_text') || '#0f172a';
    var muted = localStorage.getItem('rs_cu_muted') || '#64748b';
    h.style.setProperty('--cu-accent', c1);
    h.style.setProperty('--cu-accent2', c2);
    h.style.setProperty('--cu-bg', bg);
    h.style.setProperty('--cu-card', card);
    h.style.setProperty('--cu-text', txt);
    h.style.setProperty('--cu-muted', muted);
    h.style.setProperty('--cu-accent-light', 'rgba('+hex2rgb(c1)+', 0.12)');
}
function resetCustom(){ var def={cuAccent:'#6366f1',cuAccent2:'#a855f7',cuBg:'#eef2f7',cuCard:'#ffffff',cuText:'#0f172a',cuMuted:'#64748b'}; for(var k in def){ var el=document.getElementById(k); if(el) el.value=def[k]; } applyCustom(); }
function initCustom(){ var map={cuAccent:'rs_cu_accent',cuAccent2:'rs_cu_accent2',cuBg:'rs_cu_bg',cuCard:'rs_cu_card',cuText:'rs_cu_text',cuMuted:'rs_cu_muted'}; for(var elId in map){ var v=localStorage.getItem(map[elId]); var el=document.getElementById(elId); if(el&&v) el.value=v; } applyCustom(); }

function setTheme(t){
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('rs_theme', t);
    document.querySelectorAll('[data-theme-btn]').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-theme-btn')===t); });
    var meta = document.getElementById('tcMeta');
    if (meta) meta.setAttribute('content', THEME_COLORS[t] || '#f0f4f8');
    if (t === 'custom') applyCustom();
    spawnParticles(t);
}
function setSize(s){
    document.documentElement.classList.remove('font-small','font-large');
    if (s === 'small') document.documentElement.classList.add('font-small');
    if (s === 'large') document.documentElement.classList.add('font-large');
    localStorage.setItem('rs_size', s);
    document.querySelectorAll('[data-size]').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-size')===s); });
}
function toggleSettings(){ document.getElementById('settingsPanel').classList.toggle('open'); }
function showDay(day){
    document.querySelectorAll('.day-block').forEach(function(el){ el.classList.remove('active-day'); });
    var t = document.getElementById('block-' + day);
    if (t) t.classList.add('active-day');
    document.querySelectorAll('.tab').forEach(function(x){ x.classList.toggle('active', x.getAttribute('data-day')===day); });
}
function openSub(name){
    if (name === 'admin' && localStorage.getItem('rs_admin') !== '1') return;
    document.querySelectorAll('.subscreen').forEach(function(s){ if (s.id !== 'sub-' + name) s.classList.remove('open'); });
    var el = document.getElementById('sub-' + name);
    if (!el) return;
    void el.offsetWidth;
    el.classList.add('open');
    document.body.style.overflow = 'hidden';
    if (name === 'admin') { if (typeof loadVisitors === 'function') setTimeout(loadVisitors, 100); }
    if (name === 'app') { if (typeof renderInstallSection === 'function') setTimeout(renderInstallSection, 50); }
}
function closeSub(name){
    var el = document.getElementById('sub-' + name);
    if (!el) return;
    el.classList.remove('open');
    document.body.style.overflow = '';
}

function spawnParticles(theme){
    var c = document.getElementById('particles');
    if (!c) return;
    c.innerHTML = '';
    if (!_optIsOn('particles')) return;
    if (window.innerWidth < 320) return;
    var base = { cosmic:{chars:['✦','✧','·','+'],colors:['#fff','#b794f6','#7cf5c0','#e0d4ff'],dur:[15,28]}, sakura:{chars:['🌸','🌸','❀','✿'],colors:['#ec4899','#f9a8d4','#fbcfe8'],dur:[11,20]}, forest:{chars:['🍃','🌿'],colors:['#059669','#16a34a','#84cc16'],dur:[13,24]}, ocean:{chars:['●','○','·'],colors:['rgba(34,211,238,0.75)','rgba(8,145,178,0.65)'],dur:[11,20]}, sunset:{chars:['✨','·','✦'],colors:['#f97316','#ec4899','#fbbf24'],dur:[13,22]} }[theme];
    if (!base) return;
    var n = parseInt(localStorage.getItem('rs_particle_count') || '18', 10);
    if (window.innerWidth < 820) n = Math.max(4, Math.round(n * 0.6));
    var frag = document.createDocumentFragment();
    for (var i=0;i<n;i++){
        var el = document.createElement('span');
        el.className = 'particle';
        el.textContent = base.chars[Math.floor(Math.random()*base.chars.length)];
        el.style.left = (Math.random()*100)+'%';
        var sz = 10 + Math.random()*8;
        el.style.fontSize = sz+'px';
        el.style.color = base.colors[Math.floor(Math.random()*base.colors.length)];
        var d = base.dur[0]+Math.random()*(base.dur[1]-base.dur[0]);
        el.style.animationDuration = d+'s';
        el.style.animationDelay = (-Math.random()*d)+'s';
        frag.appendChild(el);
    }
    c.appendChild(frag);
}

/* Таймер */
(function(){
    function tick(){
        var nowSec = Math.floor(Date.now()/1000);
        var nEl = document.querySelector('.live-banner.now');
        if (nEl) {
            var end = parseInt(nEl.getAttribute('data-end-unix'),10);
            var until = nEl.getAttribute('data-until')||'';
            var tEl = nEl.querySelector('.live-timer');
            if (end && tEl) { var left = Math.max(0, Math.ceil((end-nowSec)/60)); tEl.textContent = 'до '+until+' · осталось '+left+' мин'; }
        }
        var bEl = document.querySelector('.live-banner.before');
        if (bEl) {
            var st = parseInt(bEl.getAttribute('data-start-unix'),10);
            var start = bEl.getAttribute('data-start')||'';
            var tEl2 = bEl.querySelector('.live-timer');
            if (st && tEl2) {
                var wait = Math.max(0, Math.ceil((st-nowSec)/60));
                var ws;
                if (wait >= 60) { var h=Math.floor(wait/60); var m=wait%60; ws=m?(h+' ч '+m+' мин'):(h+' ч'); }
                else ws = wait+' мин';
                tEl2.textContent = 'в '+start+' · через '+ws;
                var lbl = bEl.querySelector('.live-label');
                if (lbl) lbl.textContent = wait <= 30 ? 'Скоро урок' : 'Следующий урок';
            }
        }
    }
    tick();
    setInterval(tick, 10000);
})();

/* Восстановление дня */
(function(){
    var daysRu = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота'];
    var todayIdx = new Date().getDay() - 1;
    if (todayIdx < 0) todayIdx = 5; if (todayIdx > 5) todayIdx = 5;
    var todayName = daysRu[todayIdx];
    var tomorrowName = daysRu[(todayIdx+1)%6];
    var todayBlock = document.getElementById('block-' + todayName);
    var targetDay = todayName;
    if (todayBlock) { var has = todayBlock.querySelectorAll('.card').length > 0; if (!has) targetDay = tomorrowName; }
    var tb = document.getElementById('block-' + targetDay);
    if (tb) {
        document.querySelectorAll('.day-block').forEach(function(el){ el.classList.remove('active-day'); });
        tb.classList.add('active-day');
        document.querySelectorAll('.tab').forEach(function(x){ x.classList.toggle('active', x.getAttribute('data-day') === targetDay); });
    }
})();

/* PWA install */
var deferredPrompt = null;
var isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e){ e.preventDefault(); deferredPrompt = e; renderInstallSection(); });
window.addEventListener('appinstalled', function(){ deferredPrompt = null; localStorage.setItem('rs_installed','1'); renderInstallSection(); });
function renderInstallSection(){
    var el = document.getElementById('installSection');
    if (!el) return;
    if (isStandalone || localStorage.getItem('rs_installed') === '1') { el.innerHTML = '<div style="color:#10b981;font-weight:800;padding:10px 0;">✅ Приложение установлено</div>'; return; }
    if (deferredPrompt) { el.innerHTML = '<button class="ap-btn" style="width:100%;padding:14px;" onclick="doInstall()">📲 Установить приложение</button>'; return; }
    var ua = navigator.userAgent, hint;
    if (/iPhone|iPad|iPod/i.test(ua)) hint = '📱 iPhone: Safari → «Поделиться» → «На экран Домой».';
    else if (/Android/i.test(ua)) hint = '📱 Android: Chrome → ⋮ → «Установить приложение».';
    else hint = '💻 ПК: в Chrome — иконка в адресной строке.';
    el.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:10px 0;">'+hint+'</div>';
}
function doInstall(){ if(!deferredPrompt)return; deferredPrompt.prompt(); deferredPrompt.userChoice.then(function(c){ if(c.outcome==='accepted') localStorage.setItem('rs_installed','1'); deferredPrompt=null; renderInstallSection(); }); }

/* Админка */
(function(){
    var ADMIN_PWD = 'SixSeveeen';
    var isAdmin = localStorage.getItem('rs_admin') === '1';
    var taps = parseInt(localStorage.getItem('rs_taps') || '0', 10);
    var tapEl = document.getElementById('adminTap');
    if (tapEl) {
        if (isAdmin) tapEl.style.filter = 'drop-shadow(0 0 8px #fbbf24)';
        tapEl.addEventListener('click', function(ev){
            ev.preventDefault(); ev.stopPropagation();
            if (isAdmin) { openSub('admin'); return; }
            taps++;
            localStorage.setItem('rs_taps', String(taps));
            if (taps >= 50) {
                var pwd = prompt('Пароль:');
                if (pwd === ADMIN_PWD) {
                    localStorage.setItem('rs_admin','1'); localStorage.setItem('rs_taps','0');
                    isAdmin = true; taps = 0;
                    tapEl.style.filter = 'drop-shadow(0 0 8px #fbbf24)';
                    openSub('admin');
                } else { localStorage.setItem('rs_taps','0'); taps = 0; }
            }
        });
    }

    function agoStr(s){ if(s<60)return s+' сек'; if(s<3600)return Math.floor(s/60)+' мин'; if(s<86400)return Math.floor(s/3600)+' ч'; return Math.floor(s/86400)+' дн'; }
    function esc(x){ var d=document.createElement('div'); d.textContent=x; return d.innerHTML; }

    window.loadVisitors = function(){
        var saved = {};
        document.querySelectorAll('.ap-input').forEach(function(inp){ if(inp.id && inp.id.indexOf('msg_')===0 && inp.value) saved[inp.id]=inp.value; });
        fetch('/api/admin/list?admin=' + ADMIN_KEY_URL + '&t=' + Date.now())
            .then(function(r){ return r.json(); })
            .then(function(list){
                var el = document.getElementById('apList'); if(!el) return;
                var myVid = localStorage.getItem('rs_vid') || '';
                if (!Array.isArray(list) || !list.length) { el.innerHTML = '<div style="color:var(--muted);text-align:center;padding:20px;">Пока никого</div>'; return; }
                var banned = list.filter(function(v){return v.blocked;});
                var bl = document.getElementById('blockedList');
                if (bl) {
                    if (!banned.length) bl.innerHTML = '<div style="color:var(--muted);text-align:center;padding:20px;">Никто не забанен</div>';
                    else { var bh=''; banned.forEach(function(v){ bh += '<div class="ap-visitor blocked"><div class="ap-vid">'+esc(v.name||v.vid)+' 🚫</div><div class="ap-info">'+esc(v.ip)+'</div><button class="ap-btn success" data-act="unblock" data-vid="'+v.vid+'" style="margin-top:8px;">🔓 Разблокировать</button></div>'; }); bl.innerHTML = bh; }
                }
                var me = list.filter(function(v){return v.vid===myVid;});
                var others = list.filter(function(v){return v.vid!==myVid;});
                var sorted = me.concat(others);
                var html = '';
                sorted.forEach(function(v){
                    var isMe = (v.vid === myVid);
                    var cls = 'ap-visitor' + (v.blocked?' blocked':'') + (isMe?' is-me':'');
                    html += '<div class="'+cls+'">';
                    if (isMe) html += '<div class="ap-badge">👤 МОЙ АКК</div>';
                    html += '<div class="ap-vid">'+esc(v.name||v.vid)+(v.blocked?' 🚫':'')+'</div>';
                    if (v.name) html += '<div class="ap-info" style="font-size:0.7rem;opacity:0.6;">'+esc(v.vid)+'</div>';
                    html += '<div class="ap-info">IP '+esc(v.ip)+' · визитов '+v.count+'</div>';
                    html += '<div class="ap-ago">'+agoStr(v.ago)+'</div>';
                    html += '<div class="ap-actions">';
                    html += '<input class="ap-input" id="msg_'+v.vid+'" placeholder="Сообщение">';
                    html += '<button class="ap-btn" data-act="send" data-vid="'+v.vid+'">📩</button>';
                    html += '<button class="ap-rename" data-act="rename" data-vid="'+v.vid+'">✏️</button>';
                    if (!isMe) html += v.blocked ? '<button class="ap-btn success" data-act="unblock" data-vid="'+v.vid+'">🔓</button>' : '<button class="ap-btn danger" data-act="block" data-vid="'+v.vid+'">🚫</button>';
                    html += '</div></div>';
                });
                el.innerHTML = html;
                for (var sid in saved) { var s=document.getElementById(sid); if(s && !s.value) s.value = saved[sid]; }
            }).catch(function(){});
    };
    var ADMIN_KEY_URL = 'nikita_admin_2026';
    document.addEventListener('click', function(e){
        var b = e.target.closest && e.target.closest('[data-act]');
        if (!b) return;
        var act = b.getAttribute('data-act');
        var vid = b.getAttribute('data-vid');
        var key = 'nikita_admin_2026';
        if (act === 'send') {
            var inp = document.getElementById('msg_' + vid);
            if (!inp || !inp.value) return;
            fetch('/api/admin/send?admin='+key+'&to='+encodeURIComponent(vid)+'&text='+encodeURIComponent(inp.value)).then(function(){ inp.value=''; });
        } else if (act === 'rename') {
            var newName = prompt('Новое имя:', '');
            if (newName === null) return;
            fetch('/api/admin/rename?admin='+key+'&to='+encodeURIComponent(vid)+'&name='+encodeURIComponent(newName)).then(function(){ loadVisitors(); });
        } else if (act === 'block') {
            if (!confirm('Заблокировать?')) return;
            fetch('/api/admin/block?admin='+key+'&to='+encodeURIComponent(vid)).then(function(){ loadVisitors(); });
        } else if (act === 'unblock') {
            fetch('/api/admin/unblock?admin='+key+'&to='+encodeURIComponent(vid)).then(function(){ loadVisitors(); });
        }
    });
    window.switchAdminTab = function(name){
        document.querySelectorAll('.admin-tab').forEach(function(t){ t.classList.toggle('active', t.getAttribute('data-atab')===name); });
        document.querySelectorAll('.admin-pane').forEach(function(p){ p.classList.toggle('active', p.id === 'atab-'+name); });
        if (name === 'visitors' || name === 'blocked') loadVisitors();
    };
    window.sendBroadcast = function(){
        var t = document.getElementById('broadcastText');
        if (!t || !t.value) return;
        fetch('/api/admin/send?admin=nikita_admin_2026&to=__all__&text='+encodeURIComponent(t.value)).then(function(){ t.value=''; alert('✅ Отправлено'); });
    };

    /* Пул сообщений */
    var vid = localStorage.getItem('rs_vid');
    if (!vid) { vid = 'v'+Math.random().toString(36).slice(2,10)+Date.now().toString(36).slice(-4); localStorage.setItem('rs_vid', vid); }
    fetch('/api/visit?vid=' + vid).then(function(r){ return r.json(); }).then(function(d){
        if (d && d.blocked) showBlockOverlay();
    }).catch(function(){});
    var lastId = null;
    function poll(){
        if (document.hidden) return;
        fetch('/api/messages?vid=' + vid + '&t=' + Date.now(), {cache:'no-store'})
            .then(function(r){ return r.json(); })
            .then(function(m){
                if (m && m.blocked) { showBlockOverlay(); return; }
                if (m && m.id && m.id !== lastId) {
                    lastId = m.id;
                    var ov = document.getElementById('smsOverlay');
                    if (!ov) {
                        ov = document.createElement('div');
                        ov.id = 'smsOverlay';
                        ov.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.72);z-index:99999;align-items:center;justify-content:center;padding:20px;';
                        ov.innerHTML = '<div style="background:var(--card-bg);border-radius:24px;padding:32px 24px 24px;max-width:340px;width:100%;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,0.5),0 0 0 2px var(--accent);"><div style="font-size:0.75rem;color:var(--accent);font-weight:800;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:18px;">💬 Сообщение</div><div id="smsText" style="font-size:1.5rem;font-weight:800;color:var(--text-main);margin-bottom:26px;"></div><button onclick="closeSms()" style="width:100%;padding:15px;border-radius:14px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-weight:800;font-size:1rem;cursor:pointer;font-family:inherit;">Понятно</button></div>';
                        document.body.appendChild(ov);
                    }
                    var el = document.getElementById('smsText'); if (el) el.textContent = m.text;
                    ov.style.display = 'flex';
                    window.__smsId = m.id;
                }
            }).catch(function(){});
    }
    function showBlockOverlay(){
        if (document.getElementById('blockedOverlay')) return;
        var ov = document.createElement('div');
        ov.id = 'blockedOverlay';
        ov.style.cssText = 'position:fixed;inset:0;background:#0f1115;z-index:999999;display:flex;align-items:center;justify-content:center;padding:20px;text-align:center;color:#e6e8ec;font-family:-apple-system,sans-serif;';
        ov.innerHTML = '<div style="max-width:320px;"><div style="font-size:4rem;margin-bottom:20px;">🚫</div><h1 style="font-size:1.4rem;margin:0 0 10px;">Доступ закрыт</h1><p style="color:#9aa3b2;">Владелец сайта ограничил вам доступ.</p></div>';
        document.body.appendChild(ov);
    }
    window.closeSms = function(){
        var ov = document.getElementById('smsOverlay');
        if (ov) ov.style.display = 'none';
        if (window.__smsId) { fetch('/api/messages/read?vid=' + vid + '&id=' + window.__smsId).catch(function(){}); window.__smsId = null; }
        lastId = null;
    };
    setInterval(poll, 5000);
    setTimeout(poll, 1500);
})();

/* Init */
(function(){
    var s = localStorage.getItem('rs_theme') || 'light';
    document.documentElement.setAttribute('data-theme', s);
    var meta = document.getElementById('tcMeta'); if (meta) meta.setAttribute('content', THEME_COLORS[s] || '#f0f4f8');
    document.querySelectorAll('[data-theme-btn]').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-theme-btn')===s); });
    var size = localStorage.getItem('rs_size') || 'normal';
    if (size === 'small') document.documentElement.classList.add('font-small');
    if (size === 'large') document.documentElement.classList.add('font-large');
    document.querySelectorAll('[data-size]').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-size')===size); });
    ['particles','round_nums','compact','show_time','live_banner','progress_bar','glow','big_text','show_weekday','today_pill','hide_weekend'].forEach(function(k){ applyOpt(k, _optIsOn(k)); });
    updateOptUI();
    initCustom();
    applyVars();
    applyFilters();
    spawnParticles(s);
    var v;
    if ((v=localStorage.getItem('rs_u_lesson_size'))) { var i=document.getElementById('s-lesson_size'); if(i)i.value=v; var o=document.getElementById('o-lesson_size'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_u_num_size'))) { var i=document.getElementById('s-num_size'); if(i)i.value=v; var o=document.getElementById('o-num_size'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_u_card_radius'))) { var i=document.getElementById('s-card_radius'); if(i)i.value=v; var o=document.getElementById('o-card_radius'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_u_card_gap'))) { var i=document.getElementById('s-card_gap'); if(i)i.value=v; var o=document.getElementById('o-card_gap'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_f_saturate'))) { var i=document.getElementById('s-saturate'); if(i)i.value=v; }
    if ((v=localStorage.getItem('rs_f_brightness'))) { var i=document.getElementById('s-brightness'); if(i)i.value=v; }
    if ((v=localStorage.getItem('rs_f_hue-rotate'))) { var i=document.getElementById('s-hue'); if(i)i.value=v; }
    if ((v=localStorage.getItem('rs_particle_count'))) { var i=document.getElementById('s-particle_count'); if(i)i.value=v; var o=document.getElementById('o-particle_count'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_anim_speed'))) { var i=document.getElementById('s-anim_speed'); if(i)i.value=v; var o=document.getElementById('o-anim_speed'); if(o)o.textContent=v; }
})();

document.addEventListener('visibilitychange', function(){
    var ps = document.hidden ? 'paused' : 'running';
    document.querySelectorAll('.particle').forEach(function(p){ p.style.animationPlayState = ps; });
});

if ('serviceWorker' in navigator) {
    window.addEventListener('load', function(){ navigator.serviceWorker.register('/sw.js').catch(function(){}); });
}

/* ===== 100+ настроек ===== */
function setEmoji(em){
    if (!em) em = '📅';
    localStorage.setItem('rs_emoji', em);
    var el = document.getElementById('adminTap');
    if (el) el.textContent = em;
    document.querySelectorAll('.emoji-opt').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-em') === em);
    });
}
function setBgOpacity(v){ localStorage.setItem('rs_bg_opacity', v); var o=document.getElementById('o-bg_opacity'); if(o)o.textContent=v; applyBgOpacity(); }
function applyBgOpacity(){
    var v = localStorage.getItem('rs_bg_opacity');
    if (!v) return;
    var a = parseInt(v,10)/100;
    document.body.style.opacity = a;
}
function setCardOpacity(v){ localStorage.setItem('rs_card_opacity', v); var o=document.getElementById('o-card_opacity'); if(o)o.textContent=v; applyCardOpacity(); }
function applyCardOpacity(){
    var v = localStorage.getItem('rs_card_opacity');
    if (!v) return;
    document.querySelectorAll('.card').forEach(function(c){ c.style.opacity = parseInt(v,10)/100; });
}
function setCardBlur(v){ localStorage.setItem('rs_card_blur', v); var o=document.getElementById('o-card_blur'); if(o)o.textContent=v; applyCardBlur(); }
function applyCardBlur(){
    var v = localStorage.getItem('rs_card_blur');
    if (!v) return;
    document.querySelectorAll('.card').forEach(function(c){ c.style.backdropFilter = 'blur('+v+'px)'; });
}
function setCardShadow(v){ localStorage.setItem('rs_card_shadow', v); var o=document.getElementById('o-card_shadow'); if(o)o.textContent=v; applyCardShadow(); }
function applyCardShadow(){
    var v = localStorage.getItem('rs_card_shadow');
    if (!v) return;
    document.querySelectorAll('.card').forEach(function(c){
        c.style.boxShadow = '0 '+v+'px '+(v*4)+'px rgba(0,0,0,0.08)';
    });
}
function setGlowPow(v){ localStorage.setItem('rs_glow_pow', v); var o=document.getElementById('o-glow_pow'); if(o)o.textContent=v; }
function setParticleSpeed(v){ localStorage.setItem('rs_particle_speed', v); var o=document.getElementById('o-particle_speed'); if(o)o.textContent=v; spawnParticles(document.documentElement.getAttribute('data-theme')); }
function setParticleSize(v){ localStorage.setItem('rs_particle_size', v); var o=document.getElementById('o-particle_size'); if(o)o.textContent=v; spawnParticles(document.documentElement.getAttribute('data-theme')); }
function setParticleOpacity(v){ localStorage.setItem('rs_particle_opacity', v); var o=document.getElementById('o-particle_opacity'); if(o)o.textContent=v; spawnParticles(document.documentElement.getAttribute('data-theme')); }
function applyCustomCss(css){
    localStorage.setItem('rs_custom_css', css);
    var el = document.getElementById('customStyleTag');
    if (!el) {
        el = document.createElement('style');
        el.id = 'customStyleTag';
        document.head.appendChild(el);
    }
    el.textContent = css || '';
}
function setCorners(t){
    document.documentElement.classList.remove('corners-rounded','corners-sharp','corners-circle','corners-pill');
    document.documentElement.classList.add('corners-' + t);
    localStorage.setItem('rs_corners', t);
    ['rounded','sharp','circle','pill'].forEach(function(x){
        var e = document.getElementById('val-c-'+x); if(e) e.textContent = (x===t) ? '✓' : '';
    });
}
function initEmoji(){
    var em = localStorage.getItem('rs_emoji') || '📅';
    if (!em) em = '📅';
    var el = document.getElementById('adminTap');
    if (el) el.textContent = em;
    document.querySelectorAll('.emoji-opt').forEach(function(b){
        b.classList.toggle('active', b.getAttribute('data-em') === em);
    });
}
function initAllNew(){
    initEmoji();
    applyBgOpacity(); applyCardOpacity(); applyCardBlur(); applyCardShadow();
    var v;
    var sliders = ['lesson_size','time_size','dtitle_size','live_size','header_size','num_size','icon_size','tab_size','card_radius','btn_radius','header_radius','card_gap','page_pad','border_w','page_maxw','card_pad','header_pad','live_pad'];
    sliders.forEach(function(k){ if((v=localStorage.getItem('rs_u_'+k))){ var i=document.getElementById('s-'+k); if(i)i.value=v; var o=document.getElementById('o-'+k); if(o)o.textContent=v; } });
    ['saturate','brightness','contrast','hue-rotate','sepia','invert','grayscale'].forEach(function(k){ if((v=localStorage.getItem('rs_f_'+k))){ var i=document.getElementById('s-'+k.replace('hue-rotate','hue')); if(i)i.value=v; var o=document.getElementById('o-'+k.replace('-rotate','').replace('grayscale','grayscale')); if(o)o.textContent=v; } });
    ['particle_count','particle_size','particle_opacity','particle_speed','anim_speed','transition'].forEach(function(k){ if((v=localStorage.getItem('rs_'+k))){ var i=document.getElementById('s-'+k); if(i)i.value=v; var o=document.getElementById('o-'+k); if(o)o.textContent=v; } });
    if ((v=localStorage.getItem('rs_bg_opacity'))) { var i=document.getElementById('s-bg_opacity'); if(i)i.value=v; var o=document.getElementById('o-bg_opacity'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_card_opacity'))) { var i=document.getElementById('s-card_opacity'); if(i)i.value=v; var o=document.getElementById('o-card_opacity'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_card_blur'))) { var i=document.getElementById('s-card_blur'); if(i)i.value=v; var o=document.getElementById('o-card_blur'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_card_shadow'))) { var i=document.getElementById('s-card_shadow'); if(i)i.value=v; var o=document.getElementById('o-card_shadow'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_glow_pow'))) { var i=document.getElementById('s-glow_pow'); if(i)i.value=v; var o=document.getElementById('o-glow_pow'); if(o)o.textContent=v; }
    if ((v=localStorage.getItem('rs_custom_css'))) { applyCustomCss(v); var t=document.getElementById('customCss'); if(t)t.value=v; }
    if ((v=localStorage.getItem('rs_corners'))) setCorners(v);
}


/* Стартуем новые */
if (document.readyState !== "loading") initAllNew(); else document.addEventListener("DOMContentLoaded", initAllNew);
</script>
</body>
</html>"""


def build_tabs(active, days):
    today_idx = datetime.now(PERM_TZ).weekday()
    html = '<div class="tabs">'
    for i, full in enumerate(DAY_FULL):
        short = DAY_SHORT[full]
        has = full in days and len(days[full]) > 0
        cls = "tab"
        if full == active: cls += " active"
        if i == today_idx: cls += " today"
        if full in new_days_for_render: cls += " new-day"
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
        wait = st.get("wait", 0)
        label = "Скоро урок" if wait <= 30 else "Следующий урок"
        return ('<div class="live-banner before" data-start-unix="' + str(st["start_unix"]) + '" data-start="' + st["start"] + '">'
            '<div class="live-dot"></div><div class="live-info">'
            f'<div class="live-label">{label}</div>'
            f'<div class="live-lesson">{st["lesson"]}</div>'
            f'<div class="live-time">в {st["start"]}</div>'
            '</div></div>')
    return ""

def build_content(days, active, err, st):
    if err and not days: return f"<div class='error'>{err}</div>"
    today_idx = datetime.now(PERM_TZ).weekday()
    today_full = DAY_FULL[today_idx] if today_idx < 6 else ""
    html = ""
    for full in DAY_FULL:
        lessons = days.get(full, [])
        cls = " active-day" if full == active else ""
        html += f'<div class="day-block{cls}" id="block-{full}">'
        if full == today_full:
            html += f'<div class="day-title today">{full}<span class="today-pill">✨ Сегодня</span></div>'
        else:
            html += f'<div class="day-title">{full}</div>'
        if not lessons:
            html += '<div class="info-box">📭 Нет уроков</div>'
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

# ============ HANDLER ============
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, ct, body, cache=False):
        self.send_response(200)
        self.send_header("Content-type", ct)
        self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)
    def _json(self, obj, status=200):
        try:
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
        except Exception: pass

    def do_GET(self):
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            q = parse_qs(parsed.query)
            _pt = parsed.path
            _vid = (q.get("vid",[""])[0] or "").strip()[:40]
            _admin = q.get("admin",[""])[0] or ""
            _ip = self.client_address[0] if self.client_address else "?"

            # Static
            if _pt == "/manifest.json": self._send("application/manifest+json; charset=utf-8", MANIFEST.encode(), True); return
            if _pt == "/sw.js": self._send("application/javascript; charset=utf-8", SW_JS.encode(), True); return
            if _pt == "/icon.svg": self._send("image/svg+xml; charset=utf-8", ICON_SVG.encode(), True); return

            # API
            if _pt == "/api/visit":
                log_visit(_vid, _ip, self.headers.get("User-Agent",""))
                self._json({"ok": True, "blocked": is_blocked(_vid)}); return
            if _pt == "/api/messages":
                if is_blocked(_vid): self._json({"blocked": True}); return
                m = get_pending(_vid); self._json(m or {}); return
            if _pt == "/api/messages/read":
                mark_read(_vid, q.get("id",[""])[0]); self._json({"ok": True}); return
            if _pt == "/api/admin/list":
                if _admin != ADMIN_KEY: self._json({"error":"forbidden"}, 403); return
                d = _ld(VISITORS_FILE, {}); blocked = _ld(BLOCKED_FILE, {})
                now = int(time.time())
                items = [{"vid":k,"ip":v.get("ip",""),"last":v.get("last",0),"count":v.get("count",0),
                          "ua":v.get("ua","")[:70],"ago":now-v.get("last",0),
                          "blocked":bool(blocked.get(k)),"name":v.get("name","")} for k,v in d.items()]
                items.sort(key=lambda x: -x["last"])
                self._json(items); return
            if _pt == "/api/admin/send":
                if _admin != ADMIN_KEY: self._json({"error":"forbidden"}, 403); return
                to = q.get("to",[""])[0]; txt = q.get("text",[""])[0]
                if to == "__all__": send_all(txt)
                else: send_msg(to, txt)
                self._json({"ok": True}); return
            if _pt == "/api/admin/block":
                if _admin != ADMIN_KEY: self._json({"error":"forbidden"}, 403); return
                block_v(q.get("to",[""])[0]); self._json({"ok": True}); return
            if _pt == "/api/admin/unblock":
                if _admin != ADMIN_KEY: self._json({"error":"forbidden"}, 403); return
                unblock_v(q.get("to",[""])[0]); self._json({"ok": True}); return
            if _pt == "/api/admin/rename":
                if _admin != ADMIN_KEY: self._json({"error":"forbidden"}, 403); return
                rename_v(q.get("to",[""])[0], q.get("name",[""])[0]); self._json({"ok": True}); return

            # Main
            now = datetime.now(PERM_TZ)
            hour, minute = now.hour, now.minute
            wi = now.weekday()
            cur_day = DAY_FULL[wi] if wi < 6 else "Суббота"
            is_weekend = wi >= 5
            days, err = get_schedule()
            today_lessons = days.get(cur_day, [])
            school_over = (hour > 14 or (hour == 14 and minute >= 40) or is_weekend or not today_lessons)
            if school_over and wi < 5:
                ni = wi + 1
                if ni < 6:
                    tmr = DAY_FULL[ni]
                    active = tmr if days.get(tmr) else cur_day
                else: active = cur_day
            else: active = cur_day
            if active not in DAY_FULL: active = cur_day
            if not days.get(active) and days.get(cur_day): active = cur_day

            st = get_live_status(today_lessons) if not is_weekend else None
            live = build_live(st)
            tabs = build_tabs(active, days)
            content = build_content(days, active, err, st)

            html = PAGE
            html = html.replace("{live_banner}", live)
            html = html.replace("{tabs}", tabs)
            html = html.replace("{content}", content)
            html = html.replace("{sheet_url}", SHEET_URL)
            html = html.replace("{changed_at}", str(change_tracker.get("ts", 0)))

            self._send("text/html; charset=utf-8", html.encode('utf-8'))
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

load_change()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Сервер запущен на порту {port}")
    threading.Thread(target=keep_alive, daemon=True).start()
    server = HTTPServer(('0.0.0.0', port), H)
    server.serve_forever()
