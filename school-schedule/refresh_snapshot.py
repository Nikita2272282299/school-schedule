"""Обновляет встроенную офлайн-копию расписания (offline-data.js).

Запуск (из папки school-schedule):

    py refresh_snapshot.py
    py refresh_snapshot.py --api http://127.0.0.1:8000

Без сети скрипт возьмёт данные из data/days_store.json. Файл offline-data.js
обновляется в корне и во всех дистрибутивах, чтобы расписание было доступно
при первом запуске сайта без интернета.
"""
import argparse
import json
import pathlib
import time
import urllib.request

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
    ap.add_argument("--api", default=DEFAULT_API, help="адрес /api/schedule")
    args = ap.parse_args()
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
    for rel in TARGETS:
        folder = BASE / rel
        if rel != "." and not folder.exists():
            continue
        (folder / "offline-data.js").write_text(text, encoding="utf-8")
        print("обновлён", (folder / "offline-data.js").relative_to(BASE))
    print("Источник:", source, "| дней:", len(snap["days"]))


if __name__ == "__main__":
    main()
