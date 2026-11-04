#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Зеркало «Расписание 8Г» на PythonAnywhere (WSGI).

Бесплатный тариф PythonAnywhere не умеет запускать собственный HTTP-сервер
(http.server) и не даёт «always-on tasks», поэтому app.py подключается как
WSGI-приложение: вся логика (таблица, кэш, push) остаётся в app.py, а здесь
только маршрутизация.

Настройка (один раз):
  1. Зарегистрироваться на pythonanywhere.com (Free).
  2. В Bash-консоли:  git clone <репозиторий> school-schedule
  3. Web → Add a new web app → Manual configuration → Python 3.10
     Source code:  /home/ИМЯ/school-schedule
     WSGI file:    заменить содержимое на:
         import sys
         sys.path.insert(0, '/home/ИМЯ/school-schedule')
         from pa_wsgi import application
  4. Virtualenv: /home/ИМЯ/school-schedule/.venv  (pip install pywebpush)
  5. Нажать Reload.

Адрес сайта: https://ИМЯ.pythonanywhere.com
Если имя пользователя не schedule8g — поправьте SITE_URL ниже.
"""
import gzip
import json
import os
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# --- адрес этого зеркала (нужен для push-уведомлений) -----------------------
SITE_URL = os.environ.get("SELF_URL") or "https://schedule8g.pythonanywhere.com"
os.environ["SELF_URL"] = SITE_URL
# На PythonAnywhere не нужен «будильник» Render и фоновый watcher:
os.environ.setdefault("KEEPALIVE", "0")
os.environ.setdefault("WATCH_SECONDS", "0")

import app  # noqa: E402  (импорт после настройки окружения)

app.load_store()
app.load_push()

# Прогреваем кэш в фоне, чтобы первый посетитель не ждал Google.
def _warm():
    try:
        app.refresh(force=True)
    except Exception as e:  # сеть/доступ к таблице
        print(f"[warm] {type(e).__name__}: {e}")


threading.Thread(target=_warm, daemon=True).start()

REASONS = {200: "OK", 304: "Not Modified", 400: "Bad Request", 404: "Not Found",
           405: "Method Not Allowed", 500: "Internal Server Error", 503: "Service Unavailable"}


def _respond(start_response, code, body, ctype, cache="no-store", etag=None, environ=None):
    if isinstance(body, str):
        body = body.encode("utf-8")
    headers = [
        ("Content-Type", ctype),
        ("Cache-Control", cache),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
    ]
    if etag:
        headers.append(("ETag", etag))
    ae = ((environ or {}).get("HTTP_ACCEPT_ENCODING") or "").lower()
    compressible = (ctype.startswith("text/") or "json" in ctype
                    or "javascript" in ctype or "svg" in ctype)
    if environ and len(body) > 1024 and compressible and "gzip" in ae:
        body = gzip.compress(body, 6)
        headers.append(("Content-Encoding", "gzip"))
        headers.append(("Vary", "Accept-Encoding"))
    headers.append(("Content-Length", str(len(body))))
    start_response(f"{code} {REASONS.get(code, 'OK')}", headers)
    return [body]


def _json(start_response, obj, code=200, environ=None):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return _respond(start_response, code, body, "application/json; charset=utf-8", environ=environ)


def _read_json(environ, limit=8192):
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return None
    if n <= 0 or n > limit:
        return None
    try:
        return json.loads(environ["wsgi.input"].read(n).decode("utf-8"))
    except Exception:
        return None


def _static(start_response, name, ctype, cache, environ):
    f = BASE / name
    if not f.is_file():
        return _respond(start_response, 404, b"not found", "text/plain", environ=environ)
    raw, gz = app.static_cached(f)
    etag = f'W/"{int(f.stat().st_mtime)}-{len(raw)}"'
    if environ.get("HTTP_IF_NONE_MATCH") == etag:
        start_response("304 Not Modified", [("ETag", etag), ("Cache-Control", cache),
                                            ("Content-Length", "0")])
        return [b""]
    return _respond(start_response, 200, raw, ctype, cache=cache, etag=etag, environ=environ)


from cors import with_cors


@with_cors
def application(environ, start_response):
    """Точка входа WSGI."""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    if method == "HEAD":
        # Считаем как GET, но тело не отдаём (Content-Length: 0 — требование uWSGI).
        def head_start(status, headers, exc_info=None):
            headers = [(k, "0") if k.lower() == "content-length" else (k, v)
                       for k, v in headers if k.lower() != "content-encoding"]
            return start_response(status, headers, exc_info)

        _dispatch("GET", environ, head_start)
        return [b""]
    return _dispatch(method, environ, start_response)


def _dispatch(method, environ, start_response):
    u = urlparse(environ.get("PATH_INFO") or "/")
    path = u.path

    try:
        if method == "GET":
            if path == "/api/schedule":
                force = parse_qs(environ.get('QUERY_STRING', '')).get("force", ["0"])[0] == "1"
                return _json(start_response, app.build_payload(force), environ=environ)
            if path == "/api/push/key":
                return _json(start_response, {"key": app.VAPID_PUBLIC_KEY,
                                              "supported": app.push_ready()}, environ=environ)
            if path == "/api/diag":
                return _json(start_response, {
                    "ok": app._state.get("ok"),
                    "error": app._state.get("error"),
                    "updated": app._state.get("updated"),
                    "days": len(app._store),
                    "push": app.push_ready(),
                    "server_time": int(app.time.time()),
                }, environ=environ)
            if path == "/healthz":
                return _respond(start_response, 200, b"ok", "text/plain", environ=environ)
            if path in app.STATIC:
                name, ctype, cache = app.STATIC[path]
                return _static(start_response, name, ctype, cache, environ)
            return _respond(start_response, 404, "Не найдено".encode("utf-8"),
                            "text/plain; charset=utf-8", environ=environ)

        if method == "POST":
            if path == "/api/push/subscribe":
                data = _read_json(environ) or {}
                sub = data.get("subscription") or data
                if not app.valid_subscription(sub):
                    return _json(start_response, {"ok": False, "error": "bad subscription"},
                                 400, environ)
                count = app.add_subscription(sub)
                return _json(start_response, {"ok": True, "count": count}, environ=environ)
            if path == "/api/push/unsubscribe":
                data = _read_json(environ) or {}
                endpoint = data.get("endpoint")
                if isinstance(endpoint, str) and endpoint:
                    app.remove_subscription(endpoint)
                return _json(start_response, {"ok": True}, environ=environ)
            if path == "/api/push/test":
                data = _read_json(environ) or {}
                sub = data.get("subscription") or data
                if not app.push_ready():
                    return _json(start_response, {"ok": False, "error": "push disabled"},
                                 503, environ)
                if not app.valid_subscription(sub):
                    return _json(start_response, {"ok": False, "error": "bad subscription"},
                                 400, environ)
                try:
                    app._send_push(sub, {"title": "8Г · Уведомления включены",
                                         "body": "Изменения расписания придут на этот телефон.",
                                         "tag": "test", "url": "/"})
                except Exception as e:
                    code = getattr(getattr(e, "response", None), "status_code", None)
                    print(f"[push] test: {type(e).__name__}: {str(e)[:200]}")
                    return _json(start_response, {"ok": False, "error": f"push {code or 'error'}"},
                                 502, environ)
                return _json(start_response, {"ok": True}, environ=environ)
            return _respond(start_response, 404, "Не найдено".encode("utf-8"),
                            "text/plain; charset=utf-8", environ=environ)

        return _respond(start_response, 405, b"method not allowed", "text/plain", environ=environ)
    except Exception as e:
        print(f"[wsgi] {type(e).__name__}: {e}")
        try:
            return _respond(start_response, 500, b"error", "text/plain", environ=environ)
        except Exception:
            return [b"error"]
