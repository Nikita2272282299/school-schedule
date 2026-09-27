from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import csv
import io
from datetime import datetime, timezone, timedelta
import time

SPREADSHEET_ID = "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"

PERM_TZ = timezone(timedelta(hours=5))

TIME_TO_NUM = {
    "8:00-8:40": 1,
    "8:50-9:30": 2,
    "9:45-10:25": 3,
    "10:40-11:20": 4,
    "11:35-12:15": 5,
    "12:25-13:05": 6,
    "13:15-13:55": 7,
    "14:00-14:40": 8
}

cache = {
    "days_schedule": {},

    "error_msg": "",
    "last_update": 0
}
CACHE_TTL = 300

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

    except Exception as e:
        if cache["days_schedule"]:
            return cache["days_schedule"], ""
        error_msg = f"Офлайн-режим (нет сети)"
        cache["error_msg"] = error_msg

    return cache["days_schedule"], cache["error_msg"]


class SimpleHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()

            now_perm = datetime.now(PERM_TZ)
            hour = now_perm.hour
            minute = now_perm.minute
            weekday_idx = now_perm.weekday()

            days_order = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            current_day_name = days_order[weekday_idx] if weekday_idx < 6 else "Суббота"
            is_weekend = (weekday_idx >= 5)

            refresh_tag = "<meta http-equiv='refresh' content='900'>" if not (0 <= hour < 6) else ""

            days_schedule, error_msg = get_schedule()

            next_day_name = ""
            if weekday_idx == 4:
                next_day_name = "Понедельник"
            elif weekday_idx < len(days_order) - 1:
                next_day_name = days_order[weekday_idx + 1]
            else:
                next_day_name = "Понедельник"

            has_new_schedule = (next_day_name in days_schedule and len(days_schedule[next_day_name]) > 0)
            today_lessons = days_schedule.get(current_day_name, [])

            # Уроке кончились (позже 14:40) или сегодня выходной / нет уроков — показываем завтра по умолчанию
            school_is_over = (hour > 14 or (hour == 14 and minute >= 40) or is_weekend or not today_lessons)
            show_tomorrow_by_default = has_new_schedule and school_is_over

            active_view_name = next_day_name if show_tomorrow_by_default else current_day_name

            html = f"""
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset='utf-8'>
                <meta name='viewport' content='width=device-width, initial-scale=1'>
                {refresh_tag}
                <title>Расписание 8Г</title>
                <style>
                    :root {{
                        --card-bg: #ffffff;
                        --text-main: #1a202c;
                        --text-muted: #4a5568;
                        --accent: #4c6ef5;
                        --accent-light: #edf2ff;
                        --today-badge: #38a169;
                        --error: #e03131;
                        --shadow: 0 6px 16px rgba(0, 0, 0, 0.06);
                    }}
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                        background-color: #f0f4f8;
                        color: var(--text-main);
                        margin: 0;
                        padding: 20px 16px;
                        display: flex;
                        justify-content: center;
                    }}
                    .container {{ width: 100%; max-width: 500px; }}
                    .header-card {{
                        background: var(--card-bg);
                        padding: 20px 24px;
                        border-radius: 20px;
                        box-shadow: var(--shadow);
                        margin-bottom: 20px;
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        border: 1px solid rgba(226, 232, 240, 0.8);
                    }}
                    h2 {{
                        margin: 0; font-size: 1.7rem; color: var(--text-main); font-weight: 800;
                        display: flex; align-items: center; gap: 12px;
                    }}
                    h2 span {{
                        background: linear-gradient(135deg, #4c6ef5, #7950f2);
                        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
                    }}
                    .badge-class {{
                        background: var(--accent-light); color: var(--accent);
                        padding: 8px 16px; border-radius: 12px; font-weight: 800; font-size: 1.1rem;
                    }}
                    .notification-banner {{
                        background: linear-gradient(135deg, #ebfbee, #d3f9d8);
                        border: 1px solid #b2f2bb; padding: 16px 20px; border-radius: 16px;
                        margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between;
                        box-shadow: var(--shadow);
                    }}
                    .notification-text {{ font-size: 0.95rem; font-weight: 700; color: #2b8a3e; }}
                    .action-btn {{
                        background: #2b8a3e; color: white; border: none; padding: 10px 16px;
                        border-radius: 10px; font-weight: 700; font-size: 0.9rem; cursor: pointer;
                    }}
                    .day-block {{ display: none; }}
                    .day-block.active-day {{ display: block; }}
                    .day-title {{
                        font-size: 1.25rem; font-weight: 800; color: var(--text-muted);
                        margin-bottom: 14px; padding-left: 6px; display: flex; justify-content: space-between; align-items: center;
                    }}
                    .day-title.today {{ color: var(--text-main); }}
                    .today-pill {{
                        font-size: 0.8rem; background: #e6fcf5; color: var(--today-badge);
                        padding: 5px 12px; border-radius: 20px; font-weight: 800; text-transform: uppercase;
                    }}
                    .card {{
                        background: var(--card-bg); padding: 18px 20px; margin-bottom: 12px;
                        border-radius: 18px; box-shadow: var(--shadow);
                        display: flex; align-items: center; gap: 16px; border: 1px solid #edf2f7;
                    }}
                    .num {{
                        background: var(--accent-light); color: var(--accent); min-width: 40px;
                        height: 40px; border-radius: 12px; display: flex; align-items: center;
                        justify-content: center; font-weight: 800; font-size: 1.1rem;
                    }}
                    .left-side {{ display: flex; flex-direction: column; gap: 4px; flex-grow: 1; }}
                    .time {{ font-size: 0.85rem; color: var(--text-muted); font-weight: 700; }}
                    .lesson {{ font-size: 1.15rem; font-weight: 800; color: var(--text-main); }}
                    .error {{ background: #fff5f5; color: var(--error); padding: 18px; border-radius: 16px; font-weight: 700; font-size: 1rem; text-align: center; }}
                    .info-box {{
                        background: var(--card-bg); padding: 30px 20px; border-radius: 18px;
                        box-shadow: var(--shadow); text-align: center; font-size: 1.1rem; font-weight: 700;
                        color: var(--text-muted); border: 1px solid #edf2f7;
                    }}
                    .switcher-footer {{ margin-top: 20px; text-align: center; display: none; }}
                    .switch-link {{ background: none; border: none; color: var(--accent); font-weight: 800; font-size: 1rem; cursor: pointer; padding: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header-card">
                        <h2>📅 <span>Расписание</span></h2>
                        <div class="badge-class">8Г</div>
                    </div>
            """

            if error_msg and not cache["days_schedule"]:
                html += f"<div class='error'>{error_msg}</div>"
            else:
                # Зеленая плашка показывается, если сейчас показывается сегодняшний день, а завтрашнее расписание уже есть
                banner_display = "none" if show_tomorrow_by_default else ("flex" if has_new_schedule else "none")
                if has_new_schedule:
                    html += f"""
                        <div class="notification-banner" id="notificationBanner" style="display: {banner_display};">
                            <span class="notification-text">✨ Есть расписание на {next_day_name}!</span>
                            <button class="action-btn" onclick="showDayByName('{next_day_name}')">Посмотреть</button>
                        </div>
                    """

                # Блок сегодняшнего дня
                today_active_class = " active-day" if (current_day_name == active_view_name) else ""
                if is_weekend:
                    html += f"""
                        <div class='day-block{today_active_class}' id='block-{current_day_name}'>
                            <div class="info-box">
                                🎉 Сегодня выходной ({current_day_name})! Отдыхай! 🎮
                            </div>
                        </div>
                    """
                elif not today_lessons:
                    html += f"""
                        <div class='day-block{today_active_class}' id='block-{current_day_name}'>
                            <div class="info-box">
                                📭 Уроки на сегодня ({current_day_name}) не найдены в таблице.
                            </div>
                        </div>
                    """
                else:
                    html += f"<div class='day-block{today_active_class}' id='block-{current_day_name}'>"
                    html += f"<div class='day-title today'><span>{current_day_name}</span>"
                    html += "<span class='today-pill'>✨ Сегодня</span>"
                    html += "</div>"

                    for time_val, num_val, lesson in today_lessons:
                        html += f"<div class='card'>"
                        if num_val:
                            html += f"<div class='num'>{num_val}</div>"
                        html += f"<div class='left-side'>"
                        if time_val:
                            html += f"<div class='time'>{time_val}</div>"
                        html += f"<div class='lesson'>{lesson}</div>"
                        html += f"</div></div>"
                    html += f"</div>"

                # Блок завтрашнего дня
                if has_new_schedule:
                    tomorrow_active_class = " active-day" if (next_day_name == active_view_name) else ""
                    html += f"<div class='day-block{tomorrow_active_class}' id='block-{next_day_name}'>"
                    html += f"<div class='day-title'><span>{next_day_name}</span></div>"
                    for time_val, num_val, lesson in days_schedule[next_day_name]:
                        html += f"<div class='card'>"
                        if num_val:
                            html += f"<div class='num'>{num_val}</div>"
                        html += f"<div class='left-side'>"
                        if time_val:
                            html += f"<div class='time'>{time_val}</div>"
                        html += f"<div class='lesson'>{lesson}</div>"
                        html += f"</div></div>"
                    html += f"</div>"

                # Футер для переключения обратно на сегодня
                footer_display = "block" if show_tomorrow_by_default else "none"
                html += f"""
                    <div class="switcher-footer" id="switcherFooter" style="display: {footer_display};">
                        <button class="switch-link" onclick="showDayByName('{current_day_name}')">⬅ Посмотреть сегодняшнее расписание</button>
                    </div>
                """

            html += f"""
                </div>
                <script>
                    const currentDayName = '{current_day_name}';
                    const nextDayName = '{next_day_name}';

                    function showDayByName(dayName) {{
                        document.querySelectorAll('.day-block').forEach(function(el) {{
                            el.classList.remove('active-day');
                        }});
                        const targetBlock = document.getElementById('block-' + dayName);
                        if (targetBlock) {{
                            targetBlock.classList.add('active-day');
                        }}
                        const banner = document.getElementById('notificationBanner');
                        const footer = document.getElementById('switcherFooter');
                        
                        if (dayName !== currentDayName) {{
                            if (banner) banner.style.display = 'none';
                            if (footer) footer.style.display = 'block';
                        }} else {{
                            if (banner) banner.style.display = 'flex';
                            if (footer) footer.style.display = 'none';
                        }}
                    }}
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
        except Exception:
            pass


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Сервер запущен на порту {port}")
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()
