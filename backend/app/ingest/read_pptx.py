"""Find the blanks in a PowerPoint deck.

Decks are a weaker fit than Word or Excel and it is worth being honest about
why: a slide is a canvas, not a form. Three things are nonetheless fillable and
worth collecting:

  - empty body placeholders inherited from the layout, which is what a deck
    built from a corporate template actually leaves blank;
  - tables, which behave exactly like Word tables;
  - text boxes whose whole content is a bracketed instruction.

A title placeholder is used as the section context rather than as a question -
nobody wants to be asked to dictate a slide title.
"""
from __future__ import annotations

from typing import List

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

from .slots import DocumentPlan, Slot, is_blank

# Placeholders that hold decoration or numbering rather than content.
_IGNORED = {
    PP_PLACEHOLDER.SLIDE_NUMBER,
    PP_PLACEHOLDER.FOOTER,
    PP_PLACEHOLDER.HEADER,
    PP_PLACEHOLDER.DATE,
}
_TITLES = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.SUBTITLE}


def _shape_text(shape) -> str:
    if not shape.has_text_frame:
        return ""
    return " ".join(shape.text_frame.text.split())


def _placeholder_kind(shape):
    try:
        return shape.placeholder_format.type
    except (AttributeError, ValueError):
        return None


def read(path: str, filename: str = "") -> DocumentPlan:
    deck = Presentation(path)
    name = filename or path.rsplit("/", 1)[-1]
    slots: List[Slot] = []
    notes: List[str] = []
    title = ""

    for index, slide in enumerate(deck.slides, 1):
        heading = ""
        for shape in slide.shapes:
            if shape.is_placeholder and _placeholder_kind(shape) in _TITLES:
                heading = _shape_text(shape)
                break
        if not title and heading:
            title = heading
        section = heading or f"Diapositive {index}"

        for order, shape in enumerate(slide.shapes):
            kind = _placeholder_kind(shape) if shape.is_placeholder else None
            if kind in _IGNORED or kind in _TITLES:
                continue

            if shape.has_table:
                table = shape.table
                header = [" ".join(c.text.split()) for c in table.rows[0].cells]
                if all(not is_blank(h) for h in header) and len(header) >= 2:
                    slots.append(
                        Slot(
                            id=f"pptx.s{index}.sh{order}.grid",
                            kind="grid",
                            label=section,
                            columns=header,
                            context=[section],
                            target={
                                "slide": index,
                                "shape": order,
                                "mode": "grid",
                                "header_rows": 1,
                            },
                        )
                    )
                continue

            if not shape.has_text_frame:
                continue

            text = _shape_text(shape)
            if not is_blank(text):
                continue
            # An empty text box that is not a placeholder is usually spacing or a
            # decorative rule, not somewhere an answer belongs.
            if kind is None:
                continue

            slots.append(
                Slot(
                    id=f"pptx.s{index}.sh{order}",
                    kind="cell",
                    label=section,
                    context=[section],
                    target={"slide": index, "shape": order, "mode": "text"},
                )
            )

    if not slots:
        notes.append(
            "Aucun emplacement vide détecté. Une présentation déjà rédigée n'a "
            "rien à remplir."
        )

    return DocumentPlan(
        filename=name, kind="pptx", title=title or name, slots=slots, notes=notes
    )
