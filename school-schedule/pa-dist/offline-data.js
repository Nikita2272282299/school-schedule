/* Встроенная офлайн-копия расписания 8Г.
   Обновляется при каждой успешной загрузке с API (в localStorage) и в репозитории
   скриптом refresh_snapshot.py. Файл нужен, чтобы сайт показывал расписание
   даже при первом запуске без интернета, в том числе с file://. */
self.SCHEDULE_SNAPSHOT = {
  "class": "8Г",
  "ok": true,
  "error": "",
  "updated": 1794306656,
  "sheet_url": "https://docs.google.com/spreadsheets/d/1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE/edit",
  "days": [
    {
      "date": "2026-11-10",
      "weekday": "Вторник",
      "lessons": [
        {
          "n": 1,
          "time": "8:00-8:40",
          "subject": "",
          "room": "",
          "raw": ""
        },
        {
          "n": 2,
          "time": "8:50-9:30",
          "subject": "физика",
          "room": "310",
          "raw": "физика 310"
        },
        {
          "n": 3,
          "time": "9:45-10:25",
          "subject": "ОБЗР",
          "room": "302",
          "raw": "ОБЗР 302"
        },
        {
          "n": 4,
          "time": "10:40-11:20",
          "subject": "географ",
          "room": "326",
          "raw": "географ326"
        },
        {
          "n": 5,
          "time": "11:35-12:15",
          "subject": "физкульт",
          "room": "",
          "raw": "физкульт"
        }
      ],
      "first": 0,
      "changed": 0
    },
    {
      "date": "2026-11-11",
      "weekday": "Среда",
      "lessons": [
        {
          "n": 1,
          "time": "8:00-8:40",
          "subject": "англ319/308",
          "room": "1",
          "raw": "англ319/308(1)"
        },
        {
          "n": 2,
          "time": "8:50-9:30",
          "subject": "музык",
          "room": "106",
          "raw": "музык 106"
        },
        {
          "n": 3,
          "time": "9:45-10:25",
          "subject": "биолог",
          "room": "323",
          "raw": "биолог 323"
        },
        {
          "n": 4,
          "time": "10:40-11:20",
          "subject": "история",
          "room": "303",
          "raw": "история 303"
        },
        {
          "n": 5,
          "time": "11:35-12:15",
          "subject": "химия",
          "room": "205",
          "raw": "химия 205"
        }
      ],
      "first": 0,
      "changed": 0
    }
  ],
  "saved_at": 1794306656
};
