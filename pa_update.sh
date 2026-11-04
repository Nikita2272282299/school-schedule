#!/usr/bin/env bash
# Обновление «основы» на PythonAnywhere до версии из GitHub.
#
# Запуск в Bash-консоли PythonAnywhere (Consoles → Bash), одной строкой:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Nikita2272282299/school-schedule/main/pa_update.sh)
#
# Скрипт НЕ трогает data/ (историю дней, VAPID-ключи и подписки на push).
set -euo pipefail

RAW="https://raw.githubusercontent.com/Nikita2272282299/school-schedule/main/school-schedule/pa-dist"
FILES="index.html sw.js config.js offline-data.js manifest.json app.py pa_wsgi.py cors.py"
FONTS="manrope-cyrillic-400-800-normal.woff2 manrope-latin-400-800-normal.woff2"

# Каталог приложения берём из WSGI-конфига, иначе ищем pa_wsgi.py в домашней папке.
WSGI=$(ls -1 /var/www/*_pythonanywhere_com_wsgi.py 2>/dev/null | head -n 1 || true)
APPDIR=""
if [ -n "$WSGI" ] && [ -f "$WSGI" ]; then
  APPDIR=$(grep -oE "['\"]/home/[^'\"]+['\"]" "$WSGI" | tr -d "'\"" | head -n 1 || true)
fi
if [ -z "$APPDIR" ] || [ ! -f "$APPDIR/pa_wsgi.py" ]; then
  APPDIR=$(find "$HOME" -name pa_wsgi.py -not -path '*/.venv/*' -printf '%h\n' 2>/dev/null | head -n 1 || true)
fi
if [ -z "$APPDIR" ] || [ ! -f "$APPDIR/pa_wsgi.py" ]; then
  echo "Не нашёл каталог веб-приложения. Укажите его явно: PA_APP_DIR=/home/ИМЯ/путь bash pa_update.sh"
  exit 1
fi

echo "→ обновляю $APPDIR"
cd "$APPDIR"
for f in $FILES; do
  curl -fsSL "$RAW/$f" -o "$f"
  echo "   $f"
done
mkdir -p assets/fonts
for f in $FONTS; do
  curl -fsSL "$RAW/assets/fonts/$f" -o "assets/fonts/$f"
  echo "   assets/fonts/$f"
done

# touch WSGI-файла перезапускает веб-приложение без кнопки Reload.
if [ -n "$WSGI" ] && [ -f "$WSGI" ]; then
  touch "$WSGI"
  echo "→ веб-приложение перезапущено"
else
  echo "→ WSGI-файл не найден: нажмите Reload в панели Web"
fi

echo "→ готово. Проверка:"
echo "   curl -s https://ИМЯ.pythonanywhere.com/healthz"
echo "   curl -s -o /dev/null -w '%{http_code}' https://ИМЯ.pythonanywhere.com/offline-data.js"
