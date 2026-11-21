import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import ai_schedule
import app


SAMPLE_ROWS = [
    ["20 ноября", "Пятница"],
    ["", "", "8Г", "11А", "11Ф"],
    ["1", "8:00-8:40", "информатика / труд 423", "алгебра 407", "физика 310"],
    ["2", "8:50-9:30", "биология 323", "русский 409", "история 313"],
    ["9", "14:55-15:35", "", "с  8.50 в 405 кабинете", ""],
]


class AiScheduleTests(unittest.TestCase):
    def test_note_cell_separated_from_lessons(self):
        days = ai_schedule.build_rules_schedule(SAMPLE_ROWS, date(2026, 11, 20))
        d = days["2026-11-20"]
        self.assertEqual(len(d["classes"]["11А"]["lessons"]), 2)
        self.assertEqual(d["classes"]["11А"]["notes"], ["С 8:50 в 405 кабинете"])
        self.assertEqual(d["classes"]["8Г"]["notes"], [])

    def test_app_parse_sheet_separates_notes(self):
        days, found = app.parse_sheet(SAMPLE_ROWS, "11а", date(2026, 11, 20))
        self.assertTrue(found)
        d = days["2026-11-20"]
        self.assertEqual(len(d["lessons"]), 2)
        self.assertEqual(d["notes"], ["С 8:50 в 405 кабинете"])

    def test_cache_skips_ai_when_sheet_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ai-schedule.json"
            with mock.patch.object(ai_schedule, "call_ai", return_value=(None, "no_token")) as mocked:
                first = ai_schedule.compile_schedule(SAMPLE_ROWS, out, today=date(2026, 11, 20))
                second = ai_schedule.compile_schedule(SAMPLE_ROWS, out, today=date(2026, 11, 20))
                self.assertEqual(mocked.call_count, 1)
                self.assertEqual(first["sheet_hash"], second["sheet_hash"])

    def test_ai_output_validated_and_backfilled(self):
        ai_payload = {
            "days": [
                {
                    "date": "2026-11-20",
                    "weekday": "Пятница",
                    "classes": {
                        "11А": {
                            "notes": ["С 8:50 в 405 кабинете"],
                            "lessons": [
                                {"n": "1", "time": "8:00-8:40", "raw": "Алгебра 407"},
                                {"n": "2", "time": "8:50-9:30", "raw": "Русский язык 409"},
                            ],
                        }
                    },
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ai-schedule.json"
            with mock.patch.object(ai_schedule, "call_ai", return_value=(ai_payload, "ai:openai/gpt-4o-mini")):
                res = ai_schedule.compile_schedule(SAMPLE_ROWS, out, today=date(2026, 11, 20))
            self.assertEqual(res["source"], "ai:openai/gpt-4o-mini")
            d = res["days"]["2026-11-20"]
            self.assertEqual(d["classes"]["11А"]["notes"], ["С 8:50 в 405 кабинете"])
            # 8Г и 11Ф не вернулись от ИИ — должны подтянуться из детерминированного парсера.
            self.assertIn("8Г", d["classes"])
            self.assertIn("11Ф", d["classes"])
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["source"], "ai:openai/gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
