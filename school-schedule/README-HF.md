---
title: Расписание 8Г
emoji: 📅
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
---

# Расписание 8Г

Живое школьное расписание: сайт и API в одном приложении.

- Сайт: `index.html` + PWA (офлайн, установка на телефон, темы)
- API: `/api/schedule`, `/healthz`, push-уведомления (`/api/push/*`)
- Данные: Google-таблица → CSV; история дней хранится в `data/`

Порт 7860 задаёт HF; переменные окружения — в Dockerfile.
