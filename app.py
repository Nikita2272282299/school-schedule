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

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a78bfa"/><stop offset="0.5" stop-color="#818cf8"/><stop offset="1" stop-color="#38bdf8"/></linearGradient><linearGradient id="page" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e0e7ff"/></linearGradient><filter id="s" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#1e1b4b" flood-opacity="0.28"/></filter></defs><rect width="512" height="512" rx="118" fill="url(#bg)"/><rect width="512" height="512" rx="118" fill="#ffffff" opacity="0.08"/><g filter="url(#s)"><rect x="100" y="150" width="312" height="272" rx="44" fill="url(#page)"/></g><path d="M100 194 Q100 150 144 150 L368 150 Q412 150 412 194 L412 226 L100 226 Z" fill="#1e1b4b"/><rect x="160" y="100" width="26" height="90" rx="13" fill="#1e1b4b"/><rect x="326" y="100" width="26" height="90" rx="13" fill="#1e1b4b"/><circle cx="173" cy="108" r="6" fill="#a78bfa"/><circle cx="339" cy="108" r="6" fill="#38bdf8"/><circle cx="200" cy="188" r="11" fill="#ffffff" opacity="0.92"/><circle cx="312" cy="188" r="11" fill="#ffffff" opacity="0.92"/><text x="256" y="398" font-family="Arial,sans-serif" font-size="196" font-weight="900" fill="#1e1b4b" text-anchor="middle" letter-spacing="-8">8Г</text><path d="M400 96 L406 116 L426 122 L406 128 L400 148 L394 128 L374 122 L394 116 Z" fill="#fde047"/><path d="M118 88 L122 100 L134 104 L122 108 L118 120 L114 108 L102 104 L114 100 Z" fill="#ffffff" opacity="0.85"/></svg>'''

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>self.clients.claim());self.addEventListener('fetch',e=>{e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});"


def get_schedule():
    now = time.time()
    if cache["sched"] and now - cache["ts"] < CACHE_TTL:
        return cache["sched"], cache["err"]
    days = {}
    err = ""
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
                    if d in text:
                        found = d.capitalize(); break
                if found:
                    cur_day = found
                    days.setdefault(cur_day, [])
                    continue
                if not cur_day: continue
                tv = ""
                for c in row:
                    cc = c.strip()
                    if cc in TIME_TO_NUM:
                        tv = cc; break
                if not tv: continue
                if len(row) > col:
                    lv = row[col].strip()
                    if not lv or len(lv) < 2 or ":" in lv: continue
                    if lv.lower() in ["урок", "-", "—", ""]: continue
                    n = TIME_TO_NUM[tv]
                    if n not in [x[1] for x in days[cur_day]]:
                        days[cur_day].append((tv, n, lv))
            for d in days:
                days[d].sort(key=lambda x: x[1])
            cache["sched"] = days
            cache["err"] = ""
            cache["ts"] = now
        else:
            err = f"Класс {CLASS_CODE.upper()} не найден"
            cache["err"] = err
    except Exception:
        if cache["sched"]: return cache["sched"], ""
        cache["err"] = "Офлайн-режим"
    return cache["sched"], cache["err"]


def live_status(lessons):
    if not lessons: return None
    now = datetime.now(PERM_TZ)
    cur = now.hour * 60 + now.minute
    for tv, num, lesson in lessons:
        try:
            s, e = tv.split("-")
            sh, sm = map(int, s.split(":"))
            eh, em = map(int, e.split(":"))
        except Exception: continue
        ss = sh * 60 + sm; ee = eh * 60 + em
        if ss <= cur < ee:
            prog = int((cur - ss) / max(ee - ss, 1) * 100)
            return {"type": "now", "num": num, "lesson": lesson, "progress": prog,
                    "left": ee - cur, "until": e}
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
/* ==== THEMES ==== */
:root, [data-theme="light"] {
    --bg: #eef2f7; --card: #ffffff; --text: #0f172a; --muted: #64748b;
    --accent: #6366f1; --accent2: #a855f7;
    --a-soft: rgba(99,102,241,0.10); --a-soft2: rgba(168,85,247,0.10);
    --border: rgba(15,23,42,0.06);
    --green: #10b981; --green-soft: rgba(16,185,129,0.12);
    --orange: #f59e0b; --orange-soft: rgba(245,158,11,0.12);
    --badge-bg: linear-gradient(135deg, var(--a-soft), var(--a-soft2));
    --badge-color: var(--accent);
    --num-bg: linear-gradient(135deg, var(--a-soft), var(--a-soft2));
    --num-color: var(--accent);
    --num-radius: 12px;
    --num-shadow: none;
}
[data-theme="dark"] {
    --bg: #0b0d12; --card: #1a1f2b; --text: #e8ecf3; --muted: #8b95a8;
    --accent: #818cf8; --accent2: #c084fc;
    --a-soft: rgba(129,140,248,0.14); --a-soft2: rgba(192,132,252,0.14);
    --border: rgba(255,255,255,0.06);
    --green: #34d399; --green-soft: rgba(52,211,153,0.14);
    --orange: #fbbf24; --orange-soft: rgba(251,191,36,0.14);
    --badge-bg: linear-gradient(135deg, var(--a-soft), var(--a-soft2));
    --badge-color: #c7d2fe;
    --num-bg: linear-gradient(135deg, rgba(129,140,248,0.25), rgba(192,132,252,0.25));
    --num-color: #c7d2fe;
    --num-radius: 12px;
    --num-shadow: none;
    color-scheme: dark;
}
[data-theme="cosmic"] {
    --bg: #05021a; --card: rgba(30,20,65,0.92); --text: #ece6ff; --muted: #a89cc7;
    --accent: #b794f6; --accent2: #7cf5c0;
    --a-soft: rgba(183,148,246,0.18); --a-soft2: rgba(124,245,192,0.14);
    --border: rgba(183,148,246,0.14);
    --green: #7cf5c0; --green-soft: rgba(124,245,192,0.14);
    --orange: #fbbf77; --orange-soft: rgba(251,191,119,0.14);
    --badge-bg: linear-gradient(135deg, rgba(183,148,246,0.35), rgba(124,245,192,0.2));
    --badge-color: #e0d4ff;
    --num-bg: linear-gradient(135deg, rgba(183,148,246,0.35), rgba(124,245,192,0.25));
    --num-color: #ece6ff;
    --num-radius: 12px;
    --num-shadow: 0 0 16px rgba(183,148,246,0.4);
    color-scheme: dark;
}
[data-theme="ocean"] {
    --bg: linear-gradient(180deg,#c7e8f5 0%,#94d0e6 40%,#5aafd0 100%);
    --card: rgba(255,255,255,0.96); --text: #062b3d; --muted: #4a7a8f;
    --accent: #0891b2; --accent2: #22d3ee;
    --a-soft: rgba(8,145,178,0.12); --a-soft2: rgba(34,211,238,0.12);
    --border: rgba(8,145,178,0.12);
    --green: #10b981; --green-soft: rgba(16,185,129,0.14);
    --orange: #f59e0b; --orange-soft: rgba(245,158,11,0.14);
    --badge-bg: radial-gradient(circle at 30% 25%, rgba(255,255,255,0.95), rgba(34,211,238,0.5) 60%, rgba(8,145,178,0.75));
    --badge-color: #ffffff;
    --num-bg: radial-gradient(circle at 30% 25%, rgba(255,255,255,0.95), rgba(34,211,238,0.5) 60%, rgba(8,145,178,0.75));
    --num-color: #ffffff;
    --num-radius: 50%;
    --num-shadow: 0 3px 10px rgba(8,145,178,0.3), inset -2px -3px 6px rgba(8,145,178,0.25), inset 2px 2px 8px rgba(255,255,255,0.7);
    color-scheme: light;
}
[data-theme="sunset"] {
    --bg: linear-gradient(180deg,#ffe4b8 0%,#ffc896 30%,#ffa07a 65%,#e88898 100%);
    --card: rgba(255,250,242,0.95); --text: #3d1a0a; --muted: #8a6550;
    --accent: #f97316; --accent2: #ec4899;
    --a-soft: rgba(249,115,22,0.12); --a-soft2: rgba(236,72,153,0.12);
    --border: rgba(249,115,22,0.18);
    --green: #059669; --green-soft: rgba(5,150,105,0.14);
    --orange: #d97706; --orange-soft: rgba(217,119,6,0.14);
    --badge-bg: linear-gradient(135deg,#f97316,#ec4899);
    --badge-color: #ffffff;
    --num-bg: linear-gradient(135deg,#f97316,#ec4899);
    --num-color: #ffffff;
    --num-radius: 12px;
    --num-shadow: 0 3px 10px rgba(249,115,22,0.35);
}
[data-theme="forest"] {
    --bg: linear-gradient(180deg,#e8f5e0 0%,#c8e6c0 60%,#a8d8a0 100%);
    --card: rgba(255,255,255,0.95); --text: #0f2e1b; --muted: #5f7c68;
    --accent: #059669; --accent2: #84cc16;
    --a-soft: rgba(5,150,105,0.12); --a-soft2: rgba(132,204,22,0.12);
    --border: rgba(5,150,105,0.14);
    --green: #16a34a; --green-soft: rgba(22,163,74,0.14);
    --orange: #ca8a04; --orange-soft: rgba(202,138,4,0.14);
    --badge-bg: linear-gradient(135deg,#059669,#84cc16);
    --badge-color: #ffffff;
    --num-bg: linear-gradient(135deg,#059669,#84cc16);
    --num-color: #ffffff;
    --num-radius: 30% 70% 70% 30% / 30% 30% 70% 70%;
    --num-shadow: 0 3px 10px rgba(5,150,105,0.3);
}
[data-theme="sakura"] {
    --bg: linear-gradient(180deg,#ffe8ef 0%,#ffd0e0 50%,#ffb8d0 100%);
    --card: rgba(255,255,255,0.95); --text: #3d1029; --muted: #9a6782;
    --accent: #ec4899; --accent2: #a855f7;
    --a-soft: rgba(236,72,153,0.12); --a-soft2: rgba(168,85,247,0.12);
    --border: rgba(236,72,153,0.15);
    --green: #059669; --green-soft: rgba(5,150,105,0.14);
    --orange: #ea580c; --orange-soft: rgba(234,88,12,0.14);
    --badge-bg: linear-gradient(135deg,#ec4899,#a855f7);
    --badge-color: #ffffff;
    --num-bg: linear-gradient(135deg,#ec4899,#a855f7);
    --num-color: #ffffff;
    --num-radius: 14px;
    --num-shadow: 0 3px 10px rgba(236,72,153,0.3);
}

/* ==== BASE ==== */
html {
    min-height: 100vh;
    background: var(--bg);
    background-attachment: scroll;
}
[data-theme="cosmic"] { background: #05021a; }
[data-theme="dark"] { background: #0b0d12; }
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    background-attachment: scroll;
    color: var(--text);
    margin: 0;
    padding: 20px 14px 24px;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    transition: background 0.3s ease, color 0.3s ease;
    position: relative;
    overflow-x: hidden;
}
.container { width: 100%; max-width: 520px; margin: 0 auto; position: relative; z-index: 1; }

/* Декор — статичный, только для атмосферы */
[data-theme="ocean"] body::before {
    content: ""; position: absolute; left: 0; right: 0; bottom: 0;
    height: 180px; z-index: 0; pointer-events: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 220' preserveAspectRatio='none'><path d='M0,100 Q150,30 300,100 T600,100 T900,100 T1200,100 L1200,220 L0,220 Z' fill='%230891b2' opacity='0.28'/><path d='M0,140 Q200,80 400,140 T800,140 T1200,140 L1200,220 L0,220 Z' fill='%2306b6d4' opacity='0.38'/><path d='M0,180 Q250,140 500,180 T1000,180 T1200,180 L1200,220 L0,220 Z' fill='%230891b2' opacity='0.5'/></svg>");
    background-size: 1200px 220px; background-repeat: repeat-x;
}
[data-theme="sunset"] body::before {
    content: ""; position: absolute; top: 40px; right: 30px;
    width: 140px; height: 140px; border-radius: 50%;
    background: radial-gradient(circle, rgba(255,220,120,0.95), rgba(255,140,80,0.4) 60%, transparent 75%);
    filter: blur(8px); pointer-events: none; z-index: 0;
}
[data-theme="forest"] body::before {
    content: ""; position: absolute; left: 0; right: 0; top: 0;
    height: 120px; z-index: 0; pointer-events: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 120' preserveAspectRatio='none'><path d='M0,0 L0,60 Q100,90 200,60 Q300,30 400,60 Q500,90 600,60 Q700,30 800,60 Q900,90 1000,60 Q1100,30 1200,60 L1200,0 Z' fill='%23059669' opacity='0.22'/></svg>");
    background-size: 1200px 120px; background-repeat: repeat-x;
}
[data-theme="sakura"] body::before {
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 0;
    background: radial-gradient(circle at 80% 15%, rgba(236,72,153,0.14), transparent 40%),
                radial-gradient(circle at 15% 75%, rgba(168,85,247,0.10), transparent 40%);
}
[data-theme="cosmic"] body::before {
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 0;
    background-image:
        radial-gradient(1.2px 1.2px at 24px 32px, rgba(255,255,255,0.9), transparent 60%),
        radial-gradient(0.8px 0.8px at 118px 88px, rgba(255,255,255,0.7), transparent 60%),
        radial-gradient(1.5px 1.5px at 210px 156px, rgba(183,148,246,0.9), transparent 60%),
        radial-gradient(1px 1px at 60px 200px, rgba(255,255,255,0.6), transparent 60%),
        radial-gradient(1.3px 1.3px at 260px 40px, rgba(124,245,192,0.9), transparent 60%),
        radial-gradient(0.9px 0.9px at 180px 240px, rgba(255,255,255,0.8), transparent 60%);
    background-size: 300px 300px; background-repeat: repeat;
}

/* ==== HEADER ==== */
.header {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 22px;
    padding: 14px 18px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
}
.brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-logo {
    width: 46px; height: 46px; border-radius: 14px; flex-shrink: 0;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
    box-shadow: 0 4px 14px var(--a-soft);
}
.brand-text { min-width: 0; }
.brand-title { font-size: 1.05rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; }
.brand-sub { font-size: 0.75rem; color: var(--muted); font-weight: 600; margin-top: 2px; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.badge-class {
    background: var(--badge-bg);
    color: var(--badge-color);
    padding: 8px 14px;
    border-radius: 12px;
    font-weight: 800;
    font-size: 0.95rem;
    letter-spacing: 0.02em;
    border: 1px solid var(--border);
}
[data-theme="ocean"] .badge-class {
    border: 2px solid rgba(255,255,255,0.9);
    box-shadow: 0 3px 12px rgba(8,145,178,0.3);
    width: 44px; height: 44px; padding: 0;
    display: flex; align-items: center; justify-content: center;
    position: relative;
}
[data-theme="ocean"] .badge-class::before {
    content: ""; position: absolute; top: 7px; left: 9px;
    width: 14px; height: 7px; border-radius: 50%;
    background: rgba(255,255,255,0.85); filter: blur(2px);
}
.icon-btn {
    background: var(--card);
    color: var(--muted);
    border: 1px solid var(--border);
    width: 42px; height: 42px;
    border-radius: 13px;
    font-size: 1.15rem;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-family: inherit;
}
.icon-btn:active { background: var(--a-soft); color: var(--accent); }
[data-theme="ocean"] .icon-btn {
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.9);
    background: var(--badge-bg);
    color: #fff;
    box-shadow: 0 3px 12px rgba(8,145,178,0.3);
    position: relative;
}
[data-theme="ocean"] .icon-btn::before {
    content: ""; position: absolute; top: 6px; left: 8px;
    width: 12px; height: 6px; border-radius: 50%;
    background: rgba(255,255,255,0.85); filter: blur(2px);
}

/* ==== SETTINGS (плавное открытие через grid) ==== */
.settings {
    display: grid;
    grid-template-rows: 0fr;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    margin-bottom: 0;
    transition: grid-template-rows 0.3s cubic-bezier(0.4,0,0.2,1),
                margin-bottom 0.3s cubic-bezier(0.4,0,0.2,1);
}
.settings.open { grid-template-rows: 1fr; margin-bottom: 14px; }
.settings-inner {
    overflow: hidden;
    min-height: 0;
    padding: 0 18px;
    transition: padding 0.3s cubic-bezier(0.4,0,0.2,1);
}
.settings.open .settings-inner { padding: 16px 18px; }
.settings-title {
    font-weight: 800; font-size: 0.78rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em;
    margin-bottom: 10px;
}
.settings-title:not(:first-child) { margin-top: 16px; }
.theme-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.theme-btn {
    padding: 10px 2px; border-radius: 12px; border: 2px solid transparent;
    background: var(--bg);
    color: var(--text); font-weight: 700; font-size: 0.62rem;
    cursor: pointer; display: flex; flex-direction: column;
    align-items: center; gap: 4px;
    font-family: inherit;
    transition: background 0.15s, border-color 0.15s;
}
.theme-btn .emoji { font-size: 1.25rem; line-height: 1; }
.theme-btn.active { border-color: var(--accent); background: var(--a-soft); }
.size-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.size-btn {
    padding: 11px; border-radius: 12px; border: 2px solid var(--border);
    background: var(--bg);
    color: var(--text); font-weight: 800; cursor: pointer;
    font-family: inherit;
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
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    transform: translate3d(0,0,0);
}
.toggle.on { background: linear-gradient(135deg, var(--accent), var(--accent2)); }
.toggle.on::after { transform: translate3d(20px, 0, 0); }
.install-btn {
    display: flex; align-items: center; gap: 12px;
    width: 100%; padding: 13px 16px; border-radius: 14px; border: none;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    color: #fff; font-weight: 800; cursor: pointer;
    font-family: inherit; text-align: left;
    box-shadow: 0 4px 16px var(--a-soft);
    transition: background 0.15s;
}
.install-btn .ib-emoji { font-size: 1.5rem; }
.install-btn .ib-text { display: block; font-size: 0.95rem; font-weight: 800; }
.install-btn .ib-sub { display: block; font-size: 0.7rem; font-weight: 600; opacity: 0.8; margin-top: 2px; }
.install-tip {
    max-height: 0; overflow: hidden; opacity: 0;
    background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
    padding: 0 14px; font-size: 0.83rem; line-height: 1.5;
    color: var(--muted); font-weight: 600;
    transition: max-height 0.3s ease, opacity 0.2s ease, padding 0.3s ease, margin-top 0.3s ease;
}
.install-tip.show { max-height: 200px; opacity: 1; padding: 12px 14px; margin-top: 8px; }
.installed-badge { color: var(--green); font-weight: 700; font-size: 0.9rem; padding: 8px 0; }
.link-btn {
    background: none; border: none; color: var(--muted);
    font-weight: 600; font-size: 0.82rem;
    cursor: pointer; padding: 6px 4px;
    text-decoration: underline; font-family: inherit;
}

/* ==== LIVE BANNER ==== */
.live-banner {
    border-radius: 18px;
    padding: 14px 16px;
    margin-bottom: 14px;
    display: flex; align-items: center; gap: 12px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    border: 1px solid var(--border);
    animation: fadeIn 0.3s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translate3d(0,-6px,0); } to { opacity: 1; transform: none; } }
.live-banner.now { background: linear-gradient(135deg, var(--green-soft), var(--a-soft)); }
.live-banner.before { background: linear-gradient(135deg, var(--orange-soft), var(--a-soft)); }
.live-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--green); flex-shrink: 0;
    animation: pulse 1.8s infinite;
}
.live-banner.before .live-dot { background: var(--orange); }
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
.live-info { flex: 1; min-width: 0; }
.live-label {
    font-size: 0.7rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--green); margin-bottom: 2px;
}
.live-banner.before .live-label { color: var(--orange); }
.live-lesson {
    font-size: 1.02rem; font-weight: 800;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.live-time { font-size: 0.76rem; color: var(--muted); font-weight: 700; margin-top: 2px; }
.progress-bar {
    height: 4px; border-radius: 2px; background: var(--border);
    overflow: hidden; margin-top: 7px;
}
.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--green), var(--accent2));
    border-radius: 2px;
}

/* ==== TABS ==== */
.tabs {
    display: flex; gap: 5px; margin-bottom: 14px;
    overflow-x: auto; padding: 4px;
    scrollbar-width: none; -ms-overflow-style: none;
    background: var(--card); border-radius: 16px;
    border: 1px solid var(--border);
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}
.tabs::-webkit-scrollbar { display: none; }
.tab {
    flex: 1; min-width: 50px; padding: 10px 8px;
    border-radius: 12px; border: none;
    background: transparent; color: var(--muted);
    font-weight: 800; font-size: 0.86rem;
    cursor: pointer; font-family: inherit;
    display: flex; flex-direction: column;
    align-items: center; gap: 2px;
    position: relative;
    transition: background 0.15s, color 0.15s;
}
.tab .tab-day { font-size: 0.64rem; font-weight: 700; opacity: 0.7; }
.tab.active {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    color: white;
    box-shadow: 0 3px 12px var(--a-soft);
}
.tab.active .tab-day { opacity: 0.9; }
.tab.today:not(.active)::after {
    content: ""; position: absolute; bottom: 3px; left: 50%;
    transform: translateX(-50%);
    width: 4px; height: 4px; border-radius: 50%;
    background: var(--accent);
}

/* ==== DAY BLOCKS ==== */
.day-block { display: none; }
.day-block.active { display: block; animation: fadeUp 0.25s ease; }
@keyframes fadeUp {
    from { opacity: 0; transform: translate3d(0, 6px, 0); }
    to { opacity: 1; transform: none; }
}
.day-title {
    font-size: 1.1rem; font-weight: 800;
    margin: 4px 4px 10px;
    display: flex; justify-content: space-between; align-items: center;
}
.today-pill {
    font-size: 0.66rem;
    background: linear-gradient(135deg, var(--a-soft), var(--a-soft2));
    color: var(--accent);
    padding: 4px 10px; border-radius: 20px;
    font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em;
    border: 1px solid var(--border);
}
.card {
    background: var(--card);
    padding: 13px 15px;
    margin-bottom: 8px;
    border-radius: 16px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    display: flex; align-items: center; gap: 12px;
    border: 1px solid var(--border);
    position: relative; overflow: hidden;
}
[data-theme="ocean"] .card::after {
    content: ""; position: absolute; top: 5px; left: 12px;
    width: 28px; height: 10px; border-radius: 50%;
    background: rgba(255,255,255,0.7); filter: blur(4px); pointer-events: none;
}
.card.now {
    background: linear-gradient(135deg, var(--green-soft), var(--card));
    box-shadow: 0 3px 14px var(--green-soft), 0 0 0 1.5px var(--green);
}
.card.now::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, var(--green), var(--accent2));
}
.card.next-up { box-shadow: 0 2px 12px var(--orange-soft), 0 0 0 1.5px var(--orange); }
.num {
    min-width: 40px; height: 40px;
    border-radius: var(--num-radius);
    background: var(--num-bg);
    color: var(--num-color);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 1rem;
    flex-shrink: 0;
    border: 1px solid var(--border);
    box-shadow: var(--num-shadow);
}
.card.now .num {
    background: linear-gradient(135deg, var(--green), var(--accent2));
    color: white;
    border-color: transparent;
}
.left-side { display: flex; flex-direction: column; gap: 2px; flex-grow: 1; min-width: 0; }
.time { font-size: 0.76rem; color: var(--muted); font-weight: 700; }
.lesson { font-size: 1rem; font-weight: 800; word-wrap: break-word; }
.now-pill {
    font-size: 0.6rem; background: var(--green); color: #fff;
    padding: 3px 8px; border-radius: 20px;
    font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;
    margin-left: auto; flex-shrink: 0;
}

/* ==== INFO / ERROR ==== */
.info-box {
    background: var(--card); padding: 28px 20px; border-radius: 18px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
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

/* ==== SIZE MODES ==== */
html.font-small .lesson { font-size: 0.9rem; }
html.font-small .live-lesson { font-size: 0.92rem; }
html.font-large .lesson { font-size: 1.15rem; }
html.font-large .live-lesson { font-size: 1.18rem; }
html.font-large .day-title { font-size: 1.25rem; }
html.compact .card { padding: 9px 13px; margin-bottom: 6px; }
html.compact .num { min-width: 34px; height: 34px; font-size: 0.9rem; }
html.hide-time .time { display: none; }

/* ==== FOOTER ==== */
.sheet-link {
    display: flex; align-items: center; justify-content: center;
    gap: 6px; margin-top: 18px; padding: 12px;
    color: var(--muted); text-decoration: none;
    font-size: 0.82rem; font-weight: 700;
    border-radius: 14px;
    border: 1px dashed var(--border);
    background: var(--card);
    transition: color 0.15s, border-color 0.15s;
}
.sheet-link:active { color: var(--accent); border-color: var(--accent); border-style: solid; }
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
        <div class="settings-title">🎨 Тема оформления</div>
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
(function init() {
    var saved = localStorage.getItem('rs_theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    var colors = {light:'#eef2f7',dark:'#0b0d12',cosmic:'#05021a'};
    var meta = document.getElementById('tcMeta');
    if (meta) meta.setAttribute('content', colors[saved] || '#eef2f7');
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
    var colors = {light:'#eef2f7',dark:'#0b0d12',cosmic:'#05021a'};
    var meta = document.getElementById('tcMeta');
    if (meta) meta.setAttribute('content', colors[t] || '#eef2f7');
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
window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault(); deferredPrompt = e; renderInstall();
});
window.addEventListener('appinstalled', function() {
    deferredPrompt = null;
    localStorage.setItem('rs_installed', '1');
    renderInstall();
});
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
            deferredPrompt = null;
            renderInstall();
        });
        return;
    }
    var tip = document.getElementById('installTip');
    if (!tip) return;
    if (tip.classList.contains('show')) { tip.classList.remove('show'); return; }
    var ua = navigator.userAgent;
    var text = '';
    if (/iPhone|iPad|iPod/i.test(ua)) text = '📱 Открой меню «Поделиться» (квадрат со стрелкой внизу) → «На экран Домой»';
    else if (/Android/i.test(ua)) text = '📱 Меню <b>⋮</b> в правом верхнем углу → «Установить приложение»';
    else text = '💻 В Chrome — иконка ⊕ справа в адресной строке';
    tip.innerHTML = text;
    tip.classList.add('show');
}
renderInstall();
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js').catch(function() {});
    });
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
            f'<div class="live-time">До конца {st["left"]} мин · до {st["until"]}</div>'
            f'<div class="progress-bar"><div class="progress-fill" style="width:{st["progress"]}%"></div></div>'
            '</div></div>')
    if st["type"] == "before":
        return ('<div class="live-banner before"><div class="live-dot"></div>'
            '<div class="live-info"><div class="live-label">Скоро урок</div>'
            f'<div class="live-lesson">{st["lesson"]}</div>'
            f'<div class="live-time">Через {st["wait"]} мин · в {st["start"]}</div>'
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
                cc = "card"
                pill = ""
                if full == today_full and st and st["type"] == "now" and num == st["num"]:
                    cc += " now"
                    pill = '<span class="now-pill">сейчас</span>'
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
    server = HTTPServer(('0.0.0.0', port), SimpleHandler := Handler)
    server.serve_forever()
