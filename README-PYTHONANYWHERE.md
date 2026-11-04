# Зеркало на PythonAnywhere (работает без VPN)

Основной сайт живёт на Render: бесплатный тариф «засыпает» через 15 минут без
посетителей, первый запуск занимает ~50 секунд, а сам домен в РФ открывается
не у всех. Поэтому делаем **полную копию** на PythonAnywhere — она всегда
включена, бесплатна и открывается без VPN.

Адрес зеркала: `https://ИМЯ.pythonanywhere.com`
(в коде уже прописано `https://schedule8g.pythonanywhere.com` — см. шаг 6).

---

## 1. Регистрация

1. Открыть <https://www.pythonanywhere.com/registration/register/beginner/>
2. Зарегистрировать бесплатный аккаунт (**Free**, карта не нужна).
3. Желательно взять имя **`schedule8g`** — тогда адрес совпадёт с тем, что уже
   прописан в коде. Если имя занято — берите любое и поправьте шаг 6.

## 2. Скачать проект (Bash-консоль)

На PythonAnywhere: **Consoles → Bash** и выполнить:

```bash
cd ~
git clone https://github.com/Nikita2272282299/school-schedule.git
cd school-schedule
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install "pywebpush>=2.0,<3"
```

Если репозиторий уже клонировали раньше:

```bash
cd ~/school-schedule && git pull
```

## 3. Создать веб-приложение

**Web → Add a new web app → Next → Manual configuration → Python 3.10 → Next**

На странице конфигурации указать:

| Поле | Значение |
| --- | --- |
| Source code | `/home/ИМЯ/school-schedule` |
| Working directory | `/home/ИМЯ/school-schedule` |
| Virtualenv | `/home/ИМЯ/school-schedule/.venv` |

## 4. Прописать WSGI

На той же странице: **WSGI configuration file** → открыть ссылку
(`/var/www/ИМЯ_pythonanywhere_com_wsgi.py`), **стереть всё** и вставить:

```python
import sys

path = '/home/ИМЯ/school-schedule'
if path not in sys.path:
    sys.path.insert(0, path)

from pa_wsgi import application
```

`ИМЯ` заменить на своё имя пользователя (оно видно в адресе сайта).

## 5. Перезапустить

Кнопка **Reload** вверху страницы Web. Через 5–10 секунд открыть
`https://ИМЯ.pythonanywhere.com` — должно появиться расписание.

Проверка «живости» и данных:

- `https://ИМЯ.pythonanywhere.com/healthz` → `ok`
- `https://ИМЯ.pythonanywhere.com/api/diag` → JSON: сколько дней загружено,
  была ли ошибка таблицы, включены ли уведомления.

## 6. Если имя пользователя не `schedule8g`

В файле `index.html` найти строку (в самом начале скрипта):

```js
const MIRROR_URL='https://schedule8g.pythonanywhere.com';
```

и заменить адрес на свой. Затем:

```bash
cd ~/school-schedule
git add index.html && git commit -m "зеркало: адрес" && git push
```

и нажать **Reload** на PythonAnywhere (и подождать, пока Render
пересоберёт основной сайт).

---

## Что уже сделано в коде

- `pa_wsgi.py` — WSGI-обёртка: PythonAnywhere не умеет запускать `http.server`,
  поэтому вся логика из `app.py` (таблица, кэш, push) подключается через WSGI.
- `index.html`:
  - если `/api/schedule` не отвечает 15 секунд, сайт показывает
    **«Извините, этот домен плохо работает без VPN»** и кнопку
    **«Перейти на зеркало»**;
  - в подвале всегда есть ссылка **«Зеркало без VPN»**;
  - на самом зеркале в подвале написано «Зеркало · работает без VPN».
- `sw.js` — сервис-воркер кэширует страницу: после первого визита сайт
  открывается даже если Render спит.

## Ограничения бесплатного тарифа

| Что | Как есть |
| --- | --- |
| Сайт всегда включён | Да, в отличие от Render |
| Свой домен | Нет (только `ИМЯ.pythonanywhere.com`) |
| Аккаунт | Раз в 3 месяца надо заходить и продлевать (кнопка в панели) |
| CPU | 100 секунд в день — для этого сайта с запасом |
| Push-уведомления | Chrome/Edge/Android работают; на iPhone — только из «Домой» |
| Обновление таблицы | При каждом заходе на сайт (кэш 90 секунд), плюс можно
  добавить ежедневную задачу: **Tasks → New scheduled task** →
  `curl -s https://ИМЯ.pythonanywhere.com/api/schedule?force=1 > /dev/null` |

## Проверка после развёртывания

1. Открыть зеркало — расписание на месте.
2. Открыть основной сайт Render — в подвале ссылка «Зеркало без VPN».
3. Остановить основной сайт (или дождаться, пока он заснёт) и открыть его:
   появится сообщение про VPN и кнопка перехода на зеркало.

---

## Обновление до актуальной версии (офлайн без интернета)

`pa_update.sh` в корне репозитория обновляет файлы веб-приложения прямо из
GitHub и перезапускает его. В **Consoles → Bash** на PythonAnywhere достаточно
одной строки:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Nikita2272282299/school-schedule/main/pa_update.sh)
```

Скрипт сам находит каталог приложения по WSGI-конфигу, скачивает `index.html`,
`sw.js`, `config.js`, `offline-data.js`, `manifest.json`, `app.py`, `pa_wsgi.py`,
`cors.py` и оба шрифта Manrope, затем делает `touch` WSGI-файла (аналог кнопки
Reload). Папка `data/` с историей дней, VAPID-ключами и подписками не трогается.

Проверка: `/healthz` → `ok`, `/offline-data.js` → `200`, версия в заголовке
страницы `266`, в исходниках нет `fonts.googleapis.com`. Обновление можно
повторять сколько угодно: оно всегда берёт последнюю версию из ветки `main`.

Если консоль недоступна: `cd ~/school-schedule && git pull --ff-only`, затем
кнопка **Reload** на странице Web.
