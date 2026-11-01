from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell


def write_xlsx(
    path: Path,
    *,
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    sheet_title: str,
) -> Path:
    """Write tabular export data with untrusted strings stored as literal text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title=sheet_title)
    sheet.freeze_panes = "A2"

    def append(values: Sequence[Any]) -> None:
        cells = []
        for value in values:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, default=str)
            elif value is not None and not isinstance(value, (str, int, float, bool)):
                value = str(value)
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                cell.data_type = "s"
            cells.append(cell)
        sheet.append(cells)

    append(columns)
    for row in rows:
        append([row.get(column) for column in columns])
    workbook.save(path)
    return path
