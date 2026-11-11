"""Read the visible Google Sheets workbook with explicit merge information."""
import io
import json
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')


def sheet_rows(data):
    workbook = load_workbook(io.BytesIO(data), data_only=True)
    sheet = workbook.active
    # Export only the used range, ignoring formatting on otherwise empty rows.
    values = {}
    max_row = max_col = 0
    for row in sheet.iter_rows():
        for cell in row:
            value = cell.value
            if value is None:
                continue
            if isinstance(value, (date, datetime)):
                # Google has date-formatted labels such as '5 3' in class headers.
                value = (f'{value.day} {value.month}' if cell.number_format.lower().strip() == 'd m'
                         else f'{value.day} {MONTHS[value.month - 1]}')
            elif isinstance(value, (int, float)) and value == int(value):
                value = str(int(value))
            else:
                value = str(value)
            values[(cell.row, cell.column)] = value
            max_row, max_col = max(max_row, cell.row), max(max_col, cell.column)
    for merged in sheet.merged_cells.ranges:
        value = values.get((merged.min_row, merged.min_col), '')
        if value:
            if merged.max_row - merged.min_row > 200 or merged.max_col - merged.min_col > 200:
                raise ValueError('Слишком большое объединение ячеек')
            max_row, max_col = max(max_row, merged.max_row), max(max_col, merged.max_col)
            for r in range(merged.min_row, merged.max_row + 1):
                for c in range(merged.min_col, merged.max_col + 1):
                    values[(r, c)] = value
    return [[values.get((r, c), '') for c in range(1, max_col + 1)]
            for r in range(1, max_row + 1)]


def fetch_rows(spreadsheet_id):
    url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (school-schedule)'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return sheet_rows(response.read())


def write_data(path, rows):
    Path(path).write_text(json.dumps({'updated': int(time.time()), 'rows': rows},
                                    ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
