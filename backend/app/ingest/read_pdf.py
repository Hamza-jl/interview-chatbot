"""Find the blanks in a PDF - and say plainly when there are none to find.

PDF is the odd one out, and pretending otherwise would waste the user's time.
There are two completely different kinds of file behind the extension:

  A form PDF (AcroForm) carries named, typed, writable fields. It can be filled
  exactly, and the filled file is the original with values set.

  Everything else is ink on a page. There is no "field" to write into, and
  anything claiming to fill one is really drawing text at guessed coordinates -
  which shifts the moment a font substitutes, and produces a document nobody
  should sign.

So this reader fills form PDFs properly, and for the rest it refuses cleanly and
says what to do instead. An honest refusal beats a plausible mess in a document
that carries a signature.
"""
from __future__ import annotations

from typing import Dict, List

import fitz                                   # PyMuPDF

from .slots import DocumentPlan, Slot

# PyMuPDF widget types that accept free text. Buttons and signatures do not.
_TEXTUAL = {
    fitz.PDF_WIDGET_TYPE_TEXT,
    fitz.PDF_WIDGET_TYPE_COMBOBOX,
    fitz.PDF_WIDGET_TYPE_LISTBOX,
}


def _label_for(widget, page) -> str:
    """A field's own name is often 'Text12'. Nearby text is usually better."""
    readable = (widget.field_label or "").strip()
    if readable:
        return readable

    name = (widget.field_name or "").strip()
    # Look immediately left of the widget, which is where a form label sits.
    rect = widget.rect
    strip = fitz.Rect(max(0, rect.x0 - 260), rect.y0 - 4, rect.x0 - 2, rect.y1 + 4)
    nearby = " ".join(page.get_textbox(strip).split())
    if nearby and len(nearby) <= 120:
        return nearby.rstrip(" :.")

    return name or "Champ"


def read(path: str, filename: str = "") -> DocumentPlan:
    document = fitz.open(path)
    name = filename or path.rsplit("/", 1)[-1]
    slots: List[Slot] = []
    notes: List[str] = []

    metadata: Dict[str, str] = document.metadata or {}
    title = (metadata.get("title") or "").strip() or name

    if not document.is_form_pdf:
        pages = document.page_count
        has_text = any(document[i].get_text().strip() for i in range(min(pages, 5)))
        document.close()
        notes.append(
            "Ce PDF ne contient pas de champs de formulaire : il n'y a pas "
            "d'emplacement où écrire une réponse."
        )
        notes.append(
            "Un PDF scanné ou mis en page ne peut être rempli qu'en dessinant du "
            "texte à des coordonnées devinées, ce qui se décale à la moindre "
            "substitution de police. Fournissez plutôt le document source "
            "(Word, Excel), ou un PDF avec formulaire."
            if has_text else
            "Le document semble être une image scannée : aucun texte n'en est "
            "extractible. Fournissez le document source."
        )
        return DocumentPlan(filename=name, kind="pdf", title=title, slots=[], notes=notes)

    for number in range(document.page_count):
        page = document[number]
        for order, widget in enumerate(page.widgets() or []):
            if widget.field_type not in _TEXTUAL:
                continue
            value = (widget.field_value or "").strip()
            slots.append(
                Slot(
                    id=f"pdf.p{number}.w{order}",
                    kind="cell",
                    label=_label_for(widget, page),
                    context=[f"Page {number + 1}"],
                    existing=value or None,
                    target={
                        "page": number,
                        "mode": "widget",
                        "field_name": widget.field_name,
                    },
                )
            )

    document.close()
    if not slots:
        notes.append(
            "Formulaire PDF détecté, mais aucun champ texte inscriptible "
            "(cases à cocher et signatures uniquement)."
        )

    return DocumentPlan(filename=name, kind="pdf", title=title, slots=slots, notes=notes)
