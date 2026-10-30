#!/usr/bin/env bash
# Установка зеркала «Расписание 8Г» на PythonAnywhere (бесплатный тариф).
# Запускать в Bash-консоли PythonAnywhere:  bash pa_setup.sh
set -e

REPO="https://github.com/Nikita2272282299/school-schedule.git"
DIR="$HOME/school-schedule"

if [ -d "$DIR/.git" ]; then
  echo "→ обновляю существующую копию"
  cd "$DIR"
  git pull --ff-only
else
  echo "→ клонирую репозиторий"
  git clone "$REPO" "$DIR"
  cd "$DIR"
fi

echo "→ создаю виртуальное окружение"
python3.10 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
pip install "pywebpush>=2.0,<3" -q

echo
echo "Готово. Осталось:"
echo "  1) Web → Add a new web app → Manual configuration → Python 3.10"
echo "     Source code:     $DIR"
echo "     Virtualenv:      $DIR/.venv"
echo "  2) В WSGI-файле написать:"
echo "       import sys"
echo "       sys.path.insert(0, '$DIR')"
echo "       from pa_wsgi import application"
echo "  3) Нажать Reload."
