"""Find the blanks in an Excel workbook.

A spreadsheet form is almost always one of two things:

    A1 Nom du responsable  B1 (vide)     ← labels down A, answers down B
    A2 Direction           B2 (vide)

    A1 Domaine  B1 Processus  C1 Criticité   ← a header row, rows below empty
    A2          B2            C2

Merged cells, frozen panes and a title row above the real header are the usual
complications, so the header is located by looking for the first run of adjacent
non-empty cells with emptiness underneath, rather than assuming row 1.

Sheets that are charts, pivots or lookup tables are skipped: a lookup list is
full of data and would otherwise read as a filled form.
"""
from __future__ import annotations

import io
from typing import List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from .slots import DocumentPlan, Slot, is_blank

_MAX_SCAN_ROWS = 40          # a header this far down is not a header
_MAX_COLUMNS = 30
_MIN_GRID_COLUMNS = 2


def _text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _row_values(sheet: Worksheet, row: int, width: int) -> List[str]:
    return [_text(sheet.cell(row=row, column=c).value) for c in range(1, width + 1)]


def _used_width(sheet: Worksheet) -> int:
    # At least two: on a blank form the answer column holds nothing at all, so
    # openpyxl reports max_column == 1 and the column we mean to write into
    # looks as though it does not exist.
    return min(max(sheet.max_column or 1, 2), _MAX_COLUMNS)


def _find_header(sheet: Worksheet, width: int) -> Optional[Tuple[int, List[str]]]:
    """The first row that names columns and has emptiness beneath it."""
    limit = min(sheet.max_row or 1, _MAX_SCAN_ROWS)
    for row in range(1, limit + 1):
        values = _row_values(sheet, row, width)
        filled = [i for i, v in enumerate(values) if not is_blank(v)]
        if len(filled) < _MIN_GRID_COLUMNS:
            continue
        # Contiguous run of titles - a scattered pair of cells is not a header.
        if filled != list(range(filled[0], filled[-1] + 1)):
            continue
        below = [
            _row_values(sheet, r, width)
            for r in range(row + 1, min(row + 6, (sheet.max_row or row) + 1))
        ]
        # A header with nothing under it at all is the commonest shape of a
        # blank form, not a reason to reject it.
        empty_below = all(
            is_blank(cells[i]) for cells in below for i in filled if i < len(cells)
        )
        if empty_below:
            return row, [values[i] for i in filled]
    return None


def _key_value_pairs(sheet: Worksheet, width: int) -> List[Tuple[int, str]]:
    """Rows where column A labels something and column B is waiting for it."""
    pairs: List[Tuple[int, str]] = []
    limit = min(sheet.max_row or 1, 200)
    for row in range(1, limit + 1):
        label = _text(sheet.cell(row=row, column=1).value)
        if is_blank(label) or len(label) > 120:
            continue
        if width < 2:
            continue
        value = _text(sheet.cell(row=row, column=2).value)
        rest = [_text(sheet.cell(row=row, column=c).value) for c in range(3, width + 1)]
        if is_blank(value) and all(is_blank(v) for v in rest):
            pairs.append((row, label))
    return pairs


def read(path: str, filename: str = "") -> DocumentPlan:
    # Read into memory first: openpyxl decides what a file is from its
    # extension, and an upload is staged under a name it chose itself. The
    # format was already settled by `reader.detect`, from the bytes.
    with open(path, "rb") as handle:
        workbook = load_workbook(io.BytesIO(handle.read()), data_only=True)
    name = filename or path.rsplit("/", 1)[-1]
    slots: List[Slot] = []
    notes: List[str] = []

    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            notes.append(f"Feuille « {sheet.title} » masquée, ignorée.")
            continue

        width = _used_width(sheet)
        if not width or not sheet.max_row:
            continue

        header = _find_header(sheet, width)
        if header is not None:
            row, columns = header
            slots.append(
                Slot(
                    id=f"xlsx.{sheet.title}.grid",
                    kind="grid",
                    label=sheet.title,
                    columns=columns,
                    context=[sheet.title],
                    target={
                        "sheet": sheet.title,
                        "mode": "grid",
                        "header_row": row,
                        "first_column": 1,
                    },
                )
            )
            continue

        pairs = _key_value_pairs(sheet, width)
        for row, label in pairs:
            slots.append(
                Slot(
                    id=f"xlsx.{sheet.title}.r{row}",
                    kind="cell",
                    label=label.rstrip(" :"),
                    context=[sheet.title],
                    target={"sheet": sheet.title, "mode": "cell", "row": row, "col": 2},
                )
            )
        if not pairs:
            notes.append(f"Feuille « {sheet.title} » : aucun champ vide identifié.")

    workbook.close()
    if not slots:
        notes.append("Aucun champ à remplir détecté dans ce classeur.")

    return DocumentPlan(filename=name, kind="xlsx", title=name, slots=slots, notes=notes)
