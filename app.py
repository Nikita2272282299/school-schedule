import csv, io, json, time, os, threading, urllib.request
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from html import escape as _esc

SPREADSHEET_ID = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SELF_URL = "https://school-schedule-4ldw.onrender.com/"
PERM_TZ = timezone(timedelta(hours=5))
CLASS_CODE = "8г"

TIME_TO_NUM = {
    "8:00-8:40":1, "8:50-9:30":2, "9:45-10:25":3, "10:40-11:20":4,
    "11:35-12:15":5, "12:25-13:05":6, "13:15-13:55":7, "14:00-14:40":8,
    "14:55-15:35":9, "15:50-16:30":10, "16:45-17:25":11,
    "17:35-18:15":12, "18:20-19:00":13
}
DAY_SHORT = {"Понедельник":"Пн","Вторник":"Вт","Среда":"Ср","Четверг":"Чт","Пятница":"Пт"}
DAY_FULL = ["Понедельник","Вторник","Среда","Четверг","Пятница"]

CACHE_FILE = "schedule_cache.json"
cache = {"days": {}, "err": "", "ts": 0}
CACHE_TTL = 300

def _load_disk():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _save_disk(days):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(days, f, ensure_ascii=False)
    except Exception:
        pass

def _norm_time(s):
    s = s.replace("–","-").replace("—","-").replace(" ", "").replace(".", ":")
    if "-" not in s: return ""
    try:
        a, b = s.split("-", 1)
        ah, am = a.split(":")
        bh, bm = b.split(":")
        return f"{int(ah)}:{am}-{int(bh)}:{bm}"
    except Exception:
        return ""

def fetch_schedule():
    now = time.time()
    if cache["days"] and (now - cache["ts"] < CACHE_TTL):
        return cache["days"], cache["err"]
    days = {}
    err = ""
    try:
        req = urllib.request.urlopen(CSV_URL, timeout=8)
        data = req.read().decode("utf-8")
        rows = list(csv.reader(io.StringIO(data)))

        def norm(s):
            return "".join(c for c in (s or "").lower() if c.isalnum())

        target = norm(CLASS_CODE)
        col = -1
        for row in rows:
            for i, c in enumerate(row):
                if norm(c) == target:
                    col = i; break
            if col != -1: break
        if col == -1:
            for row in rows:
                for i, c in enumerate(row):
                    if CLASS_CODE in c.lower():
                        col = i; break
                if col != -1: break

        if col == -1:
            err = f"Класс {CLASS_CODE.upper()} не найден"
        else:
            day_aliases = {
                "Понедельник": ["понедельник","пон","пн"],
                "Вторник": ["вторник","втор","вт"],
                "Среда": ["среда","сред","ср"],
                "Четверг": ["четверг","четв","чт"],
                "Пятница": ["пятница","пятн","пт"],
            }
            cur_day = ""
            for row in rows:
                if not row: continue
                words = " ".join(row).lower().split()
                found = None
                for full, aliases in day_aliases.items():
                    for a in aliases:
                        if a in words:
                            found = full; break
                    if found: break
                if found:
                    cur_day = found
                    days.setdefault(cur_day, [])
                    continue
                if not cur_day: continue
                tv = ""
                for c in row:
                    t = _norm_time(c.strip())
                    if t and t in TIME_TO_NUM:
                        tv = t; break
                if not tv: continue
                if len(row) > col:
                    lv = row[col].strip()
                    if not lv or len(lv) < 2 or ":" in lv: continue
                    if lv.lower() in ("урок","-","—",""): continue
                    num = TIME_TO_NUM[tv]
                    days[cur_day].append([tv, num, lv])
            for d in days:
                days[d] = sorted(days[d], key=lambda x: x[1])
            cache["days"] = days
            cache["err"] = ""
            cache["ts"] = now
            _save_disk(days)
    except Exception:
        disk = _load_disk()
        if disk:
            cache["days"] = disk
            cache["err"] = ""
            return disk, ""
        err = "Офлайн-режим"
    cache["err"] = err
    return days, err

def get_live(lessons):
    if not lessons: return None
    now = datetime.now(PERM_TZ)
    cur = now.hour * 60 + now.minute
    if cur < 6*60 or cur > 21*60: return None
    prev_end = None
    for tv, num, lesson in lessons:
        try:
            s, e = tv.split("-")
            sh, sm = map(int, s.split(":"))
            eh, em = map(int, e.split(":"))
        except Exception:
            continue
        ss = sh*60+sm
        ee = eh*60+em
        if ss <= cur < ee:
            prog = int((cur - ss) / max(ee - ss, 1) * 100)
            return {
                "type": "now", "num": num, "lesson": lesson, "progress": prog,
                "until": e, "left_min": max(0, ee - cur),
                "start_unix": int(now.replace(hour=sh,minute=sm,second=0,microsecond=0).timestamp()),
                "end_unix":   int(now.replace(hour=eh,minute=em,second=0,microsecond=0).timestamp()),
            }
        if cur < ss:
            st_unix = int(now.replace(hour=sh,minute=sm,second=0,microsecond=0).timestamp())
            wait = ss - cur
            if prev_end is not None:
                return {"type": "break", "num": num, "lesson": lesson,
                        "start": s, "wait_min": wait, "start_unix": st_unix}
            return {"type": "before", "num": num, "lesson": lesson,
                    "start": s, "wait_min": wait, "start_unix": st_unix}
        prev_end = ee
    return None

PAGE = """<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#f5f5f7" id="themeMeta">
<title>Расписание 8Г</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}

html[data-theme="light"]{
  --bg:#f5f5f7; --bg1:#ffffff; --bg2:#e8ecf2;
  --card:#ffffff; --text:#1a1a1f; --muted:#6b7280;
  --accent:#4f46e5; --accent2:#7c3aed; --accent-soft:rgba(79,70,229,0.10);
  --border:rgba(0,0,0,0.07);
  --shadow:0 2px 8px rgba(15,23,42,0.06),0 8px 24px rgba(15,23,42,0.04);
  --orange:#f59e0b; --orange-soft:rgba(245,158,11,0.12);
  --green:#10b981; --green-soft:rgba(16,185,129,0.12);
  --num:linear-gradient(135deg,#4f46e5,#7c3aed); --num-fg:#fff;
}
html[data-theme="dark"]{
  --bg:#0e0e10; --bg1:#1a1a1f; --bg2:#0e0e10;
  --card:#1c1c22; --text:#f0f0f3; --muted:#9a9aa8;
  --accent:#818cf8; --accent2:#c084fc; --accent-soft:rgba(129,140,248,0.14);
  --border:rgba(255,255,255,0.07);
  --shadow:0 4px 16px rgba(0,0,0,0.35),0 12px 32px rgba(0,0,0,0.25);
  --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.14);
  --green:#34d399; --green-soft:rgba(52,211,153,0.14);
  --num:linear-gradient(135deg,#818cf8,#c084fc); --num-fg:#1a1a1f;
}
html[data-theme="cosmic"]{
  --bg:#07071c; --bg1:#141138; --bg2:#050512;
  --card:rgba(30,25,70,0.55); --text:#eae4ff; --muted:#a89dd8;
  --accent:#b794f6; --accent2:#7cf5c0; --accent-soft:rgba(183,148,246,0.18);
  --border:rgba(183,148,246,0.18);
  --shadow:0 6px 24px rgba(80,30,200,0.25),0 0 40px rgba(120,80,240,0.15);
  --orange:#fbbf24; --orange-soft:rgba(251,191,36,0.18);
  --green:#7cf5c0; --green-soft:rgba(124,245,192,0.16);
  --num:linear-gradient(135deg,#b794f6,#7cf5c0); --num-fg:#1a0d3d;
}

html{min-height:100%;background:var(--bg);overflow-x:hidden}
body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--text);min-height:100vh;
  padding:12px 12px 28px;-webkit-font-smoothing:antialiased;
  transition:background .35s ease,color .35s ease;overflow-x:hidden;
}
html[data-theme="light"] body{background-image:linear-gradient(180deg,var(--bg1),var(--bg2))}
html[data-theme="dark"]  body{background-image:linear-gradient(180deg,var(--bg1),var(--bg2))}
html[data-theme="cosmic"] body{
  background-image:
    radial-gradient(ellipse 60% 40% at 15% 10%,rgba(120,80,240,0.25),transparent 60%),
    radial-gradient(ellipse 50% 40% at 85% 85%,rgba(60,220,180,0.12),transparent 55%),
    linear-gradient(180deg,var(--bg1),var(--bg2));
  background-attachment:fixed;
}
.wrap{max-width:420px;margin:0 auto}

/* ====== Шапка ====== */
.head{
  display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:6px 4px 12px;
}
.head-left{display:flex;align-items:center;gap:8px;min-width:0}
.head-emoji{font-size:1.35rem;line-height:1;flex-shrink:0}
.head-title{
  font-size:1.15rem;font-weight:800;letter-spacing:-.02em;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.head-right{display:flex;align-items:center;gap:6px;flex-shrink:0}
.head-class{
  background:var(--accent-soft);color:var(--accent);
  padding:5px 10px;border-radius:10px;font-weight:800;font-size:.8rem;
  border:1px solid var(--border);
}
.theme-btn{
  width:34px;height:34px;border-radius:10px;border:1px solid var(--border);
  background:var(--card);color:var(--text);font-size:1.05rem;cursor:pointer;
  display:flex;align-items:center;justify-content:center;font-family:inherit;
  transition:transform .25s cubic-bezier(.34,1.56,.64,1),background .2s;
}
.theme-btn:hover{background:var(--accent-soft)}
.theme-btn:active{transform:scale(.88) rotate(-12deg)}

/* ====== Табы дней ====== */
.tabs{
  display:flex;gap:3px;padding:3px;background:var(--card);
  border-radius:13px;margin-bottom:10px;border:1px solid var(--border);
  box-shadow:var(--shadow);overflow-x:auto;scrollbar-width:none;
}
.tabs::-webkit-scrollbar{display:none}
html[data-theme="cosmic"] .tabs{backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.tab{
  flex:1;min-width:0;padding:7px 4px;border:none;background:transparent;
  border-radius:10px;font-family:inherit;font-weight:800;font-size:.82rem;
  color:var(--muted);cursor:pointer;transition:all .22s;
  position:relative;min-height:40px;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:1px;
}
.tab:hover:not(.active){background:var(--accent-soft);color:var(--text)}
.tab.active{
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#fff;box-shadow:0 3px 12px var(--accent-soft);
}
html[data-theme="cosmic"] .tab.active{color:#1a0d3d}
.tab-sub{font-size:.55rem;opacity:.75;font-weight:700}
.tab.today:not(.active)::after{
  content:"";position:absolute;bottom:4px;left:50%;transform:translateX(-50%);
  width:4px;height:4px;border-radius:50%;background:var(--accent);
}

/* ====== КОМПАКТНЫЙ бар урока ====== */
.bar{
  border-radius:13px;padding:9px 12px;margin-bottom:10px;
  background:var(--card);border:1px solid var(--border);
  box-shadow:var(--shadow);transition:all .3s;
  display:flex;align-items:center;gap:10px;
}
html[data-theme="cosmic"] .bar{backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.bar.now{border-color:var(--accent);background:linear-gradient(135deg,var(--accent-soft),var(--card))}
.bar.before{border-color:var(--orange);background:linear-gradient(135deg,var(--orange-soft),var(--card))}
.bar.break{border-color:var(--green);background:linear-gradient(135deg,var(--green-soft),var(--card))}
.bar .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.bar.now .dot{background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);animation:pulse 1.8s infinite}
.bar.before .dot{background:var(--orange);box-shadow:0 0 0 3px var(--orange-soft)}
.bar.break .dot{background:var(--green);box-shadow:0 0 0 3px var(--green-soft)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.bar-content{flex:1;min-width:0;display:flex;align-items:center;gap:8px}
.bar-label{
  font-size:.6rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
  flex-shrink:0;
}
.bar.now .bar-label{color:var(--accent)}
.bar.before .bar-label{color:var(--orange)}
.bar.break .bar-label{color:var(--green)}
.bar-title{
  font-size:.9rem;font-weight:800;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;
}
.bar-time{font-size:.7rem;color:var(--muted);font-weight:700;flex-shrink:0}
.bar-time strong{font-weight:800}
.bar.now .bar-time strong{color:var(--accent)}
.bar.before .bar-time strong{color:var(--orange)}
.bar.break .bar-time strong{color:var(--green)}
.bar-progress{
  position:absolute;left:12px;right:12px;bottom:4px;height:2px;
  background:var(--border);border-radius:1px;overflow:hidden;
}
.bar.now{position:relative}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));
  transition:width .6s linear}

/* ====== Заголовок дня ====== */
.day-head{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:8px;padding:0 2px}
.day-name{font-size:.9rem;font-weight:800}
.day-chip{
  font-size:.58rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
  padding:3px 8px;border-radius:9px;background:var(--accent-soft);
  color:var(--accent);border:1px solid var(--accent);
}

/* ====== Карточки ====== */
.list{display:flex;flex-direction:column;gap:6px}
.card{
  background:var(--card);border:1px solid var(--border);border-radius:13px;
  padding:10px 12px;display:flex;align-items:center;gap:11px;
  box-shadow:0 1px 3px rgba(0,0,0,.03);transition:all .22s;
  position:relative;overflow:hidden;
}
html[data-theme="cosmic"] .card{backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
.card.now{
  border-color:var(--accent);
  background:linear-gradient(135deg,var(--accent-soft),var(--card));
  box-shadow:0 4px 16px var(--accent-soft);
}
.card.next{
  border-color:var(--orange);
  background:linear-gradient(135deg,var(--orange-soft),var(--card));
}
.card.next::before{
  content:"";position:absolute;left:0;top:0;bottom:0;width:3px;
  background:var(--orange);
}
.num{
  width:36px;height:36px;min-width:36px;border-radius:11px;
  background:var(--num);color:var(--num-fg);
  display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:.95rem;flex-shrink:0;
  box-shadow:0 2px 8px var(--accent-soft);
}
.card.next .num{background:linear-gradient(135deg,#f59e0b,#f97316);color:#fff}
.card-body{flex:1;min-width:0}
.card-time{font-size:.7rem;color:var(--muted);font-weight:700;margin-bottom:1px}
.card-title{font-size:.94rem;font-weight:700;line-height:1.25;
  letter-spacing:-.005em;word-wrap:break-word}
.pill{
  font-size:.55rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;
  padding:3px 8px;border-radius:10px;margin-left:auto;flex-shrink:0;color:#fff;
}
.pill.now{background:linear-gradient(135deg,var(--accent),var(--accent2))}
html[data-theme="cosmic"] .pill.now{color:#1a0d3d}
.pill.next{background:var(--orange)}

.empty{
  text-align:center;padding:26px 16px;background:var(--card);
  border-radius:13px;border:1px solid var(--border);
  color:var(--muted);font-weight:700;font-size:.85rem;
}
.empty-emoji{font-size:1.6rem;display:block;margin-bottom:6px;opacity:.65}

.foot{
  display:flex;align-items:center;justify-content:center;gap:6px;
  margin-top:14px;padding:10px 14px;
  color:var(--accent);text-decoration:none;font-size:.78rem;font-weight:800;
  border-radius:12px;border:1px solid var(--accent);
  background:transparent;transition:all .22s;
}
.foot:hover{background:var(--accent-soft)}

@media (max-width:380px){
  body{padding:10px 8px 22px}
  .card{padding:9px 10px;gap:10px}
  .num{width:32px;height:32px;min-width:32px;font-size:.88rem}
  .card-title{font-size:.88rem}
  .bar{padding:8px 10px}
  .bar-title{font-size:.85rem}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="head-left">
      <span class="head-emoji">📅</span>
      <span class="head-title">Расписание</span>
    </div>
    <div class="head-right">
      <span class="head-class">8Г</span>
      <button class="theme-btn" id="themeBtn" title="Сменить тему">🌙</button>
    </div>
  </div>

  {tabs}
  {bar}
  {content}

  <a class="foot" href="{sheet_url}" target="_blank" rel="noopener">
    📊 Открыть таблицу
  </a>
</div>

<script>
(function(){
  var TK = 'sch_theme_v2';
  var THEMES = ['light','dark','cosmic'];
  var ICON = {light:'☀️', dark:'🌙', cosmic:'🌌'};
  var META = {light:'#f5f5f7', dark:'#0e0e10', cosmic:'#07071c'};

  var btn = document.getElementById('themeBtn');
  var cur = 'light';
  try { cur = localStorage.getItem(TK) || 'light'; } catch(e){}
  if (THEMES.indexOf(cur) === -1) cur = 'light';

  function apply(t){
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem(TK, t); } catch(e){}
    var meta = document.getElementById('themeMeta');
    if (meta) meta.setAttribute('content', META[t]);
    if (btn) btn.textContent = ICON[t];
    cur = t;
  }

  btn.addEventListener('click', function(){
    var i = THEMES.indexOf(cur);
    apply(THEMES[(i + 1) % THEMES.length]);
  });

  apply(cur);

  var tabs = document.querySelectorAll('.tab');
  var blocks = document.querySelectorAll('.day-block');
  for (var i = 0; i < tabs.length; i++) {
    (function(tab){
      tab.addEventListener('click', function(){
        var day = tab.getAttribute('data-day');
        for (var j = 0; j < tabs.length; j++) tabs[j].classList.toggle('active', tabs[j] === tab);
        for (var k = 0; k < blocks.length; k++) blocks[k].classList.toggle('active-day', blocks[k].id === 'block-' + day);
      });
    })(tabs[i]);
  }

  function tick(){
    var nowMs = Date.now();
    var nowSec = Math.floor(nowMs / 1000);

    // Баннер "now"
    var nowEl = document.querySelector('.bar.now');
    if (nowEl) {
      var endS = parseInt(nowEl.getAttribute('data-end'), 10);
      var startS = parseInt(nowEl.getAttribute('data-start'), 10);
      var until = nowEl.getAttribute('data-until') || '';
      var leftMin = Math.max(0, Math.ceil((endS - nowSec) / 60));
      var t = nowEl.querySelector('.bar-time strong');
      if (t) t.textContent = 'до ' + until + ' · ' + leftMin + ' мин';
      var fill = nowEl.querySelector('.bar-fill');
      if (fill && startS && endS > startS) {
        var total = endS - startS;
        var passed = Math.max(0, Math.min(total, nowSec - startS));
        fill.style.width = Math.round(passed/total*100) + '%';
      }
    }

    // Баннер "before" / "break"
    var preEl = document.querySelector('.bar.before, .bar.break');
    if (preEl) {
      var stS = parseInt(preEl.getAttribute('data-start'), 10);
      var stStr = preEl.getAttribute('data-start-str') || '';
      var leftMin2 = Math.max(0, Math.ceil((stS - nowSec) / 60));
      var t2 = preEl.querySelector('.bar-time strong');
      if (t2) t2.textContent = 'в ' + stStr + ' · через ' + leftMin2 + ' мин';
    }
  }
  tick();
  setInterval(tick, 1000);
})();
</script>
</body>
</html>"""

def build_bar(st):
    if not st: return ""
    if st["type"] == "now":
        return (
            f'<div class="bar now" data-start="{st["start_unix"]}" data-end="{st["end_unix"]}" data-until="{st["until"]}">'
            '<div class="dot"></div>'
            '<div class="bar-content">'
            '<span class="bar-label">Сейчас идёт</span>'
            f'<span class="bar-title">{_esc(st["lesson"])}</span>'
            f'<span class="bar-time"><strong>до {st["until"]} · {st["left_min"]} мин</strong></span>'
            '</div>'
            f'<div class="bar-progress"><div class="bar-fill" style="width:{st["progress"]}%"></div></div>'
            '</div>')
    if st["type"] == "before":
        return (
            f'<div class="bar before" data-start="{st["start_unix"]}" data-start-str="{st["start"]}">'
            '<div class="dot"></div>'
            '<div class="bar-content">'
            '<span class="bar-label">Скоро</span>'
            f'<span class="bar-title">{_esc(st["lesson"])}</span>'
            f'<span class="bar-time"><strong>в {st["start"]} · через {st["wait_min"]} мин</strong></span>'
            '</div></div>')
    if st["type"] == "break":
        return (
            f'<div class="bar break" data-start="{st["start_unix"]}" data-start-str="{st["start"]}">'
            '<div class="dot"></div>'
            '<div class="bar-content">'
            '<span class="bar-label">Перемена</span>'
            f'<span class="bar-title">Дальше: {_esc(st["lesson"])}</span>'
            f'<span class="bar-time"><strong>в {st["start"]} · через {st["wait_min"]} мин</strong></span>'
            '</div></div>')
    return ""

def build_tabs(active, days):
    now_idx = datetime.now(PERM_TZ).weekday()
    html = '<div class="tabs">'
    for i, full in enumerate(DAY_FULL):
        has = bool(days.get(full))
        cls = "tab"
        if full == active: cls += " active"
        if i == now_idx: cls += " today"
        html += f'<button class="{cls}" data-day="{full}">{DAY_SHORT[full]}'
        html += f'<span class="tab-sub">{"•" if has else "—"}</span></button>'
    html += '</div>'
    return html

def build_content(days, active, st, err):
    if err and not days:
        return f'<div class="empty"><span class="empty-emoji">⚠️</span>{_esc(err)}</div>'
    now_idx = datetime.now(PERM_TZ).weekday()
    today_full = DAY_FULL[now_idx] if now_idx < 5 else ""
    html = ""
    for full in DAY_FULL:
        lessons = days.get(full, [])
        cls = " active-day" if full == active else ""
        html += f'<div class="day-block{cls}" id="block-{full}">'
        html += '<div class="day-head">'
        html += f'<div class="day-name">{full}</div>'
        if full == today_full:
            html += '<div class="day-chip">✨ Сегодня</div>'
        html += '</div>'
        if not lessons:
            html += '<div class="empty"><span class="empty-emoji">📭</span>Нет уроков</div>'
        else:
            html += '<div class="list">'
            for tv, num, lesson in lessons:
                cc = "card"
                pill = ""
                if full == today_full and st and st["type"] == "now" and num == st["num"]:
                    cc += " now"
                    pill = '<span class="pill now">сейчас</span>'
                elif full == today_full and st and st["type"] in ("before","break") and num == st["num"]:
                    cc += " next"
                    pill = '<span class="pill next">дальше</span>'
                html += f'<div class="{cc}"><div class="num">{num}</div>'
                html += '<div class="card-body">'
                html += f'<div class="card-time">{tv}</div>'
                html += f'<div class="card-title">{_esc(lesson)}</div>'
                html += f'</div>{pill}</div>'
            html += '</div>'
        html += '</div>'
    return html

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        try:
            if self.path.split("?")[0] != "/":
                self.send_response(404); self.end_headers(); return

            days, err = fetch_schedule()
            now = datetime.now(PERM_TZ)
            wi = now.weekday()
            cur_day = DAY_FULL[wi] if wi < 5 else ""
            today_lessons = days.get(cur_day, [])
            st = get_live(today_lessons) if wi < 5 else None

            active = cur_day if cur_day in DAY_FULL else ""
            if not days.get(active):
                for d in DAY_FULL:
                    if days.get(d):
                        active = d; break
            if not active:
                active = DAY_FULL[0]

            html = PAGE
            html = html.replace("{tabs}", build_tabs(active, days))
            html = html.replace("{bar}", build_bar(st))
            html = html.replace("{content}", build_content(days, active, st, err))
            html = html.replace("{sheet_url}", SHEET_URL)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as e:
            import traceback
            self.send_response(500); self.end_headers()
            self.wfile.write(("Error: " + str(e) + "\n\n" + traceback.format_exc()).encode("utf-8","replace"))

def keep_alive():
    while True:
        time.sleep(600)
        try: urllib.request.urlopen(SELF_URL, timeout=30)
        except Exception: pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[boot] port {port}")
    threading.Thread(target=keep_alive, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
