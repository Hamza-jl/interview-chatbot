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
    # "Heading 1" / "Titre 1" for sections, and the document's own "Title" /
    # "Titre" style, which is what carries the name of the questionnaire.
    if style.startswith(("heading", "titre", "title")):
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


# « Tableau N°9 : Référents de crise », « Table 3 - Applications », « Figure 2 : … »
_CAPTION = re.compile(
    r"^\s*(?:tableau|table|figure|annexe)\s*n?\s*[°ºo]?\s*[\dIVXA-Za-z]*(?:[.\-]\d+)*"
    r"\s*[:\-–—]\s*(?P<titre>.+?)\s*$",
    re.IGNORECASE,
)
# En dessous, la légende ne nomme rien : « Tableau N°3.c : » tout seul, ou
# « Tableau N°3.b : Evaluation des impacts : » tronqué à deux lettres.
_MIN_CAPTION = 4


def _caption(paragraph: Paragraph) -> Optional[str]:
    """The table's own caption, when the line above it carries one.

    A section heading names a whole section, which may hold several tables; the
    caption names one. Where the two disagree the caption is right - and they do
    disagree, in every template that puts a matrix the reader cannot fill under
    the same heading as the table it can, because the heading then lands on the
    wrong table.
    """
    match = _CAPTION.match(" ".join(paragraph.text.split()))
    if not match:
        return None
    titre = match.group("titre").strip(" :;-–—")
    return titre if len(titre) >= _MIN_CAPTION else None


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


def _is_unread_form(table: Table) -> bool:
    """A table with blanks to fill that `_classify` could not make sense of.

    The shape this catches is the matrix: row labels down the first column,
    column headings across the first row, answers at the intersections - an
    impact grid, a "montee en charge" schedule. It is not supported yet, and the
    point of recognising it is to be able to say so rather than pass over it.

    Layout boxes and glossaries are excluded: a table needs a real grid shape,
    labels on both axes, and a meaningful share of its body still empty.
    """
    if len(table.rows) < 3 or len(table.rows[0].cells) < 3:
        return False

    header = [_cell_text(c) for c in table.rows[0].cells]
    side = [_cell_text(r.cells[0]) for r in table.rows[1:]]
    if sum(1 for h in header[1:] if not is_blank(h)) < 2:
        return False
    if sum(1 for s in side if not is_blank(s)) < 2:
        return False

    body = [
        _cell_text(c)
        for row in table.rows[1:]
        for c in list(row.cells)[1:]
    ]
    return bool(body) and sum(1 for v in body if is_blank(v)) >= len(body) // 2


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

    # Two columns, the left one consistently written: a list of fields.
    #
    # What makes it a form is the label column, NOT how much of the answer
    # column is still empty. Templates come back half-completed - a real BIA
    # fiche had four of its six answers written and two left as "xx" - and
    # requiring most of the column to be blank found nothing in it at all.
    # Rows already answered are skipped when the slots are emitted, so a
    # partially filled table asks only about what is actually missing.
    if width == 2 and table.rows:
        labels = [_cell_text(r.cells[0]) for r in table.rows]
        answers = [_cell_text(r.cells[1]) for r in table.rows]
        missing = [is_blank(a) or _is_instruction(a) for a in answers]

        if all(not is_blank(label) for label in labels) and any(missing):
            # Row 0 is a column heading only if it carries one on BOTH sides -
            # "Question | Réponse". A first row whose answer cell is blank is a
            # question like any other, and skipping it loses a field.
            heading = not is_blank(labels[0]) and not is_blank(answers[0])
            if heading and any(missing[1:]):
                return "keyvalue-header"
            if not heading:
                return "keyvalue"

    return "prose"


def read(path: str, filename: str = "") -> DocumentPlan:
    document = Document(path)
    name = filename or path.rsplit("/", 1)[-1]

    title = ""
    context: List[str] = []
    slots: List[Slot] = []
    notes: List[str] = []
    ignored: List[str] = []
    table_index = 0

    caption: Optional[str] = None
    légendes: set = set()

    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            level = _heading_level(block)
            text = block.text.strip()
            if level is not None and text:
                if not title:
                    # A heading can carry a manual line break; the title is
                    # shown on one line in a list, so it becomes one line here.
                    title = " ".join(text.split())
                # Keep the trail shallow: two levels is all a question needs.
                context = (context[: max(0, level - 1)] + [text])[-3:]
                caption = None
            elif text:
                # Une légende ne vaut que pour le tableau qui la suit : toute
                # autre ligne de texte entre les deux la périme.
                caption = _caption(block)
            continue

        table_index += 1
        shape = _classify(block)
        # Une légende déjà portée par un tableau précédent ne distingue plus
        # rien - et ce document-ci en a deux identiques. Dans ce cas le titre de
        # section, lui, sépare bien les deux.
        if caption and caption.lower() in légendes:
            caption = None
        nom = caption or (context[-1] if context else f"Tableau {table_index}")
        if caption:
            légendes.add(caption.lower())
        caption = None

        if shape == "prose" and _is_unread_form(block):
            ignored.append(f"« {nom} » (tableau {table_index})")

        if shape == "grid":
            header = [_cell_text(c) for c in block.rows[0].cells]
            label = nom
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
                # Already answered. Asking again would put the interviewee's
                # reply over something the document already says - the one thing
                # write-back must never do to a half-completed template.
                if not is_blank(hint) and not _is_instruction(hint):
                    continue
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

    if ignored:
        # Said out loud rather than passed over. These are matrix tables - row
        # labels down the side, column headings across the top, answers at the
        # intersections - and they carry real content in a BIA fiche. Reading
        # them is not supported yet; leaving the reader silent about them would
        # let someone hand over a document believing it complete.
        notes.append(
            "Tableau(x) non pris en charge, à compléter à la main : "
            + ", ".join(ignored)
            + ". Ces tableaux croisent des lignes et des colonnes déjà nommées ; "
            "leurs cases seront laissées telles quelles."
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
