import io
import unittest
from datetime import date
from openpyxl import Workbook
import app
from sheet_export import sheet_rows

class ExportTests(unittest.TestCase):
    def test_explicit_merged_cells_only(self):
        book = Workbook()
        sheet = book.active
        sheet['D1'] = date(2026, 11, 11)
        sheet['D1'].number_format = 'd mmmm'
        for col, name in enumerate(['8А', '8Б', '8В', '8Г'], 3):
            sheet.cell(2, col, name)
        sheet.append([7, '13:15-13:55', 'химия (профиль) 205'])
        sheet.merge_cells('C3:F3')
        sheet.append([8, '14:00-14:40', 'информатика 324', None, None, None])
        buf = io.BytesIO(); book.save(buf)
        rows = sheet_rows(buf.getvalue())
        self.assertEqual(rows[2][2:6], ['химия (профиль) 205'] * 4)
        self.assertEqual(rows[3][2:6], ['информатика 324', '', '', ''])
        for cls in ('8А', '8Б', '8В', '8Г'):
            days, found = app.parse_sheet(rows, cls, date(2026, 11, 11))
            self.assertTrue(found)
            self.assertEqual(days['2026-11-11']['lessons'][0]['raw'], 'химия (профиль) 205')
        self.assertEqual(rows[0][3], '11 ноября')

    def test_vertical_merge_and_class_date_format(self):
        book = Workbook(); sheet = book.active
        sheet['A1'] = 'Урок'; sheet.merge_cells('A1:A2')
        sheet['B1'] = date(2026, 3, 5); sheet['B1'].number_format = 'd m'
        buf = io.BytesIO(); book.save(buf)
        rows = sheet_rows(buf.getvalue())
        self.assertEqual(rows[1][0], 'Урок')
        self.assertEqual(rows[0][1], '5 3')
