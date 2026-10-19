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
  VAPID_PRIVATE_KEY  ключ для push-уведомлений (base64url или PEM); если не
                  задан, ключ создаётся сам и лежит в DATA_DIR/vapid.json.
                  Клиент при каждом открытии сайта заново присылает подписку,
                  поэтому смена ключей не ломает уведомления.
  WATCH_SECONDS   как часто сервер сам проверяет таблицу, по умолчанию 180;
                  "0" — проверять только при запросах сайта

Push-уведомления: при появлении нового дня или изменении уроков сервер шлёт
Web Push всем подписанным телефонам. Подписки и ключи лежат в DATA_DIR.
"""
import base64
import csv
import gzip
import io
import json
import os
import re
import threading
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from pywebpush import WebPushException, webpush
    PUSH_OK = True
except Exception:  # библиотека не установлена — сайт работает, уведомления нет
    PUSH_OK = False

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
VAPID_FILE = DATA_DIR / "vapid.json"
PUSH_FILE = DATA_DIR / "push_subs.json"
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", SELF_URL.rstrip("/"))

MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
          "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
WEEKDAYS = {"понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3, "пятница": 4,
            "суббота": 5, "воскресенье": 6}
WD_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
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


# ============ PUSH-УВЕДОМЛЕНИЯ ============

_psave_warned = False

def b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _vapid_normalize(private_key):
    """Принимает raw base64url или PEM → (raw base64url, публичный base64url)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    s = private_key.strip()
    if "BEGIN" in s:
        key = serialization.load_pem_private_key(s.replace("\\n", "\n").encode("utf-8"), password=None)
    else:
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        key = ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())
    raw = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint)
    return b64u(raw), b64u(pub)


def load_vapid():
    """Ключи из env, из файла или новые (файл в DATA_DIR)."""
    env_priv = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    try:
        if env_priv:
            return _vapid_normalize(env_priv)
        try:
            with open(VAPID_FILE, "r", encoding="utf-8") as f:
                j = json.load(f)
            priv, pub = _vapid_normalize(j["private"])
            return priv, pub
        except Exception:
            pass
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ec.generate_private_key(ec.SECP256R1())
        raw = key.private_numbers().private_value.to_bytes(32, "big")
        priv = b64u(raw)
        pub = b64u(key.public_key().public_bytes(serialization.Encoding.X962,
                                                 serialization.PublicFormat.UncompressedPoint))
        try:
            with open(VAPID_FILE, "w", encoding="utf-8") as f:
                json.dump({"private": priv, "public": pub}, f)
        except Exception as e:
            print(f"[warn] не удалось сохранить {VAPID_FILE}: {e}")
        return priv, pub
    except Exception as e:
        print(f"[warn] VAPID-ключи недоступны: {e}")
        return "", ""


VAPID_PRIVATE_PEM, VAPID_PUBLIC_KEY = load_vapid()
_push_lock = threading.Lock()
_subs = {}
_notify_ready = False


def load_push():
    global _subs
    try:
        with open(PUSH_FILE, "r", encoding="utf-8") as f:
            _subs = json.load(f).get("subs", {})
    except Exception:
        _subs = {}


def save_push():
    global _psave_warned
    try:
        with open(PUSH_FILE, "w", encoding="utf-8") as f:
            json.dump({"subs": _subs}, f, ensure_ascii=False)
    except Exception as e:
        if not _psave_warned:
            _psave_warned = True
            print(f"[warn] не удалось сохранить {PUSH_FILE}: {e}")


def valid_subscription(sub):
    if not isinstance(sub, dict):
        return False
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    return (isinstance(endpoint, str) and endpoint.startswith("https://") and len(endpoint) < 2000
            and bool(keys.get("p256dh")) and bool(keys.get("auth")))


def add_subscription(sub):
    endpoint = sub["endpoint"]
    clean = {"endpoint": endpoint, "ts": int(time.time()),
             "keys": {"p256dh": sub["keys"]["p256dh"], "auth": sub["keys"]["auth"]}}
    with _push_lock:
        _subs[endpoint] = clean
        if len(_subs) > 500:  # защита от бесконечного роста
            for k in sorted(_subs, key=lambda e: _subs[e].get("ts", 0))[:len(_subs) - 500]:
                _subs.pop(k, None)
    save_push()
    return len(_subs)


def remove_subscription(endpoint):
    with _push_lock:
        _subs.pop(endpoint, None)
    save_push()


def _send_push(sub, payload):
    return webpush(subscription_info=sub,
                   data=json.dumps(payload, ensure_ascii=False),
                   vapid_private_key=VAPID_PRIVATE_PEM,
                   vapid_claims={"sub": VAPID_SUBJECT},
                   ttl=3600, timeout=10)


def push_ready():
    return PUSH_OK and bool(VAPID_PRIVATE_PEM and VAPID_PUBLIC_KEY)


def broadcast(events):
    """Рассылает события всем телефонам; мёртвые подписки удаляет."""
    if not push_ready() or not events:
        return
    with _push_lock:
        targets = list(_subs.values())
    dead = []
    for sub in targets:
        for ev in events:
            try:
                _send_push(sub, ev)
            except WebPushException as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code in (401, 403, 404, 410):  # подписка мертва или ключ сменился
                    dead.append(sub.get("endpoint"))
                else:
                    print(f"[push] {code}: {str(e)[:200]}")
                break
            except Exception as e:
                print(f"[push] {type(e).__name__}: {str(e)[:200]}")
                break
    if dead:
        with _push_lock:
            for endpoint in dead:
                _subs.pop(endpoint, None)
        save_push()


def _lesson_line(l):
    return f"{l.get('n')}. {l.get('subject') or '—'}"


def build_event(iso, day, old, is_new):
    """Текст уведомления об одном дне."""
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return None
    when = f"{d.day} {MONTHS_GEN[d.month - 1]}"
    lessons = [l for l in day.get("lessons", []) if l.get("raw")]
    old_map = {l.get("n"): l for l in (old or {}).get("lessons", []) if l.get("raw")}
    new_map = {l.get("n"): l for l in lessons}
    if is_new or not old_map:
        title = f"Расписание на {when}"
        if lessons:
            body = ", ".join(_lesson_line(l) for l in lessons[:4])
            if len(lessons) > 4:
                body += f" и ещё {len(lessons) - 4}"
        else:
            body = "Уроков нет"
        return {"title": title, "body": body, "tag": iso, "url": f"/?day={iso}"}
    parts = []
    for n in sorted(set(old_map) | set(new_map)):
        a, b = old_map.get(n), new_map.get(n)
        if a and not b:
            parts.append(f"− {n}. {a.get('subject') or '—'}")
        elif b and not a:
            parts.append(f"+ {n}. {b.get('subject') or '—'}")
        elif a.get("subject") != b.get("subject"):
            parts.append(f"{n}. {a.get('subject') or '—'} → {b.get('subject') or '—'}")
        elif a.get("room") != b.get("room"):
            parts.append(f"{n}. {b.get('subject') or '—'}: каб. {a.get('room') or '—'} → {b.get('room') or '—'}")
        elif a.get("time") != b.get("time"):
            parts.append(f"{n}. {a.get('time')} → {b.get('time')}")
    if not parts:
        parts.append("Расписание обновилось")
    body = ", ".join(parts[:3])
    if len(parts) > 3:
        body += f" и ещё {len(parts) - 3}"
    return {"title": f"Изменения на {when}", "body": body, "tag": iso, "url": f"/?day={iso}"}


# ============ ЗАГРУЗКА И КЭШ ============

_lock = threading.Lock()          # защищает _state/_store/_meta (только данные, без сети)
_fetch_lock = threading.Lock()    # гарантирует, что одновременно идёт максимум один фетч
_save_warned = False
_state = {"ts": 0.0, "ok": False, "error": "", "updated": 0, "fresh": set()}
_store = {}
_meta = {}   # iso -> {h: хэш уроков, first: когда появилось, changed: когда менялось}


def load_store():
    global _store, _meta, _notify_ready
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            j = json.load(f)
            _store = j.get("days", {})
            _meta = j.get("meta", {})
    except Exception:
        _store, _meta = {}, {}
    # первый запуск с пустым хранилищем не должен разослать всё расписание
    _notify_ready = bool(_store)


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
        events = []
        today_iso = today.isoformat()
        with _lock:
            notify = _notify_ready
            for iso, d in updates.items():
                old = _store.get(iso)
                h = json.dumps(d.get("lessons", []), sort_keys=True, ensure_ascii=False)
                m = _meta.get(iso)
                is_new = m is None
                changed = False
                if is_new:
                    _meta[iso] = {"h": h, "first": now_ts, "changed": 0}
                elif m["h"] != h:
                    m["h"], m["changed"] = h, now_ts
                    changed = True
                _store[iso] = d
                fresh.add(iso)
                if notify and iso >= today_iso and (is_new or changed):
                    ev = build_event(iso, d, old, is_new)
                    if ev:
                        events.append(ev)
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
            if found_any:
                globals()["_notify_ready"] = True
        save_store()
        if events:
            threading.Thread(target=broadcast, args=(events[:3],), daemon=True).start()
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


# ============ ВИДЖЕТ ДЛЯ ЭКРАНА БЛОКИРОВКИ ============

SUBJ_FULL = {
    "алг": "Алгебра", "геом": "Геометрия", "матем": "Математика", "математика": "Математика",
    "вис": "Вероятность и статистика", "рус.яз.": "Русский язык", "русский язык": "Русский язык",
    "литер": "Литература", "литература": "Литература", "ин.яз.": "Иностранный язык",
    "иностранный язык": "Иностранный язык", "англ": "Английский язык", "англ.яз.": "Английский язык",
    "ист": "История", "история": "История", "общ": "Обществознание",
    "обществознание": "Обществознание", "географ": "География", "география": "География",
    "физ-ра": "Физкультура", "физкультура": "Физкультура", "физика": "Физика", "хим": "Химия",
    "химия": "Химия", "био": "Биология", "биология": "Биология", "инф": "Информатика",
    "информатика": "Информатика", "обзр": "ОБЗР", "ров": "Разговоры о важном", "изо": "ИЗО",
    "муз": "Музыка", "труд": "Труд (технология)", "технология": "Труд (технология)",
    "алгоритмика": "Алгоритмика", "эврика": "Эврика", "проект": "Проект",
}


def _pretty_subject(raw, full=False):
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    out = []
    for p in parts:
        m = re.match(r"^(.*?)\s+пр$", p, re.I)
        base = (m.group(1) if m else p).strip()
        name = SUBJ_FULL.get(base.lower(), base) if full else base
        out.append(name + (" ПР" if m else ""))
    return (" / " if full else ", ").join(out)


def _lesson_secs(t):
    m = TIME_RE.search(t or "")
    if not m:
        return None
    return (int(m.group(1)) * 3600 + int(m.group(2)) * 60,
            int(m.group(3)) * 3600 + int(m.group(4)) * 60)


def _w_lessons(day, full):
    out = []
    for l in (day or {}).get("lessons") or []:
        if not l.get("raw"):
            continue
        tm = _lesson_secs(l.get("time"))
        if not tm:
            continue
        out.append({"n": l.get("n"), "s": tm[0], "e": tm[1],
                    "subject": _pretty_subject(l.get("subject") or l.get("raw"), full),
                    "room": (l.get("room") or "").strip()})
    return out


def _hm(sec):
    return f"{sec // 3600}:{sec % 3600 // 60:02d}"


def _lessons_word(n):
    m, d = n % 100, n % 10
    w = "уроков" if 10 < m < 15 else ("урок" if d == 1 else ("урока" if 1 < d < 5 else "уроков"))
    return f"{n} {w}"


def _widget_opts(qs):
    theme = qs.get("theme", ["auto"])[0]
    if theme not in ("auto", "dark", "light"):
        theme = "auto"
    accent = qs.get("accent", ["6366f1"])[0].lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", accent):
        accent = "6366f1"
    def flag(name, default=True):
        return qs.get(name, ["1" if default else "0"])[0] not in ("0", "false", "off", "")
    return {"theme": theme, "accent": "#" + accent.lower(), "room": flag("room"),
            "next": flag("next"), "progress": flag("progress"), "full": flag("full", False)}


def widget_status(opts=None):
    opts = opts or {}
    full = bool(opts.get("full"))
    payload = build_payload(False)
    now = now_perm()
    today = now.date()
    t = now.hour * 3600 + now.minute * 60 + now.second
    days = {d.get("date"): d for d in payload.get("days") or []}
    cls = payload.get("class") or CLASS_CODE.upper()
    lessons = _w_lessons(days.get(today.isoformat()), full)

    def next_day_info(after):
        for i in range(1, 22):
            d = after + timedelta(days=i)
            ls = _w_lessons(days.get(d.isoformat()), full)
            if ls:
                rel = "Завтра" if i == 1 else WD_NAMES[d.weekday()]
                return f"{rel}: {_lessons_word(len(ls))} · с {_hm(ls[0]['s'])}"
        return "Следующих дней в таблице пока нет"

    def count_text(sec):
        if sec is None:
            return "—"
        return f"{max(0, -(-sec // 60))} мин"

    state, cur, nxt, left, prog = "none", None, None, None, 0.0
    if not days.get(today.isoformat()):
        state = "weekend" if today.weekday() >= 5 else "none"
    elif not lessons:
        state = "free"
    elif t < lessons[0]["s"]:
        state, nxt = "before", lessons[0]
        left = lessons[0]["s"] - t
    else:
        state = "done"
        for i, l in enumerate(lessons):
            if t < l["s"]:
                break
            if t < l["e"]:
                state, cur = "now", l
                left = l["e"] - t
                prog = (t - l["s"]) / max(1, l["e"] - l["s"])
                if i + 1 < len(lessons):
                    nxt = lessons[i + 1]
                break
            if i + 1 < len(lessons) and t < lessons[i + 1]["s"]:
                gap = lessons[i + 1]["s"] - l["e"]
                state = "window" if gap > 1500 else "break"
                nxt = lessons[i + 1]
                left = nxt["s"] - t
                prog = (t - l["e"]) / max(1, gap)
                break

    header = {"now": f"Урок {cur['n']}" if cur else "Урок", "break": "Перемена",
              "window": "Окно", "before": "Скоро уроки", "done": "Уроки закончились",
              "free": "Уроков нет", "weekend": "Выходной", "none": "Нет данных"}[state]
    shown = cur or nxt
    subject, room = "", ""
    if state == "now" and cur:
        subject, room = cur["subject"], cur["room"]
    elif state in ("before", "break", "window") and nxt:
        subject, room = nxt["subject"], nxt["room"]
    elif state == "done":
        subject = "Отдыхай"
    elif state == "free":
        subject = "Сегодня уроков нет"
    elif state == "weekend":
        subject = "Сегодня выходной"
    elif state == "none":
        subject = "Расписание не опубликовано"

    room_text = f"каб. {room}" if room and opts.get("room", True) else ""
    if room_text:
        header += " · " + room_text
    header += " · " + cls

    label = {"now": "до конца", "break": "до урока", "window": "до урока",
             "before": "до начала", "done": "на сегодня всё", "free": "уроков нет",
             "weekend": "выходной", "none": "нет данных"}[state]
    if state == "now" and cur:
        sub_text, start, end = f"до конца · {_hm(cur['e'])}", _hm(cur["s"]), _hm(cur["e"])
        next_text = (f"Дальше: {nxt['subject']} · {_hm(nxt['s'])}" if nxt and opts.get("next", True)
                     else ("Последний урок сегодня" if opts.get("next", True) else ""))
    elif state in ("break", "window") and nxt:
        sub_text, start, end = f"до урока · {_hm(nxt['s'])}", _hm(nxt["s"]), _hm(nxt["e"])
        after = lessons[lessons.index(nxt) + 1] if nxt in lessons and lessons.index(nxt) + 1 < len(lessons) else None
        next_text = (f"После: {after['subject']} · {_hm(after['s'])}" if after and opts.get("next", True)
                     else ("Последний урок сегодня" if opts.get("next", True) else ""))
    elif state == "before" and nxt:
        sub_text, start, end = f"до начала · {_hm(nxt['s'])}", _hm(nxt["s"]), _hm(nxt["e"])
        after = lessons[1] if len(lessons) > 1 else None
        next_text = (f"Дальше: {after['subject']} · {_hm(after['s'])}" if after and opts.get("next", True)
                     else ("Всего " + _lessons_word(len(lessons)) if opts.get("next", True) else ""))
    else:
        start = end = ""
        sub_text = label
        next_text = next_day_info(today) if opts.get("next", True) else ""

    if not opts.get("progress", True):
        prog = 0.0
    return {
        "ok": bool(payload.get("ok")), "cls": cls, "date": today.isoformat(), "state": state,
        "header": header, "subject": subject, "room_text": room_text,
        "countdown": None if left is None else max(0, -(-left // 60)),
        "countdown_text": count_text(left), "unit": "мин", "label": label,
        "start": start, "end": end, "time": end if state == "now" else start,
        "progress": round(max(0.0, min(1.0, prog)), 3),
        "sub_text": sub_text, "next_text": next_text,
        "lesson": (cur or nxt or {}).get("n"), "total": len(lessons),
        "left_sec": 0 if left is None else max(0, left),
        "server_time": int(now.timestamp()), "updated": payload.get("updated", 0),
        "error": payload.get("error", ""),
    }


def _ios_widget(cfg):
    w = widget_status(cfg["opts"])
    starter = ("// Файл для приложения Scriptable (App Store, бесплатно).\n"
               "// 1. Откройте файл на iPhone → «Поделиться» → Scriptable.\n"
               "// 2. Зажмите экран блокировки → «Настроить» → «Добавить виджет».\n"
               "// 3. Выберите Scriptable и этот скрипт. Файл можно скачать заново с сайта.\n")
    return starter + _IOS_TMPL.replace("__CONFIG__", json.dumps(cfg, ensure_ascii=False, indent=2))


_IOS_TMPL = r'''
const CONFIG = __CONFIG__;
const ACCENT = new Color(CONFIG.accent);

function hexA(hex, a) { return new Color(hex, a); }

async function loadStatus() {
  const q = CONFIG.api + (CONFIG.api.includes("?") ? "&" : "?") + "t=" + Date.now();
  const req = new Request(q);
  req.timeoutInterval = 12;
  try {
    const j = await req.loadJSON();
    if (j && j.state) {
      try {
        const fm = FileManager.local();
        fm.writeString(fm.joinPath(fm.documentsDirectory(), "sch8g-widget.json"), JSON.stringify(j));
      } catch (e) {}
      return j;
    }
  } catch (e) {}
  try {
    const fm = FileManager.local();
    const p = fm.joinPath(fm.documentsDirectory(), "sch8g-widget.json");
    if (fm.fileExists(p)) return JSON.parse(fm.readString(p));
  } catch (e) {}
  return null;
}

function palette() {
  const dark = CONFIG.theme === "dark" || (CONFIG.theme === "auto" && Device.isUsingDarkAppearance());
  return dark
    ? { bg1: "#151a2b", bg2: "#0b0e17", fg: "#ffffff", muted: "#9aa3b2" }
    : { bg1: "#f7f8fd", bg2: "#e8edf8", fg: "#111827", muted: "#6b7280" };
}

function addBar(w, p, color, width, height) {
  if (!CONFIG.showProgress) return;
  const dc = new DrawContext();
  dc.size = new Size(width, height);
  dc.opaque = false;
  dc.setFillColor(hexA("#ffffff", 0.25));
  dc.fillRect(new Rect(0, 0, width, height));
  dc.setFillColor(color);
  dc.fillRect(new Rect(0, 0, Math.max(1, width * p), height));
  const img = dc.getImage();
  const el = w.addImage(img);
  el.imageSize = new Size(width, height);
}

function lockRect(w, st) {
  w.setPadding(0, 1, 0, 1);
  const a = w.addText((st.header || "").toUpperCase());
  a.font = Font.semiboldSystemFont(10);
  a.textOpacity = 0.66;
  a.lineLimit = 1;
  a.minimumScaleFactor = 0.6;
  const b = w.addText(st.subject || "Расписание 8Г");
  b.font = Font.boldSystemFont(15);
  b.lineLimit = 1;
  b.minimumScaleFactor = 0.6;
  w.addSpacer(2);
  const c = w.addText(st.countdown_text + (st.time ? " · до " + st.time : ""));
  c.font = Font.mediumSystemFont(12);
  c.lineLimit = 1;
  c.minimumScaleFactor = 0.7;
  if (CONFIG.showNext && st.next_text) {
    w.addSpacer(1);
    const d = w.addText(st.next_text);
    d.font = Font.systemFont(9);
    d.textOpacity = 0.6;
    d.lineLimit = 1;
    d.minimumScaleFactor = 0.6;
  }
  addBar(w, st.progress || 0, hexA("#ffffff", 0.9), 155, 2);
}

function lockCircle(w, st) {
  w.addAccessoryWidgetBackground = true;
  w.setPadding(0, 0, 0, 0);
  const a = w.addText((st.header || "").split(" · ")[0]);
  a.font = Font.semiboldSystemFont(8);
  a.textOpacity = 0.7;
  a.lineLimit = 1;
  a.minimumScaleFactor = 0.5;
  w.addSpacer(1);
  const b = w.addText(st.countdown === null || st.countdown === undefined ? "—" : String(st.countdown));
  b.font = Font.boldSystemFont(26);
  b.lineLimit = 1;
  b.minimumScaleFactor = 0.5;
  w.addSpacer(1);
  const c = w.addText(st.countdown === null ? "" : "мин");
  c.font = Font.systemFont(8);
  c.textOpacity = 0.7;
}

function homeWidget(w, st, fam) {
  const p = palette();
  const g = new LinearGradient();
  g.colors = [new Color(p.bg1), new Color(p.bg2)];
  g.locations = [0, 1];
  w.backgroundGradient = g;
  w.cornerRadius = 20;
  w.setPadding(15, 15, 15, 15);
  const top = w.addText((st.header || "").toUpperCase());
  top.font = Font.semiboldSystemFont(10);
  top.textColor = new Color(p.muted);
  top.lineLimit = 1;
  w.addSpacer(6);
  const subj = w.addText(st.subject || "Расписание 8Г");
  subj.font = Font.boldSystemFont(fam === "small" ? 16 : 20);
  subj.textColor = new Color(p.fg);
  subj.lineLimit = 1;
  subj.minimumScaleFactor = 0.6;
  w.addSpacer(3);
  const cd = w.addText(st.countdown_text + "  " + st.label);
  cd.font = Font.boldSystemFont(fam === "small" ? 19 : 26);
  cd.textColor = ACCENT;
  cd.lineLimit = 1;
  cd.minimumScaleFactor = 0.6;
  if (fam !== "small") {
    const s = w.addText(st.time ? "в " + st.time + (st.room_text ? " · " + st.room_text : "") : "");
    s.font = Font.systemFont(11);
    s.textColor = new Color(p.muted);
  }
  addBar(w, st.progress || 0, ACCENT, fam === "small" ? 130 : 280, 4);
  if (CONFIG.showNext && st.next_text) {
    w.addSpacer(5);
    const n = w.addText(st.next_text);
    n.font = Font.systemFont(10);
    n.textColor = new Color(p.muted);
    n.lineLimit = 1;
    n.minimumScaleFactor = 0.6;
  }
}

function noData() {
  const w = new ListWidget();
  w.url = CONFIG.site;
  w.addSpacer();
  const t = w.addText("Нет данных");
  t.font = Font.boldSystemFont(14);
  t.centerAlignText();
  const s = w.addText("Проверьте интернет");
  s.font = Font.systemFont(10);
  s.textOpacity = 0.65;
  s.centerAlignText();
  w.addSpacer();
  w.refreshAfterDate = new Date(Date.now() + 5 * 60000);
  return w;
}

const st = await loadStatus();
const fam = config.widgetFamily || "medium";
let w;
if (!st) {
  w = noData();
} else {
  w = new ListWidget();
  w.url = CONFIG.site;
  if (fam === "accessoryRectangular") lockRect(w, st);
  else if (fam === "accessoryCircular") lockCircle(w, st);
  else if (fam === "accessoryInline") {
    const t = w.addText(st.cls + " · " + (st.subject || "") + " · " + st.countdown_text);
    t.font = Font.mediumSystemFont(12);
  } else homeWidget(w, st, fam);
  w.refreshAfterDate = new Date(Date.now() + Math.max(1, CONFIG.refreshMin) * 60000);
}
if (config.runsInWidget) Script.setWidget(w);
else {
  if (fam === "accessoryRectangular" || fam === "accessoryCircular") await w.presentMedium();
  else await w.presentMedium();
}
Script.complete();
'''


def _kwgt_widget(cfg):
    o = cfg["opts"]
    accent = o["accent"].upper().replace("#", "")
    accent = "#FF" + accent
    if o["theme"] == "dark":
        bg, fg, muted, track = "#F211141C", "#FFFFFFFF", "#FF9AA3B2", "#33FFFFFF"
    elif o["theme"] == "light":
        bg, fg, muted, track = "#F2F4F6FB", "#FF111827", "#FF6B7280", "#22000000"
    else:
        bg = "$if(si(darkmode), #F211141C, #F2F4F6FB)$"
        fg = "$if(si(darkmode), #FFFFFFFF, #FF111827)$"
        muted = "$if(si(darkmode), #FF9AA3B2, #FF6B7280)$"
        track = "$if(si(darkmode), #33FFFFFF, #22000000)$"
    base = cfg["api"]
    fields = {
        "header": "header", "subject": "subject", "countdown_text": "countdown_text",
        "sub_text": "sub_text", "next_text": "next_text", "progress": "progress",
    }
    globals_list = {}
    for i, (name, field) in enumerate(fields.items(), start=1):
        globals_list[name] = {"index": i, "type": "TEXT", "title": name,
                              "global_formula": f'$wg("{base}", json, .{field})$'}
    for i, (name, val) in enumerate((("bg", bg), ("fg", fg), ("muted", muted), ("track", track), ("accent", accent)), start=20):
        d = {"index": i, "type": "COLOR", "title": name}
        if val.startswith("$"):
            d["global_formula"] = val
        else:
            d["value"] = val
        globals_list[name] = d

    def txt(expr, size, color, y, w=650, title=None):
        return {"internal_type": "TextModule", "text_expression": expr, "text_size": size,
                "text_align": "CENTER", "text_width": w, "text_height": size * 1.6,
                "position_offset_y": y, "internal_toggles": {"paint_color": 100},
                "internal_globals": {"paint_color": color},
                **({"internal_title": title} if title else {})}

    items = [
        {"internal_type": "ShapeModule", "shape_type": "RECT", "shape_width": 720,
         "shape_height": 360, "shape_corners": 32, "internal_toggles": {"paint_color": 100},
         "internal_globals": {"paint_color": "bg"},
         "internal_events": [{"type": "SINGLE_TAP", "action": "KUSTOM_ACTION",
                              "kustom_action": "TEXT_UPDATE"}]},
        txt("$tc(up, gv(header))$", 21, "muted", -128, title="Header"),
        txt("[b]$gv(subject)$[/b]", 44, "fg", -68, title="Subject"),
        txt("[b]$gv(countdown_text)$[/b]", 58, "accent", 12, title="Countdown"),
        txt("$gv(sub_text)$", 21, "muted", 76, title="Sub"),
        txt("$gv(next_text)$", 17, "muted", 121, w=640, title="Next"),
    ]
    if o["progress"]:
        items += [
            {"internal_type": "OverlapLayerModule", "position_offset_y": 154,
             "viewgroup_items": [
                 {"internal_type": "ShapeModule", "shape_type": "RECT", "shape_width": 620,
                  "shape_height": 8, "shape_corners": 4,
                  "internal_toggles": {"paint_color": 100},
                  "internal_globals": {"paint_color": "track"}},
                 {"internal_type": "ShapeModule", "shape_type": "RECT", "shape_width": 620,
                  "shape_height": 8, "shape_corners": 4, "position_anchor": "CENTERLEFT",
                  "paint_color": accent,
                  "internal_formulas": {"shape_width": "$gv(progress)*620$"}},
             ]},
        ]
    preset = {
        "preset_info": {"version": 13, "title": f"Расписание {cfg['cls']}", "author": "Расписание 8Г",
                        "description": "Обратный отсчёт до конца урока. Нажмите, чтобы обновить.",
                        "email": "", "width": 720, "height": 360, "features": "",
                        "release": 0, "locked": False, "pflags": 0, "xscreens": 0, "yscreens": 0},
        "preset_root": {"internal_type": "RootLayerModule", "globals_list": globals_list,
                        "config_scale_value": 100.0, "viewgroup_items": items},
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("preset.json", json.dumps(preset, ensure_ascii=False, indent=2))
    return buf.getvalue()


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

    def _send(self, code, body, ctype, cache="no-store", head=False, etag=None, gz=None, extra=None):
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
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _not_modified(self, etag, cache):
        self.send_response(304)
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, code, obj, head=False):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return self._send(code, body, "application/json; charset=utf-8", head=head)

    def _read_json(self, limit=8192):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0 or n > limit:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return None

    def _handle(self, head=False):
        u = urlparse(self.path)
        path = u.path
        try:
            if path == "/api/push/key":
                return self._json(200, {"key": VAPID_PUBLIC_KEY, "supported": push_ready()}, head=head)
            if path == "/api/schedule":
                force = parse_qs(u.query).get("force", ["0"])[0] == "1"
                return self._json(200, build_payload(force), head=head)
            if path == "/api/widget":
                return self._json(200, widget_status(_widget_opts(parse_qs(u.query))), head=head)
            if path in ("/api/widget/ios", "/api/widget/kwgt"):
                opts = _widget_opts(parse_qs(u.query))
                flags = f"full={int(opts['full'])}&room={int(opts['room'])}&next={int(opts['next'])}&progress={int(opts['progress'])}"
                cfg = {"api": SELF_URL.rstrip("/") + "/api/widget?" + flags,
                       "site": SELF_URL.rstrip("/"), "cls": CLASS_CODE.upper(),
                       "theme": opts["theme"], "accent": opts["accent"],
                       "showRoom": opts["room"], "showNext": opts["next"],
                       "showProgress": opts["progress"], "full": opts["full"],
                       "refreshMin": 1, "opts": opts}
                if path.endswith("/ios"):
                    data = _ios_widget(cfg).encode("utf-8")
                    name, ctype = "raspisanie-8g-iphone.js", "application/javascript; charset=utf-8"
                else:
                    data = _kwgt_widget(cfg)
                    name, ctype = "raspisanie-8g-android.kwgt", "application/octet-stream"
                return self._send(200, data, ctype, head=head,
                                  extra={"Content-Disposition": f'attachment; filename="{name}"'})
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

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/push/subscribe":
                data = self._read_json() or {}
                sub = data.get("subscription") or data
                if not valid_subscription(sub):
                    return self._json(400, {"ok": False, "error": "bad subscription"})
                count = add_subscription(sub)
                return self._json(200, {"ok": True, "count": count})
            if path == "/api/push/unsubscribe":
                data = self._read_json() or {}
                endpoint = data.get("endpoint")
                if isinstance(endpoint, str) and endpoint:
                    remove_subscription(endpoint)
                return self._json(200, {"ok": True})
            if path == "/api/push/test":
                data = self._read_json() or {}
                sub = data.get("subscription") or data
                if not push_ready():
                    return self._json(503, {"ok": False, "error": "push disabled"})
                if not valid_subscription(sub):
                    return self._json(400, {"ok": False, "error": "bad subscription"})
                try:
                    _send_push(sub, {"title": "8Г · Уведомления включены",
                                     "body": "Изменения расписания придут на этот телефон.",
                                     "tag": "test", "url": "/"})
                except Exception as e:
                    code = getattr(getattr(e, "response", None), "status_code", None)
                    print(f"[push] test: {type(e).__name__}: {str(e)[:200]}")
                    return self._json(502, {"ok": False, "error": f"push {code or 'error'}"})
                return self._json(200, {"ok": True})
            return self._send(404, "Не найдено".encode("utf-8"), "text/plain; charset=utf-8")
        except Exception:
            try:
                self._json(500, {"ok": False, "error": "server error"})
            except Exception:
                pass


def watcher(interval):
    """Сам проверяет таблицу, чтобы уведомления не ждали открытия сайта."""
    while True:
        time.sleep(interval)
        try:
            refresh(force=True)
        except Exception as e:
            print(f"[watch] {type(e).__name__}: {e}")


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
    load_push()
    if not push_ready():
        print("[warn] push-уведомления выключены: нет pywebpush или VAPID-ключей")
    threading.Thread(target=refresh, daemon=True).start()
    try:
        watch_seconds = int(os.getenv("WATCH_SECONDS", "180"))
    except ValueError:
        watch_seconds = 180
    if watch_seconds > 0:
        threading.Thread(target=watcher, args=(watch_seconds,), daemon=True).start()
    if os.getenv("KEEPALIVE", "1") != "0":
        threading.Thread(target=keepalive, daemon=True).start()
    port = int(os.getenv("PORT", "8000"))
    print(f"Расписание {CLASS_CODE.upper()}: http://0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
