import sys
import unittest
from datetime import date
from pathlib import Path

# Тестируем именно отправляемую копию, а не одноимённый legacy-файл в корне.
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import app

class FixTests(unittest.TestCase):
    def test_room_group_annotation(self):
        self.assertEqual(app.split_lesson('англ319/308(1)'), ('англ','319/308(1)'))
        self.assertEqual(app.split_lesson('Физика (305(2),407)'), ('Физика','305(2),407'))
        self.assertEqual(app.split_lesson('Химия (пр)'), ('Химия (пр)',''))
        self.assertEqual(app.split_lesson('Химия (пр) 205'), ('Химия (пр)','205'))

    def test_merged_html_and_blank_spacers(self):
        # Synthetic fixture, not a claim about the school's current timetable.
        html = '<table class="waffle"><tr><td colspan="5">10 ноября</td></tr><tr><td></td><td></td><td>8А</td><td>8Б</td><td>8Г</td></tr><tr><th>1</th><td>1</td><td>8:00-8:40</td><td colspan="3">Хим пр 205</td></tr><tr><td colspan="5"></td></tr><tr><td>2</td><td>8:50-9:30</td><td></td><td></td><td>англ319/308(1)</td></tr></table>'
        rows=app.parse_sheet_html(html)
        days,found=app.parse_sheet(rows,'8г',date(2026,11,10))
        self.assertTrue(found)
        ls=days['2026-11-10']['lessons']
        self.assertEqual(len(ls),2)
        self.assertEqual(ls[0]['raw'],'Хим пр 205')
        self.assertEqual(ls[1]['room'],'319/308(1)')

    def test_repeated_class_blocks(self):
        header=['','','8А','8Б','8Г']
        rows=[['10 ноября'],header,['1','8:00-8:40','','','Алг 407'],[],header,['6','12:25-13:05','','','Хим пр 205']]
        days,_=app.parse_sheet(rows,'8г',date(2026,11,10))
        self.assertEqual([l['n'] for l in days['2026-11-10']['lessons']],[1,6])

    def test_rowspan_preserves_column_positions(self):
        html='<table><tr><td>8А</td><td>8Б</td><td>8Г</td></tr><tr><td rowspan="2">Хим пр</td><td>x</td><td>y</td></tr><tr><td>a</td><td>b</td></tr></table>'
        self.assertEqual(app.parse_sheet_html(html)[2],['Хим пр','a','b'])
