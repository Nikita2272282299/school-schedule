"""Обновляет встроенную офлайн-копию расписания (offline-data.js и блок в index.html).

Запуск (из папки school-schedule):

    py refresh_snapshot.py              # по умолчанию: напрямую из Google-таблицы
    py refresh_snapshot.py --api URL    # из API (например http://127.0.0.1:8000/api/schedule)
    py refresh_snapshot.py --sheet      # явно из Google-таблицы (для GitHub Actions)

Без сети скрипт возьмёт данные из data/days_store.json. Файл offline-data.js
обновляется в корне и во всех дистрибутивах, чтобы расписание было доступно
при первом запуске сайта без интернета, в том числе с file://.
"""
import argparse
import csv
import io
import json
import pathlib
import re
import time
import urllib.request

# Встроенная копия в index.html (между маркерами) обновляется вместе с файлом.
BOOT_RE = re.compile(r"/\*BOOT:SNAPSHOT\*/.*?/\*BOOT:SNAPSHOT:END\*/", re.S)

BASE = pathlib.Path(__file__).resolve().parent
DEFAULT_API = "https://nassda.pythonanywhere.com/api/schedule"
TARGETS = (".", "pa-dist", "hf-dist", "pages-dist")


def from_api(url):
    req = urllib.request.Request(url, headers={"User-Agent": "school-schedule/refresh"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.load(r)
    if not j.get("days"):
        raise ValueError("API вернул пустое расписание")
    return {k: j.get(k) for k in ("class", "ok", "error", "updated", "sheet_url", "days")}


def from_sheet(primary_rows=None):
    """Скачивает Google-таблицу напрямую и парсит через app.parse_sheet."""
    import app  # локальный модуль
    today = app.now_perm().date()
    found_any = False
    errors = []
    updates = {}
    for gid in [None] + app.EXTRA_GIDS:
        try:
            rows = primary_rows if gid is None and primary_rows is not None else app.fetch_csv(gid)
            days, found = app.parse_sheet(rows, app.CLASS_CODE, today)
            found_any = found_any or found
            updates.update(days)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
    if not found_any:
        raise ValueError("Класс не найден в таблице. Ошибки: " + "; ".join(errors))
    days_list = []
    for iso, d in sorted(updates.items()):
        d = dict(d)
        d["first"] = 0
        d["changed"] = 0
        days_list.append(d)
    return {
        "class": app.CLASS_CODE.upper(),
        "ok": True,
        "error": "",
        "updated": int(time.time()),
        "sheet_url": app.SHEET_URL,
        "days": days_list,
    }


def from_store():
    store = json.loads((BASE / "data/days_store.json").read_text(encoding="utf-8"))
    meta = store.get("meta", {})
    days = []
    for iso, d in sorted(store.get("days", {}).items()):
        d = dict(d)
        m = meta.get(iso, {})
        d["first"] = m.get("first", 0)
        d["changed"] = m.get("changed", 0)
        days.append(d)
    if not days:
        raise ValueError("в data/days_store.json нет дней")
    return {"class": "8Г", "ok": True, "error": "", "updated": int(time.time()),
            "sheet_url": "", "days": days}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=None, help="адрес /api/schedule (если задан, берёт оттуда)")
    ap.add_argument("--sheet", action="store_true", help="скачать напрямую из Google-таблицы")
    args = ap.parse_args()

    source = None
    snap = None

    # Build a merge-aware all-class snapshot. Do not overwrite it on failure.
    if args.sheet:
        import app
        from sheet_export import fetch_rows, write_data
        rows = fetch_rows(app.SPREADSHEET_ID)
        if not any(sum(bool(app.CLASS_RE.match(app.norm(c))) for c in row) >= 3 for row in rows):
            raise ValueError('В XLSX не найдена строка классов')
        write_data(BASE / 'sheet-data.json', rows)

    # Режим --sheet: напрямую из Google-таблицы (для GitHub Actions)
    if args.sheet:
        try:
            snap = from_sheet(rows)
            source = "Google Sheets (direct)"
        except Exception as e:
            print("Google-таблица недоступна ({}), fallback".format(e))

    # Режим по умолчанию: сначала пробуем напрямую из таблицы, потом API, потом локальный архив
    if snap is None and not args.api:
        try:
            snap = from_sheet()
            source = "Google Sheets (direct)"
        except Exception as e:
            print("Google-таблица недоступна ({}), пробую API".format(e))
            try:
                snap = from_api(DEFAULT_API)
                source = DEFAULT_API
            except Exception as e2:
                print("API недоступен ({}), беру локальный архив".format(e2))
                snap = from_store()
                source = "data/days_store.json"

    # Режим --api: только из указанного API
    if snap is None and args.api:
        try:
            snap = from_api(args.api)
            source = args.api
        except Exception as e:
            print("API недоступен ({}), беру локальный архив".format(e))
            snap = from_store()
            source = "data/days_store.json"

    snap["saved_at"] = int(time.time())
    header = ("/* Встроенная офлайн-копия расписания 8Г.\n"
              "   Обновляется при каждой успешной загрузке с API (в localStorage) и в репозитории\n"
              "   скриптом refresh_snapshot.py. Файл нужен, чтобы сайт показывал расписание\n"
              "   даже при первом запуске без интернета, в том числе с file://. */\n")
    text = header + "self.SCHEDULE_SNAPSHOT = " + json.dumps(snap, ensure_ascii=False, indent=2) + ";\n"
    inline = "/*BOOT:SNAPSHOT*/self.SCHEDULE_SNAPSHOT = " + json.dumps(snap, ensure_ascii=False) + ";/*BOOT:SNAPSHOT:END*/"
    for rel in TARGETS:
        folder = BASE / rel
        if rel != "." and not folder.exists():
            continue
        (folder / "offline-data.js").write_text(text, encoding="utf-8")
        print("обновлён", (folder / "offline-data.js").relative_to(BASE))
        html = folder / "index.html"
        if html.is_file():
            src = html.read_text(encoding="utf-8")
            out, n = BOOT_RE.subn(lambda _: inline, src, count=1)
            if n:
                html.write_text(out, encoding="utf-8")
                print("обновлён встроенный снимок", html.relative_to(BASE))
    print("Источник:", source, "| дней:", len(snap["days"]))


if __name__ == "__main__":
    main()
