/* Встроенная офлайн-копия расписания 8Г.
   Обновляется при каждой успешной загрузке с API (в localStorage) и в репозитории
   скриптом refresh_snapshot.py. Файл нужен, чтобы сайт показывал расписание
   даже при первом запуске без интернета, в том числе с file://. */
self.SCHEDULE_SNAPSHOT = {
  "class": "8Г",
  "ok": true,
  "error": "",
  "updated": 1794255131,
  "sheet_url": "https://docs.google.com/spreadsheets/d/1OtsY3sw2MqQXUg9FA0GXNbYboSwTw33og-rAn9CofOE/edit",
  "days": [
    {
      "date": "2026-11-09",
      "weekday": "Понедельник",
      "lessons": [
        {
          "n": 1,
          "time": "8:00-8:40",
          "subject": "химия",
          "room": "205",
          "raw": "химия 205"
        },
        {
          "n": 2,
          "time": "8:50-9:30",
          "subject": "истор",
          "room": "326",
          "raw": "истор 326"
        },
        {
          "n": 3,
          "time": "9:45-10:25",
          "subject": "алгебр",
          "room": "409",
          "raw": "алгебр 409"
        },
        {
          "n": 4,
          "time": "10:40-11:20",
          "subject": "англ",
          "room": "319/307",
          "raw": "англ319/307"
        },
        {
          "n": 5,
          "time": "11:35-12:15",
          "subject": "алгебр",
          "room": "409",
          "raw": "алгебр 409"
        },
        {
          "n": 6,
          "time": "12:25-13:05",
          "subject": "",
          "room": "",
          "raw": ""
        },
        {
          "n": 7,
          "time": "13:15-13:55",
          "subject": "РоВ",
          "room": "323",
          "raw": "РоВ 323"
        }
      ],
      "first": 0,
      "changed": 0
    },
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
    }
  ],
  "saved_at": 1794255131
};
