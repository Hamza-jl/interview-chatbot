"""Find the blanks in a Word document.

Real forms are built from tables, and the two that matter look different enough
to tell apart without guessing:

    Nom du responsable │              ← a label beside an empty cell
    Direction          │

    Domaine │ Processus │ Criticité   ← a header row over empty rows
            │           │
            │           │

Everything hangs on deciding which is which, so the decision is made from
evidence in the table itself - how many columns, which of them are empty, how
many rows repeat the same shape - and never from a model's opinion. A wrong call
here writes an answer into the wrong cell of a document someone signs.
"""
from __future__ import annotations

import re

from typing import List, Optional

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from .slots import DocumentPlan, Slot, is_blank, looks_like_label

# A heading longer than this is prose that happens to be styled as a heading.
_MAX_HEADING = 120
# Below this many columns a table is a key/value list, not a grid to fill.
_GRID_MIN_COLUMNS = 2


def _iter_blocks(document: Document):
    """Paragraphs and tables in the order they appear on the page.

    python-docx exposes the two as separate collections, which loses the
    interleaving - and the interleaving is exactly what says which heading a
    table sits under.
    """
    from docx.oxml.ns import qn

    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _heading_level(paragraph: Paragraph) -> Optional[int]:
    style = (paragraph.style.name or "").lower()
    if style.startswith("heading") or style.startswith("titre"):
        digits = "".join(c for c in style if c.isdigit())
        return int(digits) if digits else 1
    # Many real templates never use heading styles; a short bold line that opens
    # a block does the same job and has to be honoured.
    text = paragraph.text.strip()
    if text and len(text) <= _MAX_HEADING and paragraph.runs:
        if all(r.bold for r in paragraph.runs if r.text.strip()):
            return 9
    return None


def _cell_text(cell) -> str:
    return " ".join(cell.text.split())


_INSTRUCTION = re.compile(
    r"^\s*(?:n\.?\s?b\.?|note|nota|remarque|ex\.?|exemple|cf\.?|voir)\b",
    re.IGNORECASE,
)


def _is_instruction(text: str) -> bool:
    """An author's note parked in the answer column, not somebody's answer."""
    return bool(_INSTRUCTION.match(text or ""))


def _column_is_blank(table: Table, index: int, skip_header: bool) -> bool:
    rows = table.rows[1:] if skip_header else table.rows
    for row in rows:
        if index < len(row.cells) and not is_blank(_cell_text(row.cells[index])):
            return False
    return True


def _classify(table: Table) -> str:
    """'grid', 'keyvalue' or 'prose' - decided on the table's own evidence."""
    if not table.rows:
        return "prose"

    width = len(table.rows[0].cells)
    header = [_cell_text(c) for c in table.rows[0].cells]
    header_filled = sum(1 for h in header if not is_blank(h))

    # A header row whose every cell carries a title, over rows that are empty:
    # that is a grid waiting for an unknown number of entries.
    if width >= _GRID_MIN_COLUMNS and header_filled == width and len(table.rows) >= 2:
        body_blank = all(
            is_blank(_cell_text(c)) for row in table.rows[1:] for c in row.cells
        )
        if body_blank:
            return "grid"
        # A single filled row under a full header is usually a worked example
        # the author left in, not data. Still a grid.
        filled_rows = sum(
            1 for row in table.rows[1:]
            if any(not is_blank(_cell_text(c)) for c in row.cells)
        )
        if filled_rows <= 1 and len(table.rows) > 2:
            return "grid"

    # Two columns, the left one consistently written and the right one empty:
    # a list of fields.
    if width == 2 and _column_is_blank(table, 1, skip_header=False):
        labels = [_cell_text(r.cells[0]) for r in table.rows]
        if sum(1 for label in labels if label) >= max(1, len(labels) // 2):
            return "keyvalue"

    # The same thing with a header row over it - "Question | Réponse" is how
    # most of these templates are actually written, and requiring the header
    # cell to be empty missed every one of them.
    if width == 2 and len(table.rows) >= 2:
        body = table.rows[1:]
        answers = [_cell_text(r.cells[1]) for r in body]
        labels = [_cell_text(r.cells[0]) for r in body]
        # An instruction the author left in the answer column ("N.B. : template
        # envoyé séparément") is guidance, not data - it must not disqualify the
        # row. Real data in most rows must.
        unanswered = sum(1 for a in answers if is_blank(a) or _is_instruction(a))
        if labels and all(labels) and unanswered >= max(1, len(body) // 2):
            return "keyvalue-header"

    return "prose"


def read(path: str, filename: str = "") -> DocumentPlan:
    document = Document(path)
    name = filename or path.rsplit("/", 1)[-1]

    title = ""
    context: List[str] = []
    slots: List[Slot] = []
    notes: List[str] = []
    table_index = 0

    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            level = _heading_level(block)
            text = block.text.strip()
            if level is not None and text:
                if not title:
                    title = text
                # Keep the trail shallow: two levels is all a question needs.
                context = (context[: max(0, level - 1)] + [text])[-3:]
            continue

        table_index += 1
        shape = _classify(block)

        if shape == "grid":
            header = [_cell_text(c) for c in block.rows[0].cells]
            label = context[-1] if context else f"Tableau {table_index}"
            example = None
            for row in block.rows[1:]:
                values = [_cell_text(c) for c in row.cells]
                if any(not is_blank(v) for v in values):
                    example = " | ".join(values)
                    break
            slots.append(
                Slot(
                    id=f"docx.t{table_index}.grid",
                    kind="grid",
                    label=label,
                    columns=header,
                    context=list(context),
                    existing=example,
                    target={"table": table_index, "mode": "grid", "header_rows": 1},
                )
            )

        elif shape in ("keyvalue", "keyvalue-header"):
            rows = list(enumerate(block.rows))
            if shape == "keyvalue-header":
                rows = rows[1:]                      # the header names the columns
            for row_index, row in rows:
                label = _cell_text(row.cells[0])
                if not label or is_blank(label):
                    continue
                hint = _cell_text(row.cells[1]) if len(row.cells) > 1 else ""
                slots.append(
                    Slot(
                        id=f"docx.t{table_index}.r{row_index}",
                        kind="cell",
                        label=label.rstrip(" :"),
                        context=list(context),
                        existing=hint if _is_instruction(hint) else None,
                        target={
                            "table": table_index,
                            "mode": "cell",
                            "row": row_index,
                            "col": 1,
                        },
                    )
                )

    if not slots:
        notes.append(
            "Aucun tableau à remplir détecté. Le document est peut-être rédigé en "
            "texte libre, ou protégé."
        )

    return DocumentPlan(
        filename=name,
        kind="docx",
        title=title or name,
        slots=slots,
        notes=notes,
    )
