#!/usr/bin/env python3
"""
Расписание 8Г — маленький сервер без внешних зависимостей.

Что делает:
  * забирает Google-таблицу как CSV и вытаскивает из неё колонку нужного класса;
  * копит дни в days_store.json, чтобы неделя не пропадала, когда в таблице остаётся один день;
  * отдаёт сайт (index.html) и JSON по адресу /api/schedule.

Настройки (всё необязательно, можно задать переменными окружения на Render):
  SPREADSHEET_ID  id таблицы
  CLASS_CODE      класс, по умолчанию "8г"
  EXTRA_GIDS      gid дополнительных вкладок через запятую, если дни лежат на разных вкладках
  KEEPALIVE       "0" — выключить самопинг (нужен, чтобы бесплатный Render не засыпал)
  DATA_DIR        куда писать days_store.json (на бесплатном Render файловая
                  система эфемерна: файл переживёт работу, но не рестарт/деплой;
                  для надёжности подключите Render Disk и укажите DATA_DIR)
"""
import csv
import gzip
import io
import json
import os
import re
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE")
CLASS_CODE = os.getenv("CLASS_CODE", "8г")
EXTRA_GIDS = [g.strip() for g in os.getenv("EXTRA_GIDS", "").split(",") if g.strip()]
SELF_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL") or "https://school-schedule-4ldw.onrender.com"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
TZ = timezone(timedelta(hours=5))  # Пермь
CACHE_TTL = 90          # сек: как часто ходим в таблицу
FORCE_COOLDOWN = 10     # сек: защита от частых «обновить»
KEEP_DAYS = 30
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE)))
STORE_FILE = DATA_DIR / "days_store.json"

MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
          "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
WEEKDAYS = {"понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3, "пятница": 4,
            "суббота": 5, "воскресенье": 6}
WD_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
# Звонки (по вашей таблице) — нужны, только если в строке нет времени
BELLS = {1: "8:00-8:40", 2: "8:50-9:30", 3: "9:45-10:25", 4: "10:40-11:20", 5: "11:35-12:15",
         6: "12:25-13:05", 7: "13:15-13:55", 8: "14:00-14:40", 9: "14:55-15:35", 10: "15:50-16:30",
         11: "16:45-17:25", 12: "17:35-18:15", 13: "18:20-19:00"}

DATE_RE = re.compile(r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")", re.I)
DOT_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?")
TIME_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})")
CLASS_RE = re.compile(r"^\d{1,2}[а-яёa-z]$")
LOOKALIKE = str.maketrans({"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х",
                           "y": "у", "k": "к", "m": "м", "t": "т", "h": "н", "b": "в", "r": "г"})


def now_perm():
    return datetime.now(TZ)


def norm(s):
    s = re.sub(r"\s+", "", (s or "").lower())
    return s.translate(LOOKALIKE)


# ============ РАЗБОР ТАБЛИЦЫ ============

def closest_date(day, month, today):
    best = None
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if best is None or abs((d - today).days) < abs((best - today).days):
            best = d
    return best


def closest_weekday(wd, today):
    for off in (0, 1, -1, 2, -2, 3, -3):
        d = today + timedelta(days=off)
        if d.weekday() == wd:
            return d
    return today


def day_header(cells, today):
    """Строка вида «13 октября | Вторник» → date, иначе None."""
    if any(TIME_RE.search(c) for c in cells[:4]):
        return None
    found_date = None
    found_wd = None
    for c in cells:
        low = c.lower().strip()
        if not low or len(low) > 40:
            continue
        m = DATE_RE.search(low)
        if m and found_date is None:
            found_date = closest_date(int(m.group(1)), MONTHS[m.group(2)], today)
        m2 = DOT_DATE_RE.fullmatch(low)
        if m2 and found_date is None and 1 <= int(m2.group(2)) <= 12 and 1 <= int(m2.group(1)) <= 31:
            found_date = closest_date(int(m2.group(1)), int(m2.group(2)), today)
        for name, idx in WEEKDAYS.items():
            if low == name or low.startswith(name + ","):
                found_wd = idx
    if found_date:
        return found_date
    if found_wd is not None:
        return closest_weekday(found_wd, today)
    return None


def split_lesson(text):
    """«Физика, Алг (305(2),407)» → («Физика, Алг», «305(2),407»)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    i = text.find("(")
    if i == -1:
        return text, ""
    subject = text[:i].strip()
    room = text[i:].strip()
    if room.startswith("(") and room.endswith(")"):
        room = room[1:-1]
    return subject, room.strip()


def clean_time(t):
    m = TIME_RE.search(t or "")
    if not m:
        return ""
    return f"{int(m.group(1))}:{m.group(2)}-{int(m.group(3))}:{m.group(4)}"


def parse_sheet(rows, class_code, today):
    """Возвращает (days, class_found). days: {iso: {...}}."""
    target = norm(class_code)
    days = {}
    class_found = False
    cur = None
    col = None
    first_class_col = 3

    def finish(day):
        if day is None or not day["has_class"]:
            return
        lessons = [day["lessons"][n] for n in sorted(day["lessons"])]
        while lessons and not lessons[-1]["raw"]:
            lessons.pop()
        if not any(l["raw"] for l in lessons):
            lessons = []
        iso = day["date"].isoformat()
        old = days.get(iso)
        if old is None or lessons or not old["lessons"]:
            days[iso] = {
                "date": iso,
                "weekday": WD_NAMES[day["date"].weekday()],
                "lessons": lessons,
            }

    for row in rows:
        cells = [(c or "").strip() for c in row]
        if not any(cells):
            continue

        dh = day_header(cells, today)
        if dh:
            finish(cur)
            cur = {"date": dh, "has_class": False, "lessons": {}}
            col = None
            continue

        norm_cells = [norm(c) for c in cells]
        class_cols = [i for i, c in enumerate(norm_cells) if CLASS_RE.match(c)]
        if len(class_cols) >= 3:  # строка-шапка с названиями классов
            if cur is None:
                cur = {"date": today, "has_class": False, "lessons": {}}
            first_class_col = class_cols[0]
            if target in norm_cells:
                col = norm_cells.index(target)
                cur["has_class"] = True
                class_found = True
            else:
                col = None
            continue

        if cur is None or col is None:
            continue

        left = cells[:first_class_col]
        num = next((int(c) for c in left if re.fullmatch(r"\d{1,2}", c)), None)
        if num is None:
            continue
        time_str = next((clean_time(c) for c in left if TIME_RE.search(c)), "") or BELLS.get(num, "")
        text = cells[col] if col < len(cells) else ""
        if num in cur["lessons"] and cur["lessons"][num]["raw"]:
            continue
        subject, room = split_lesson(text)
        cur["lessons"][num] = {"n": num, "time": time_str, "subject": subject, "room": room, "raw": text}

    finish(cur)
    return days, class_found


# ============ ЗАГРУЗКА И КЭШ ============

_lock = threading.Lock()          # защищает _state/_store/_meta (только данные, без сети)
_fetch_lock = threading.Lock()    # гарантирует, что одновременно идёт максимум один фетч
_save_warned = False
_state = {"ts": 0.0, "ok": False, "error": "", "updated": 0, "fresh": set()}
_store = {}
_meta = {}   # iso -> {h: хэш уроков, first: когда появилось, changed: когда менялось}


def load_store():
    global _store, _meta
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            j = json.load(f)
            _store = j.get("days", {})
            _meta = j.get("meta", {})
    except Exception:
        _store, _meta = {}, {}


def save_store():
    global _save_warned
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump({"days": _store, "meta": _meta}, f, ensure_ascii=False)
    except Exception as e:
        if not _save_warned:
            _save_warned = True
            print(f"[warn] не удалось сохранить {STORE_FILE}: {e}")


def fetch_csv(gid=None):
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
    if gid:
        url += f"&gid={gid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (school-schedule)"})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = r.read().decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(data)))


def _needs_refresh(force):
    age = time.time() - _state["ts"]
    if force and age < FORCE_COOLDOWN:
        return False
    if not force and _state["ok"] and age < CACHE_TTL:
        return False
    if not force and not _state["ok"] and _state["ts"] and age < 15:
        return False
    return True


def refresh(force=False):
    """Обновляет данные при необходимости.

    Сетевой запрос идёт БЕЗ удержания _lock, поэтому запросы к /api/schedule
    не ждут чужой загрузки таблицы. Одновременно идёт максимум один фетч.
    """
    if not _needs_refresh(force):
        return
    if not _fetch_lock.acquire(blocking=False):
        return  # обновление уже идёт — отдадим то, что есть
    try:
        today = now_perm().date()
        found_any, errors, updates = False, [], {}
        for gid in [None] + EXTRA_GIDS:
            try:
                rows = fetch_csv(gid)
                days, found = parse_sheet(rows, CLASS_CODE, today)
                found_any = found_any or found
                updates.update(days)
            except Exception as e:  # сеть / доступ к таблице
                errors.append(f"{type(e).__name__}: {e}")
        now_ts = int(time.time())
        fresh = set()
        with _lock:
            for iso, d in updates.items():
                h = json.dumps(d.get("lessons", []), sort_keys=True, ensure_ascii=False)
                m = _meta.get(iso)
                if not m:
                    _meta[iso] = {"h": h, "first": now_ts, "changed": 0}
                elif m["h"] != h:
                    m["h"], m["changed"] = h, now_ts
                _store[iso] = d
                fresh.add(iso)
            _state["ts"] = time.time()
            if errors and not fresh and not found_any:
                _state["ok"] = False
                _state["error"] = "Не удалось загрузить таблицу. Показаны сохранённые данные."
            elif not found_any:
                _state["ok"] = False
                _state["error"] = f"Класс {CLASS_CODE.upper()} не найден в таблице."
            else:
                _state["ok"] = True
                _state["error"] = ""
                _state["updated"] = now_ts
                _state["fresh"] = fresh
                cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
                for k in [k for k in _store if k < cutoff]:
                    del _store[k]
        save_store()
    finally:
        _fetch_lock.release()


def build_payload(force=False):
    # Данные уже есть → отдаём сразу и обновляем в фоне (stale-while-revalidate).
    # Холодный старт (данных нет) или явное «обновить» → ждём загрузку.
    if not force and _store:
        if _needs_refresh(False):
            threading.Thread(target=refresh, daemon=True).start()
    else:
        refresh(force)
    with _lock:
        store_snapshot = dict(_store)
        state = dict(_state)
        meta_snapshot = dict(_meta)
    today = now_perm().date()
    lo, hi = (today - timedelta(days=21)).isoformat(), (today + timedelta(days=21)).isoformat()
    out = []
    for iso in sorted(store_snapshot):
        if lo <= iso <= hi:
            d = dict(store_snapshot[iso])
            d["live"] = iso in state["fresh"]
            m = meta_snapshot.get(iso) or {}
            d["first"] = m.get("first", 0)
            d["changed"] = m.get("changed", 0)
            out.append(d)
    return {
        "class": CLASS_CODE.upper(),
        "ok": state["ok"],
        "error": state["error"],
        "updated": state["updated"],
        "server_time": int(time.time()),
        "sheet_url": SHEET_URL,
        "days": out,
    }


# ============ HTTP ============

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8", "no-cache"),
    "/index.html": ("index.html", "text/html; charset=utf-8", "no-cache"),
    "/sw.js": ("sw.js", "application/javascript; charset=utf-8", "no-cache"),
    "/manifest.json": ("manifest.json", "application/manifest+json; charset=utf-8", "no-cache"),
    "/icon.svg": ("icon.svg", "image/svg+xml", "public, max-age=604800"),
    "/icon-192.png": ("icon-192.png", "image/png", "public, max-age=604800"),
    "/icon-512.png": ("icon-512.png", "image/png", "public, max-age=604800"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png", "public, max-age=604800"),
    "/favicon.ico": ("icon-192.png", "image/png", "public, max-age=604800"),
}

# файлы отдаются из памяти: диск читается только при изменении файла
_static_cache = {}


def static_cached(f):
    """(сырые байты, gzip-версия) с перепроверкой по mtime и размеру."""
    st = f.stat()
    hit = _static_cache.get(f.name)
    if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[2], hit[3]
    raw = f.read_bytes()
    gz = gzip.compress(raw, 6) if len(raw) > 512 else None
    _static_cache[f.name] = (st.st_mtime, st.st_size, raw, gz)
    return raw, gz


class Handler(BaseHTTPRequestHandler):
    server_version = "Schedule8G/2.0"
    protocol_version = "HTTP/1.1"   # keep-alive: меньше соединений на загрузку

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype, cache="no-store", head=False, etag=None, gz=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        ae = (self.headers.get("Accept-Encoding") or "").lower()
        compressible = ctype.startswith("text/") or "json" in ctype or "javascript" in ctype or "svg" in ctype
        encoding = None
        if gz is not None and "gzip" in ae and compressible:
            body, encoding = gz, "gzip"
        elif gz is None and len(body) > 512 and "gzip" in ae and compressible:
            body, encoding = gzip.compress(body, 6), "gzip"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _not_modified(self, etag, cache):
        self.send_response(304)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle(self, head=False):
        u = urlparse(self.path)
        path = u.path
        try:
            if path == "/api/schedule":
                force = parse_qs(u.query).get("force", ["0"])[0] == "1"
                body = json.dumps(build_payload(force), ensure_ascii=False).encode("utf-8")
                return self._send(200, body, "application/json; charset=utf-8", head=head)
            if path == "/healthz":
                return self._send(200, b"ok", "text/plain", head=head)
            if path in STATIC:
                name, ctype, cache = STATIC[path]
                f = BASE / name
                if not f.is_file():
                    return self._send(404, b"not found", "text/plain", head=head)
                raw, gz = static_cached(f)
                etag = f'W/"{int(f.stat().st_mtime)}-{len(raw)}"'
                if self.headers.get("If-None-Match") == etag:
                    return self._not_modified(etag, cache)
                return self._send(200, raw, ctype, cache, head=head, etag=etag, gz=gz)
            return self._send(404, "Не найдено".encode("utf-8"), "text/plain; charset=utf-8", head=head)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            try:
                self._send(500, b"error", "text/plain", head=head)
            except Exception:
                pass

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle(head=True)


def keepalive():
    """Бесплатный Render засыпает через 15 минут без запросов — будим сами себя."""
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(SELF_URL.rstrip("/") + "/healthz", timeout=20).read()
        except Exception:
            pass


def main():
    load_store()
    threading.Thread(target=refresh, daemon=True).start()
    if os.getenv("KEEPALIVE", "1") != "0":
        threading.Thread(target=keepalive, daemon=True).start()
    port = int(os.getenv("PORT", "8000"))
    print(f"Расписание {CLASS_CODE.upper()}: http://0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
