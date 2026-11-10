/* HTTPS-адрес API для GitHub Pages (там своего сервера нет).
   На localhost, в локальной сети и при открытии файлом сайт сам использует
   свой сервер и встроенную офлайн-копию offline-data.js — внешний адрес
   в этих режимах не запрашивается. Пустая строка: API на том же домене. */
self.SCHEDULE_CONFIG = { apiBase: 'https://nassda.pythonanywhere.com' };
