"""Регрессия: старый Safari (iOS 12/13) не разбирает синтаксис ES2020.

Если в отправляемые файлы попадёт optional chaining `?.` или nullish `??`,
браузер не выполнит скрипт вообще, и страница останется пустой.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHIPPED = [
    "index.html",
    "sw.js",
    "config.js",
    "manifest.json",
    "pa-dist/index.html",
    "pa-dist/sw.js",
]

ES2020 = [
    ("?. optional chaining", re.compile(r"\?\.(?!\d)")),
    ("?? nullish coalescing", re.compile(r"\?\?")),
]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class CompatibilityTests(unittest.TestCase):
    def test_no_es2020_syntax_in_shipped_files(self):
        for rel in SHIPPED:
            path = ROOT / rel
            if not path.exists():
                continue
            text = read(rel)
            for name, rx in ES2020:
                for m in rx.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    self.fail(f"{rel}:{line}: найден {name} — старый Safari не выполнит скрипт")

    def test_old_browser_fallback_present(self):
        """Если основной скрипт не запустился, пользователь видит сообщение, а не пустоту."""
        for rel in ("index.html", "pa-dist/index.html"):
            path = ROOT / rel
            if not path.exists():
                continue
            text = read(rel)
            self.assertEqual(
                text.count("document.documentElement.dataset.app='ok'"),
                1,
                f"{rel}: маркер успешного запуска должен быть ровно один",
            )
            self.assertIn("Браузер слишком старый", text, f"{rel}: нет сообщения для старого браузера")
            self.assertIn("<noscript>", text, f"{rel}: нет заглушки при выключенном JavaScript")
            # страховка должна стоять после основного скрипта, иначе смысла нет
            self.assertLess(
                text.index("dataset.app='ok'"),
                text.index("Браузер слишком старый"),
                f"{rel}: страховка стоит раньше основного скрипта",
            )

    def test_api_base_read_without_optional_chaining(self):
        """Адрес API должен читаться так, чтобы работало и без ES2020."""
        for rel in ("index.html", "pa-dist/index.html"):
            path = ROOT / rel
            if not path.exists():
                continue
            text = read(rel)
            self.assertIn("SCHEDULE_CONFIG&&self.SCHEDULE_CONFIG.apiBase", text, rel)


if __name__ == "__main__":
    unittest.main()
