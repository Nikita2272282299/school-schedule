# Расписание 8Г: GitHub Pages + отдельный API

Это выделенная копия сайта. Исходные файлы в корне сохранены для отката и старого Render; остальные проекты сюда не включены.

## Локальный запуск

Python 3.10+ (проверено на 3.12):

```text
py -m pip install -r requirements.txt
py app.py
```

Без pywebpush сайт работает, но отправка push недоступна.
Данные сохраняются в `data/` (или `DATA_DIR`), папка исключена из Git.
Не переносите ключи и подписки в публичные файлы. Историю `days_store.json` при переносе сервера скопируйте в DATA_DIR отдельно, не через Git.

## API вне Render

GitHub Pages не запускает Python. Нужен отдельный HTTPS-сервер с постоянным диском.
Адрес schedule8g.pythonanywhere.com на момент проверки возвращал заглушку 404: это НЕ рабочее зеркало.
На PythonAnywhere настройте веб-приложение WSGI, виртуальное окружение с requirements.txt и путь к этой папке. Пример WSGI:

```python
import os
import sys
sys.path.insert(0, '/home/USERNAME/school-schedule/school-schedule')
os.environ['DATA_DIR'] = '/home/USERNAME/schedule-private'
os.environ['SELF_URL'] = 'https://USERNAME.pythonanywhere.com'
os.environ['ALLOWED_ORIGINS'] = 'https://nikita2272282299.github.io'
from pa_wsgi import application
```

Проверить `/healthz`, `/api/diag`, `/api/schedule?force=1`, доступ к Google-таблице и Web Push. Доступность домена из РФ не гарантируется: проверить без VPN с целевых устройств.
Бесплатный WSGI-хостинг не обеспечивает постоянный фоновый watcher: для уведомлений без посетителей нужен разрешённый планировщик/постоянный процесс. Проверить ограничения тарифа перед выбором. Текущий watcher работает при запуске `app.py`, но не при WSGI.

## Подключение Pages

В `config.js` указать реальный адрес API, например `https://USERNAME.pythonanywhere.com` (без `/api`). Не указывать выдуманный или неработающий адрес. Пустая строка предназначена для совместного локального размещения.
Сервер API должен использовать `pa_wsgi.application` с ограниченным CORS.
В репозитории `Nikita2272282299/school-schedule`: Settings → Pages → Source → GitHub Actions.
Workflow `.github/workflows/schedule-pages.yml` проверяет код, собирает только 8 разрешённых публичных файлов и развёртывает Pages.
Ожидаемый адрес: https://nikita2272282299.github.io/school-schedule/

```text
py -m unittest discover -s school-schedule/tests
py school-schedule/build_pages.py
```

Команды выше запускаются из корня репозитория. `pages-dist/` — автоматически создаваемый артефакт, не исходники.
После публикации проверить день/неделю, обновление, темы, ссылку «Поделиться», офлайн после первого посещения, установку на телефон и уведомление с переходом на конкретный день. Старые подписки привязаны к домену Render: на Pages потребуется включить уведомления заново.
Render не отключать, пока сайт и API не проверены без VPN.
