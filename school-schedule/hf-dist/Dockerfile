# Расписание 8Г — Docker-Space для бесплатного Hugging Face Spaces.
# Локальная сборка не требуется: образ собирается на стороне HF.
FROM python:3.12-slim

WORKDIR /app

# pywebpush нужен только для push-уведомлений; остальное — стандартная библиотека Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html sw.js manifest.json config.js offline-data.js icon.svg icon-192.png icon-512.png apple-touch-icon.png ./
# Встроенная офлайн-копия и локальный шрифт — без них сайт не работает без сети.
RUN mkdir -p /app/assets/fonts
COPY assets/fonts/*.woff2 ./assets/fonts/

# HF ждёт приложение на порту 7860 и запускает контейнер от пользователя 1000.
# data/ — история дней, подписки push и VAPID-ключи (на бесплатном тарифе эфемерна).
# KEEPALIVE=0 — не пингуем старый адрес Render, он тут ни при чём.
ENV PORT=7860 \
    DATA_DIR=/app/data \
    KEEPALIVE=0
RUN mkdir -p /app/data && chown -R 1000:1000 /app

EXPOSE 7860
CMD ["python", "app.py"]
