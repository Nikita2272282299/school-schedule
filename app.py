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
            error_msg = "Класс 8Г не найден в таблице."
            cache["error_msg"] = error_msg
    except Exception:
        if cache["days_schedule"]:
            return cache["days_schedule"], ""
        cache["error_msg"] = "Офлайн-режим (нет сети)"
    return cache["days_schedule"], cache["error_msg"]


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
    --bg: #f0f4f8; --card-bg: #ffffff; --text-main: #1a202c; --text-muted: #4a5568;
    --accent: #4c6ef5; --accent-light: #edf2ff; --today-badge: #38a169;
    --error: #e03131; --shadow: 0 6px 16px rgba(0,0,0,0.06); --border: #edf2f7;
    --banner-bg: linear-gradient(135deg, #ebfbee, #d3f9d8); --banner-border: #b2f2bb;
    --banner-text: #2b8a3e; --btn-bg: #2b8a3e;
}
[data-theme="dark"] {
    --bg: #0f1115; --card-bg: #1a1d24; --text-main: #e6e8ec; --text-muted: #9aa3b2;
    --accent: #7c93ff; --accent-light: #232741; --today-badge: #4ade80;
    --error: #ff6b6b; --shadow: 0 6px 16px rgba(0,0,0,0.4); --border: #232733;
    --banner-bg: linear-gradient(135deg, #1a2e1e, #14321c); --banner-border: #2b5733;
    --banner-text: #86efac; --btn-bg: #2b8a3e;
}
[data-theme="cosmic"] {
    --bg: radial-gradient(circle at 20% 10%, #1b1035 0%, #0a0620 55%, #030014 100%);
    --card-bg: rgba(30, 20, 60, 0.65); --text-main: #eae4ff; --text-muted: #b3a8d9;
    --accent: #b794f6; --accent-light: rgba(183, 148, 246, 0.15); --today-badge: #7cf5c0;
    --error: #ff8ab5; --shadow: 0 8px 30px rgba(140, 80, 255, 0.25);
    --border: rgba(183, 148, 246, 0.2);
    --banner-bg: linear-gradient(135deg, rgba(124,245,192,0.15), rgba(183,148,246,0.15));
    --banner-border: rgba(124, 245, 192, 0.4); --banner-text: #7cf5c0; --btn-bg: #7c3aed;
}
html { min-height: 100%; background: var(--bg); background-attachment: fixed; }
[data-theme="dark"] { color-scheme: dark; }
[data-theme="cosmic"] { color-scheme: dark; background: #030014; }
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); background-attachment: fixed; color: var(--text-main);
    margin: 0; padding: 20px 16px 30px; display: flex; justify-content: center;
    min-height: 100vh; transition: background 0.4s ease, color 0.3s ease;
}
.container { width: 100%; max-width: 500px; }
.header-card {
    background: var(--card-bg); padding: 18px 22px; border-radius: 20px;
    box-shadow: var(--shadow); margin-bottom: 16px; display: flex;
    align-items: center; justify-content: space-between; border: 1px solid var(--border);
    gap: 10px; backdrop-filter: blur(8px);
}
h2 { margin: 0; font-size: 1.4rem; font-weight: 800; display: flex; align-items: center; gap: 10px; }
h2 span { background: linear-gradient(135deg, #4c6ef5, #7950f2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
[data-theme="dark"] h2 span { background: linear-gradient(135deg, #7c93ff, #b794f6); -webkit-background-clip: text; background-clip: text; }
[data-theme="cosmic"] h2 span { background: linear-gradient(135deg, #b794f6, #7cf5c0); -webkit-background-clip: text; background-clip: text; }
.header-right { display: flex; align-items: center; gap: 8px; }
.badge-class { background: var(--accent-light); color: var(--accent); padding: 7px 14px; border-radius: 12px; font-weight: 800; font-size: 1rem; }
.icon-btn {
    background: var(--accent-light); color: var(--accent); border: none;
    width: 40px; height: 40px; border-radius: 12px; font-size: 1.15rem;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    transition: transform 0.15s;
}
.icon-btn:active { transform: scale(0.92); }
.settings-panel {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px;
    padding: 16px 18px; margin-bottom: 16px; box-shadow: var(--shadow); display: none;
    backdrop-filter: blur(8px); position: relative;
}
.settings-panel.open { display: block; animation: slideDown 0.25s ease; }
@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: none; } }
.settings-title { font-weight: 800; font-size: 0.95rem; margin-bottom: 12px; }
.theme-options { display: flex; gap: 8px; }
.theme-btn {
    flex: 1; padding: 14px 6px; border-radius: 12px; border: 2px solid var(--border);
    background: transparent; color: var(--text-main); font-weight: 700; font-size: 0.8rem;
    cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 6px;
    transition: all 0.2s;
}
.theme-btn.active { border-color: var(--accent); background: var(--accent-light); }
.theme-btn:active { transform: scale(0.96); }
.theme-btn .emoji { font-size: 1.4rem; }
.install-btn {
    width: 100%; padding: 14px; border-radius: 12px; border: none;
    background: linear-gradient(135deg, var(--accent), #7950f2); color: white;
    font-weight: 800; font-size: 0.95rem; cursor: pointer; margin-top: 4px;
    transition: transform 0.15s, opacity 0.2s;
}
.install-btn:active { transform: scale(0.97); }
.link-btn {
    background: none; border: none; color: var(--text-muted); font-weight: 600;
    font-size: 0.85rem; cursor: pointer; padding: 6px 4px; text-decoration: underline;
    margin-top: 6px; display: inline-block;
}
.installed-badge {
    color: var(--today-badge); font-weight: 700; font-size: 0.9rem;
    padding: 10px 0; display: flex; align-items: center; gap: 6px;
}
.hint-text { color: var(--text-muted); font-size: 0.82rem; line-height: 1.4; margin-top: 4px; }
.notification-banner {
    background: var(--banner-bg); border: 1px solid var(--banner-border);
    padding: 14px 18px; border-radius: 16px; margin-bottom: 16px;
    display: flex; align-items: center; justify-content: space-between;
    box-shadow: var(--shadow); gap: 10px;
}
.notification-text { font-size: 0.9rem; font-weight: 700; color: var(--banner-text); }
.action-btn {
    background: var(--btn-bg); color: white; border: none; padding: 9px 14px;
    border-radius: 10px; font-weight: 700; font-size: 0.85rem; cursor: pointer; white-space: nowrap;
}
.action-btn:active { transform: scale(0.95); }
.day-block { display: none; }
.day-block.active-day { display: block; }
.day-title {
    font-size: 1.15rem; font-weight: 800; color: var(--text-muted); margin-bottom: 12px;
    padding-left: 6px; display: flex; justify-content: space-between; align-items: center;
}
.day-title.today { color: var(--text-main); }
.today-pill {
    font-size: 0.7rem; background: var(--accent-light); color: var(--today-badge);
    padding: 5px 12px; border-radius: 20px; font-weight: 800; text-transform: uppercase;
}
.card {
    background: var(--card-bg); padding: 16px 18px; margin-bottom: 10px; border-radius: 16px;
    box-shadow: var(--shadow); display: flex; align-items: center; gap: 14px;
    border: 1px solid var(--border); transition: transform 0.15s;
    backdrop-filter: blur(8px);
}
.num {
    background: var(--accent-light); color: var(--accent); min-width: 38px; height: 38px;
    border-radius: 11px; display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 1.05rem; flex-shrink: 0;
}
.left-side { display: flex; flex-direction: column; gap: 3px; flex-grow: 1; min-width: 0; }
.time { font-size: 0.8rem; color: var(--text-muted); font-weight: 700; }
.lesson { font-size: 1.05rem; font-weight: 800; color: var(--text-main); word-wrap: break-word; }
.error { background: rgba(224,49,49,0.1); color: var(--error); padding: 16px; border-radius: 16px; font-weight: 700; text-align: center; }
.info-box {
    background: var(--card-bg); padding: 28px 20px; border-radius: 18px; box-shadow: var(--shadow);
    text-align: center; font-size: 1.05rem; font-weight: 700; color: var(--text-muted);
    border: 1px solid var(--border); backdrop-filter: blur(8px);
}
.switcher-footer { margin-top: 16px; text-align: center; }
.switch-link { background: none; border: none; color: var(--accent); font-weight: 800; font-size: 0.95rem; cursor: pointer; padding: 10px; }
.sheet-link {
    display: block; text-align: center; margin-top: 24px; color: var(--text-muted);
    text-decoration: none; font-size: 0.85rem; font-weight: 600;
    padding: 12px; border-radius: 12px; opacity: 0.7; transition: opacity 0.2s;
}
.sheet-link:active { opacity: 1; }
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
<div class="settings-title">🎨 Тема оформления</div>
<div class="theme-options">
<button class="theme-btn" data-theme-btn="light" onclick="setTheme('light')"><span class="emoji">☀️</span>Светлая</button>
<button class="theme-btn" data-theme-btn="dark" onclick="setTheme('dark')"><span class="emoji">🌙</span>Тёмная</button>
<button class="theme-btn" data-theme-btn="cosmic" onclick="setTheme('cosmic')"><span class="emoji">🌌</span>Космос</button>
</div>
<div class="settings-title" style="margin-top:18px;">📱 Приложение</div>
<div id="installSection"></div>
</div>
{content}
<a class="sheet-link" href="{sheet_url}" target="_blank" rel="noopener">📊 Открыть таблицу в Google Sheets</a>
</div>
<script>
(function() {
    var saved = localStorage.getItem('rs_theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    var meta = document.getElementById('themeColorMeta');
    if (meta) {
        var colors = {light: '#f0f4f8', dark: '#0f1115', cosmic: '#030014'};
        meta.setAttribute('content', colors[saved] || '#f0f4f8');
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
        var colors = {light: '#f0f4f8', dark: '#0f1115', cosmic: '#030014'};
        meta.setAttribute('content', colors[t] || '#f0f4f8');
    }
}
function toggleSettings() {
    document.getElementById('settingsPanel').classList.toggle('open');
}
var currentDayName = '{current_day_name}';
function showDayByName(dayName) {
    document.querySelectorAll('.day-block').forEach(function(el) {
        el.classList.remove('active-day');
    });
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
var isStandalone = window.matchMedia('(display-mode: standalone)').matches
                   || window.navigator.standalone === true;
window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault();
    deferredPrompt = e;
    renderInstallSection();
});
window.addEventListener('appinstalled', function() {
    deferredPrompt = null;
    localStorage.setItem('rs_installed', '1');
    renderInstallSection();
});
function renderInstallSection() {
    var el = document.getElementById('installSection');
    if (!el) return;
    var installed = isStandalone || localStorage.getItem('rs_installed') === '1';
    if (installed) {
        el.innerHTML = '<div class="installed-badge">✅ Приложение установлено</div>' +
                       '<button class="link-btn" onclick="resetInstallFlag()">Сбросить (показать кнопку установки)</button>';
        return;
    }
    var hidden = localStorage.getItem('rs_install_hidden') === '1';
    if (hidden) {
        el.innerHTML = '<button class="link-btn" onclick="showInstall()">Показать кнопку установки</button>';
        return;
    }
    if (deferredPrompt) {
        el.innerHTML = '<button class="install-btn" onclick="doInstall()">📲 Добавить на рабочий стол</button>' +
                       '<button class="link-btn" onclick="hideInstall()">Скрыть</button>';
    } else {
        el.innerHTML = '<div class="hint-text">Если кнопка не появилась — откройте сайт в Chrome и выберите «Установить приложение» или «Добавить на главный экран» через меню ⋮ браузера.</div>' +
                       '<button class="link-btn" onclick="hideInstall()">Скрыть это сообщение</button>';
    }
}
function doInstall() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(function(choice) {
        if (choice.outcome === 'accepted') {
            localStorage.setItem('rs_installed', '1');
        }
        deferredPrompt = null;
        renderInstallSection();
    });
}
function hideInstall() {
    localStorage.setItem('rs_install_hidden', '1');
    renderInstallSection();
}
function showInstall() {
    localStorage.removeItem('rs_install_hidden');
    renderInstallSection();
}
function resetInstallFlag() {
    localStorage.removeItem('rs_installed');
    renderInstallSection();
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


def build_content(current_day_name, next_day_name, days_schedule, error_msg, is_weekend, has_new_schedule, show_tomorrow_by_default):
    content = ""
    if error_msg and not cache["days_schedule"]:
        content += "<div class='error'>" + error_msg + "</div>"
        return content
    today_lessons = days_schedule.get(current_day_name, [])
    if has_new_schedule:
        banner_display = "none" if show_tomorrow_by_default else "flex"
        content += '<div class="notification-banner" id="notificationBanner" style="display: ' + banner_display + ';">'
        content += '<span class="notification-text">✨ Есть расписание на ' + next_day_name + '!</span>'
        content += '<button class="action-btn" onclick="showDayByName(\'' + next_day_name + '\')">Посмотреть</button></div>'
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
            content += '<div class="card"><div class="num">' + str(num_val) + '</div>'
            content += '<div class="left-side"><div class="time">' + time_val + '</div>'
            content += '<div class="lesson">' + lesson + '</div></div></div>'
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
    content += '<div class="switcher-footer" id="switcherFooter" style="display: ' + footer_display + ';">'
    content += '<button class="switch-link" onclick="showDayByName(\'' + current_day_name + '\')">⬅ Посмотреть сегодняшнее расписание</button></div>'
    return content


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
                self._send("application/manifest+json; charset=utf-8", MANIFEST.encode("utf-8"))
                return
            if path == "/sw.js":
                self._send("application/javascript; charset=utf-8", SW_JS.encode("utf-8"))
                return
            if path == "/icon.svg":
                self._send("image/svg+xml; charset=utf-8", ICON_SVG.encode("utf-8"))
                return

            now_perm = datetime.now(PERM_TZ)
            hour = now_perm.hour
            minute = now_perm.minute
            weekday_idx = now_perm.weekday()

            days_order = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
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

            content = build_content(current_day_name, next_day_name, days_schedule, error_msg, is_weekend, has_new_schedule, show_tomorrow_by_default)

            html = PAGE_TEMPLATE
            html = html.replace("{refresh_tag}", refresh_tag)
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
        except Exception:
            pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Сервер запущен на порту {port}")
    threading.Thread(target=keep_alive, daemon=True).start()
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()
