"""AI-компилятор расписания для GitHub Actions (без тяжёлых весов в репозитории).

Как работает:
  1. Считает SHA-256 хэш сырой таблицы `rows`. Если таблица не менялась —
     переиспользует готовый `ai-schedule.json` и не тратит лимиты.
  2. Когда появляется новое расписание или правки, отправляет компактное
     представление таблицы в лёгкую нейросеть:
       - GitHub Models (`GITHUB_TOKEN` + `permissions: models: read`, по умолчанию
         `openai/gpt-4o-mini`, можно сменить через `AI_MODEL`);
       - либо любой OpenAI-совместимый endpoint (`AI_API_URL` + `AI_API_KEY`,
         например локальная Ollama / Groq / Gemini).
  3. Нейросеть сама распознаёт даты, классы, уроки и отделяет объявления/заметки
     (вроде «с 8.50 в 405 кабинете») от настоящих уроков.
  4. Результат строго валидируется; при недоступности нейросети или ошибке
     автоматически срабатывает детерминированный парсер, чтобы расписание
     никогда не сломалось.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import app

GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

# Фразы, которые в таблице пишут в ячейке урока, но это объявление/заметка, а не урок.
NOTE_PATTERNS = (
    re.compile(r"^\s*с\s+\d{1,2}[:.]\d{2}\b", re.I),
    re.compile(r"^\s*к\s+\d{1,2}[:.]\d{2}\b", re.I),
    re.compile(r"^\s*(приходить|приходим|сбор|линейка|медосмотр|экскурси|собрание|родительск)", re.I),
    re.compile(r"\bв\s+\d{2,3}\s*каб(?:инет[еа]?)?\.?\s*$", re.I),
)

SYSTEM_PROMPT = (
    "Ты компактный парсер школьного расписания из Google Таблиц. "
    "Твоя задача — по строкам таблицы составить чистый JSON расписания для всех классов.\n"
    "Правила:\n"
    "1. Выведи СТРОГО валидный JSON без markdown и пояснений.\n"
    "2. Формат ответа:\n"
    '{"days":[{"date":"YYYY-MM-DD","weekday":"Понедельник","classes":{"8Г":{"notes":[],"lessons":[{"n":"1","time":"8:00-8:40","raw":"Информатика / Труд 423"}]}}}]}\n'
    "3. НЕ выдумывай уроки, которых нет в таблице. Сохраняй точные номера уроков, время, кабинеты, деление на группы и профиль/базу (П/Б). "
    "При этом ИСПРАВЛЯЙ очевидные опечатки, склеенные с номером кабинета слова, разрядку буквами и кривые сокращения "
    "(например: «аргл 319» -> «Английский 319», «англ319» -> «Английский 319», «Т Р Е Н И Н Г» -> «Тренинг», «матматика 207» -> «Математика 207», «русскй 409» -> «Русский язык 409», «физкльтура» -> «Физкультура»).\n"
    "4. Если в строке записано объявление/заметка, а не урок (например «с 8.50 в 405 кабинете», «приходить ко 2 уроку», «медосмотр»), "
    "НЕ включай его в lessons — перенеси в массив notes этого класса (с заглавной буквы, аккуратно оформив время через двоеточие).\n"
    "5. Пустые ячейки в начале и конце дня отбрасывай. Пустые ячейки между уроками (окна) можно не удалять или оставлять raw=\"\"."
)


def is_note_cell(text):
    """Определяет, является ли ячейка текстовой заметкой/объявлением, а не уроком."""
    s = re.sub(r"\s+", " ", (text or "")).strip()
    if not s:
        return False
    return any(p.search(s) for p in NOTE_PATTERNS)


def normalize_note(text):
    s = re.sub(r"\s+", " ", (text or "")).strip()
    s = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", s)
    return (s[0].upper() + s[1:]) if s else ""


def sheet_hash(rows):
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def find_classes(rows):
    found = []
    seen = set()
    for row in rows:
        norms = [app.norm(c) for c in row]
        cls_in_row = [c for c in norms if app.CLASS_RE.match(c)]
        if len(cls_in_row) >= 3:
            for c in cls_in_row:
                up = c.upper()
                if up not in seen:
                    seen.add(up)
                    found.append(up)
    return found


def build_rules_schedule(rows, today=None):
    """Детерминированный разбор всех классов + отделение заметок от уроков."""
    today = today or app.now_perm().date()
    classes = find_classes(rows)
    days_out = {}

    for cls in classes:
        parsed_days, found = app.parse_sheet(rows, cls, today)
        if not found:
            continue
        for iso, d in parsed_days.items():
            day_entry = days_out.setdefault(
                iso,
                {"date": iso, "weekday": d["weekday"], "classes": {}},
            )
            notes = list(d.get("notes", []))
            lessons = []
            for l in d.get("lessons", []):
                raw = (l.get("raw") or "").strip()
                if raw and is_note_cell(raw):
                    note = normalize_note(raw)
                    if note and note not in notes:
                        notes.append(note)
                    continue
                lessons.append({
                    "n": str(l.get("n", "")),
                    "time": l.get("time", ""),
                    "raw": raw,
                })
            while lessons and not lessons[-1]["raw"]:
                lessons.pop()
            while lessons and not lessons[0]["raw"]:
                lessons.pop(0)
            if lessons or notes:
                day_entry["classes"][cls] = {"notes": notes, "lessons": lessons}

    return {k: v for k, v in sorted(days_out.items()) if v["classes"]}


def compact_rows_for_prompt(rows, today):
    """Сжимает строки таблицы в компактный текст, чтобы уложиться в контекст слабой нейронки."""
    lines = [f"Сегодня (Пермь): {today.isoformat()}"]
    for idx, row in enumerate(rows):
        non_empty = [(i, re.sub(r"\s+", " ", str(c or "")).strip()) for i, c in enumerate(row)]
        non_empty = [(i, c) for i, c in non_empty if c]
        if not non_empty:
            continue
        joined = " | ".join(f"[{i}]{c}" for i, c in non_empty)
        lines.append(f"R{idx}: {joined}")
    return "\n".join(lines)


def call_ai(rows, today):
    """Вызывает Groq, GitHub Models или кастомный OpenAI-совместимый API. Возвращает (data, source) или (None, reason)."""
    if os.getenv("AI_DISABLED", "").strip() in ("1", "true", "yes"):
        return None, "disabled"

    url, token, model = _resolve_ai_endpoint()
    if not url or not token:
        return None, "no_token"

    prompt_text = compact_rows_for_prompt(rows, today)
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "school-schedule-ai/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = int(os.getenv("AI_TIMEOUT", "45"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        # На случай, если модель обернула JSON в ```json ... ```
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            return None, "invalid_json"
        parsed = json.loads(m.group(0))
        return parsed, f"ai:{model}"
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, ValueError, TimeoutError) as e:
        return None, f"error:{type(e).__name__}:{e}"


def merge_and_validate(ai_data, rules_days):
    """Валидирует вывод нейросети и дополняет пропущенные классы из детерминированного парсера."""
    if not isinstance(ai_data, dict):
        return rules_days, False

    raw_days = ai_data.get("days")
    if isinstance(raw_days, dict):
        day_items = list(raw_days.values())
    elif isinstance(raw_days, list):
        day_items = raw_days
    else:
        return rules_days, False

    validated = {}
    used_ai = False
    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for d in day_items:
        if not isinstance(d, dict):
            continue
        iso = str(d.get("date") or "").strip()
        if not iso_re.match(iso):
            continue
        classes_in = d.get("classes")
        if not isinstance(classes_in, dict):
            continue

        day_classes = {}
        for raw_cls, entry in classes_in.items():
            cls = app.norm(str(raw_cls)).upper()
            if not app.CLASS_RE.match(cls.lower()):
                continue
            if not isinstance(entry, dict):
                continue
            raw_lessons = entry.get("lessons")
            if not isinstance(raw_lessons, list):
                continue

            clean_lessons = []
            notes = []
            for note in (entry.get("notes") or []):
                nt = normalize_note(str(note))
                if nt and nt not in notes:
                    notes.append(nt)

            for l in raw_lessons:
                if not isinstance(l, dict):
                    continue
                num = str(l.get("n", l.get("num", ""))).strip()
                tm = app.clean_time(str(l.get("time", ""))) or (app.BELLS.get(int(num), "") if num.isdigit() else "")
                raw = re.sub(r"\s+", " ", str(l.get("raw", "") or "")).strip()
                if not raw and l.get("subject"):
                    raw = (str(l.get("subject")) + " " + str(l.get("room") or "")).strip()
                if raw and is_note_cell(raw):
                    nt = normalize_note(raw)
                    if nt and nt not in notes:
                        notes.append(nt)
                    continue
                if num or tm or raw:
                    clean_lessons.append({"n": num, "time": tm, "raw": raw})

            while clean_lessons and not clean_lessons[-1]["raw"]:
                clean_lessons.pop()
            while clean_lessons and not clean_lessons[0]["raw"]:
                clean_lessons.pop(0)

            if clean_lessons or notes:
                day_classes[cls] = {"notes": notes, "lessons": clean_lessons}
                used_ai = True

        if day_classes:
            weekday = str(d.get("weekday") or "").strip()
            if not weekday and iso in rules_days:
                weekday = rules_days[iso]["weekday"]
            validated[iso] = {"date": iso, "weekday": weekday, "classes": day_classes}

    if not used_ai:
        return rules_days, False

    # Дополняем классы/дни, которые нейросеть могла пропустить, из rules_days.
    for iso, rday in rules_days.items():
        if iso not in validated:
            validated[iso] = rday
            continue
        for cls, rentry in rday["classes"].items():
            if cls not in validated[iso]["classes"]:
                validated[iso]["classes"][cls] = rentry

    return dict(sorted(validated.items())), True


def compile_schedule(rows, out_path, today=None, force=False):
    """Компилирует расписание из rows и записывает ai-schedule.json. Возвращает итоговый dict."""
    out_path = Path(out_path)
    today = today or app.now_perm().date()
    h = sheet_hash(rows)

    if not force and out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if existing.get("sheet_hash") == h and existing.get("days"):
                print(f"[ai] Таблица не изменилась (hash {h[:8]}), использую кэш {out_path.name}")
                return existing
        except Exception:
            pass

    rules_days = build_rules_schedule(rows, today)
    ai_raw, ai_source = call_ai(rows, today)

    if ai_raw is not None:
        days, ok = merge_and_validate(ai_raw, rules_days)
        source = ai_source if ok else f"rules (fallback: invalid AI output)"
    else:
        days = rules_days
        source = f"rules ({ai_source})"

    result = {
        "updated": int(time.time()),
        "sheet_hash": h,
        "source": source,
        "days": days,
    }
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"[ai] Скомпилирован {out_path.name}: дней={len(days)}, источник={source}")
    return result


ASK_SYSTEM_PROMPT = (
    "Ты дружелюбный ИИ-помощник школьного расписания. Отвечай на русском языке, кратко и по делу.\n"
    "Используй ТОЛЬКО переданные данные расписания — не выдумывай уроки, классы и кабинеты.\n"
    "Если спрашивает учитель (по предмету или кабинету) — просматривай ВСЕ классы и группируй по кабинетам/времени, если их несколько.\n"
    "Если запрошенного дня (например, завтра) ещё нет в расписании — прямо скажи об этом и при необходимости приведи данные за последний доступный день."
)


def _resolve_ai_endpoint():
    api_url = os.getenv("AI_API_URL", "").strip()
    api_key = os.getenv("AI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gh_token = os.getenv("GITHUB_TOKEN", "").strip()
    model = os.getenv("AI_MODEL", "").strip()

    if api_url:
        return api_url, (api_key or groq_key or gh_token), (model or DEFAULT_MODEL)
    if groq_key:
        return "https://api.groq.com/openai/v1/chat/completions", groq_key, (model or "llama-3.1-8b-instant")
    if api_key or gh_token:
        return GITHUB_MODELS_URL, (api_key or gh_token), (model or DEFAULT_MODEL)
    return "", "", ""


def ask_ai(question, schedule_text="", class_code="", today_str=""):
    """Отвечает на свободный вопрос пользователя по расписанию через реальную нейросеть."""
    q = re.sub(r"\s+", " ", str(question or "")).strip()[:600]
    if not q:
        return None, "empty"
    url, token, model = _resolve_ai_endpoint()
    if not url or not token:
        return None, "no_token"

    ctx_parts = []
    if today_str:
        ctx_parts.append(f"Сейчас: {today_str}")
    if class_code:
        ctx_parts.append(f"Выбранный класс пользователя: {class_code}")
    if schedule_text:
        ctx_parts.append("Расписание:\n" + str(schedule_text)[:24000])
    user_msg = "\n\n".join(ctx_parts) + f"\n\nВопрос: {q}"

    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": ASK_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "school-schedule-ai/1.0",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = int(os.getenv("AI_TIMEOUT", "25"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        ans = (body["choices"][0]["message"]["content"] or "").strip()
        if not ans:
            return None, "empty_answer"
        return ans, model
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, ValueError, TimeoutError) as e:
        return None, f"error:{type(e).__name__}"
