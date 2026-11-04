"""Номер сборки для заголовка: число коммитов в репозитории.

Используется build_pages.py (публикация на GitHub Pages) и вручную:
    py school-schedule/version_stamp.py
"""
from pathlib import Path
import re
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent

TITLE_RE = re.compile(r'<title>Расписание 8Г[^<]*</title>')
VER_RE = re.compile(r"const APP_VER='\d+'")

TARGETS = ('index.html', 'school-schedule/index.html', 'school-schedule/pa-dist/index.html')


def build_number():
    """Число коммитов в HEAD или None, если git недоступен."""
    try:
        out = subprocess.run(['git', 'rev-list', '--count', 'HEAD'], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    n = out.stdout.strip()
    return int(n) if n.isdigit() else None


def stamp(path, number):
    """Пишет номер сборки в <title> и APP_VER. True, если файл изменился."""
    p = Path(path)
    src = p.read_text(encoding='utf-8')
    out = TITLE_RE.sub('<title>Расписание 8Г · версия %d</title>' % number, src)
    out = VER_RE.sub("const APP_VER='%d'" % number, out)
    if out == src:
        return False
    p.write_text(out, encoding='utf-8')
    return True


if __name__ == '__main__':
    n = build_number()
    if not n:
        raise SystemExit('номер сборки не определён: нет git или пустая история')
    for rel in TARGETS:
        p = ROOT / rel
        if p.exists():
            print('обновлён' if stamp(p, n) else 'без изменений', rel)
    print('версия сборки:', n)
