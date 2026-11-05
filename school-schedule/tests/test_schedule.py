import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
TEMP = tempfile.TemporaryDirectory()
os.environ['DATA_DIR'] = TEMP.name
import app
from cors import with_cors
from build_pages import PUBLIC


class ScheduleTests(unittest.TestCase):
    def test_parser(self):
        rows = [['4 ноября'], ['', '', '', '8а', '8б', '8г'],
                ['1', '8:00-8:40', '', '', '', 'Алг (305)']]
        days, found = app.parse_sheet(rows, '8г', app.date(2026, 11, 4))
        self.assertTrue(found)
        self.assertEqual(days['2026-11-04']['lessons'][0]['room'], '305')

    def test_room_without_brackets(self):
        # в таблице кабинет часто записан в той же ячейке: «Англ319/221»
        self.assertEqual(app.split_lesson('Англ319/221'), ('Англ', '319/221'))
        self.assertEqual(app.split_lesson('истор 305'), ('истор', '305'))
        self.assertEqual(app.split_lesson('Физкультура спортзал'), ('Физкультура', 'спортзал'))
        self.assertEqual(app.split_lesson('Алг (305)'), ('Алг', '305'))
        # предмет без кабинета не должен пострадать
        self.assertEqual(app.split_lesson('Русский язык'), ('Русский язык', ''))
        self.assertEqual(app.split_lesson('Математика 2'), ('Математика 2', ''))

    def test_history_and_source_failure(self):
        iso = app.now_perm().date().isoformat()
        app._store = {iso: {'date': iso, 'lessons': []}}
        app._meta = {}
        app.save_store()
        app._store = {}
        app.load_store()
        self.assertIn(iso, app._store)
        app._state['ts'] = 0
        with patch.object(app, 'fetch_csv', side_effect=OSError('offline')):
            app.refresh(True)
        self.assertFalse(app._state['ok'])
        self.assertIn(iso, app._store)

    def test_cors(self):
        @with_cors
        def endpoint(env, start):
            start('200 OK', [('Content-Length', '2')])
            return [b'ok']
        def request(origin, method):
            result = []
            body = endpoint({'PATH_INFO': '/api/schedule', 'HTTP_ORIGIN': origin,
                             'REQUEST_METHOD': method}, lambda s, h, e=None: result.extend([s, dict(h)]))
            return result, b''.join(body)
        result, _ = request('https://nikita2272282299.github.io', 'OPTIONS')
        self.assertEqual(result[0], '204 No Content')
        self.assertEqual(result[1]['Access-Control-Allow-Origin'], 'https://nikita2272282299.github.io')
        self.assertEqual(request('https://untrusted.example', 'POST')[0][0], '403 Forbidden')

    def test_pages_paths_and_allowlist(self):
        manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['scope'], './')
        self.assertTrue(all(not i['src'].startswith('/') for i in manifest['icons']))
        self.assertFalse({'app.py', 'vapid.json', 'days_store.json', 'push_subs.json'} & set(PUBLIC))
        html = (BASE / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('href="/', html)
        self.assertNotIn("register('/", html)
        self.assertNotIn("fetch('/api/", html)


if __name__ == '__main__':
    unittest.main()
