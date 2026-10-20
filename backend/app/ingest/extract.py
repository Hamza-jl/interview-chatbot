"""Get readable content out of any file somebody drops on the application.

Two different jobs hide behind "support every file type", and conflating them
is how this feature would go wrong:

    Reading a file   - turning bytes into text a model can reason about.
    Writing it back  - putting an answer into a specific cell of that same file.

Word, Excel, PowerPoint and fillable PDFs can do both: the readers in this
package already find their blanks and record exact write addresses. A scan, a
photograph of a form, a flat PDF or a text file can only do the first. You can
read a JPEG; you cannot fill one.

So every extraction reports which of the two it supports. A file that can be
read but not written still produces a useful interview - the answers come back
as a new document rather than as the original with its gaps closed - and the
consultant is told that up front rather than discovering it at download time.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("pca.ingest.extract")

# Text formats carry no layout to preserve, so they are read as-is.
_PLAIN = {".txt": "txt", ".md": "md", ".csv": "csv", ".tsv": "csv",
          ".json": "json", ".log": "txt", ".rtf": "rtf"}

_IMAGE = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp",
          ".gif": "gif", ".bmp": "bmp", ".tif": "tiff", ".tiff": "tiff"}

# OpenDocument is a zip like the Office formats, with its own telltale part.
_ODF = {"content.xml": True}


@dataclass
class Extraction:
    """What we managed to read, and what can be done with it."""

    kind: str                       # docx | xlsx | pptx | pdf | png | txt | odt ...
    text: str                       # readable representation, for the cloud model
    fillable: bool                  # can answers be written back into this file?
    pages: int = 1
    images: int = 0                 # pages/figures that need a model that sees
    notes: List[str] = field(default_factory=list)
    # Set only when `fillable`: the deterministic reader found real write
    # addresses. The cloud model never invents these.
    plan: Optional[object] = None

    @property
    def needs_vision(self) -> bool:
        return self.images > 0 and len(self.text.strip()) < 200


def _ext(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()


def sniff(path: str, filename: str = "") -> str:
    """What kind of file this actually is, from its bytes where possible."""
    name = filename or os.path.basename(path)
    ext = _ext(name)

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        for marker, kind in (("word/document.xml", "docx"),
                             ("xl/workbook.xml", "xlsx"),
                             ("ppt/presentation.xml", "pptx")):
            if marker in names:
                return kind
        if "content.xml" in names:
            mimetype = ""
            with zipfile.ZipFile(path) as archive:
                if "mimetype" in names:
                    mimetype = archive.read("mimetype").decode("utf-8", "ignore")
            if "spreadsheet" in mimetype:
                return "ods"
            if "presentation" in mimetype:
                return "odp"
            return "odt"
        return "zip"

    with open(path, "rb") as handle:
        head = handle.read(12)
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"GIF8"):
        return "gif"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"                       # legacy .doc/.xls/.ppt

    return _PLAIN.get(ext, _IMAGE.get(ext, "text"))


# --------------------------------------------------------------------------- #
# Fillable formats: reuse the deterministic readers, which also give us targets
# --------------------------------------------------------------------------- #
def _from_office(path: str, filename: str, kind: str) -> Extraction:
    from . import read_docx, read_pdf, read_pptx, read_xlsx

    reader = {"docx": read_docx, "xlsx": read_xlsx,
              "pptx": read_pptx, "pdf": read_pdf}[kind]
    plan = reader.read(path, filename)

    lines = [f"# {plan.title}"] if plan.title else []
    for slot in plan.slots:
        where = " > ".join(slot.context) if slot.context else ""
        if slot.kind == "grid":
            lines.append(f"[TABLEAU] {where} :: {slot.label} "
                         f"(colonnes : {' | '.join(slot.columns)})")
        else:
            lines.append(f"[CHAMP] {where} :: {slot.label}")
    for note in plan.notes:
        lines.append(f"[NOTE] {note}")

    return Extraction(kind=kind, text="\n".join(lines), fillable=True,
                      notes=list(plan.notes), plan=plan)


# --------------------------------------------------------------------------- #
# Readable-only formats
# --------------------------------------------------------------------------- #
def _from_plain(path: str, kind: str) -> Extraction:
    with open(path, "rb") as handle:
        raw = handle.read()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "replace")

    if kind == "csv":
        # A delimited file reads far better as aligned rows than as raw commas,
        # and the model is being asked to recognise a table.
        try:
            dialect = csv.Sniffer().sniff(text[:4000])
            rows = list(csv.reader(io.StringIO(text), dialect))
            text = "\n".join(" | ".join(cell.strip() for cell in row)
                             for row in rows[:400])
        except (csv.Error, StopIteration):
            pass

    return Extraction(kind=kind, text=text, fillable=False,
                      notes=["Ce format ne peut pas être rempli sur place : "
                             "les réponses seront livrées dans un nouveau document."])


def _from_odf(path: str, kind: str) -> Extraction:
    import re

    with zipfile.ZipFile(path) as archive:
        xml = archive.read("content.xml").decode("utf-8", "ignore")
    # Paragraph and cell boundaries become newlines so the structure survives.
    xml = re.sub(r"</(?:text:p|text:h|table:table-row)>", "\n", xml)
    xml = re.sub(r"</table:table-cell>", " | ", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return Extraction(kind=kind, text=text.strip(), fillable=False,
                      notes=["Format OpenDocument : lecture possible, "
                             "remplissage sur place non pris en charge. "
                             "Les réponses seront livrées dans un nouveau document."])


def _from_image(path: str, kind: str) -> Extraction:
    size = os.path.getsize(path)
    return Extraction(
        kind=kind, text="", fillable=False, images=1,
        notes=[f"Image de {size // 1024} Ko : son contenu sera lu par un modèle "
               "capable de voir. Les réponses seront livrées dans un nouveau document."])


def _from_pdf_flat(path: str, filename: str) -> Extraction:
    """A PDF with no form fields: readable, not fillable."""
    import fitz

    document = fitz.open(path)
    pages = document.page_count
    chunks, drawn = [], 0
    for page in document:
        chunks.append(page.get_text())
        drawn += len(page.get_images())
    document.close()

    text = "\n".join(chunks).strip()
    notes = ["PDF sans champ de formulaire : lecture possible, remplissage sur "
             "place impossible. Les réponses seront livrées dans un nouveau document."]
    if len(text) < 200 and drawn:
        notes.append("Peu de texte extractible : le document semble scanné, "
                     "il sera lu comme une image.")
    return Extraction(kind="pdf", text=text, fillable=False, pages=pages,
                      images=drawn if len(text) < 200 else 0, notes=notes)


# --------------------------------------------------------------------------- #
class Unreadable(Exception):
    """Raised with a message meant for the person who uploaded the file."""


_LEGACY = {
    "ole": "Format Office 97-2003 (.doc, .xls, .ppt). Enregistrez-le au format "
           "récent (.docx, .xlsx, .pptx) et réessayez.",
    "zip": "Archive non reconnue. Déposez le document lui-même plutôt qu'une archive.",
}


def read(path: str, filename: str = "") -> Extraction:
    """Read any supported file. Raises `Unreadable` with a reason for the rest."""
    name = filename or os.path.basename(path)
    kind = sniff(path, name)

    if kind in _LEGACY:
        raise Unreadable(_LEGACY[kind])

    if kind in ("docx", "xlsx", "pptx"):
        return _from_office(path, name, kind)

    if kind == "pdf":
        # A fillable PDF keeps its write addresses; a flat one does not.
        from . import read_pdf
        try:
            return _from_office(path, name, "pdf")
        except Exception:                                   # noqa: BLE001
            return _from_pdf_flat(path, name)

    if kind in ("odt", "ods", "odp"):
        return _from_odf(path, kind)

    if kind in _IMAGE.values():
        return _from_image(path, kind)

    if kind in ("txt", "md", "csv", "json", "rtf", "text"):
        return _from_plain(path, "csv" if kind == "csv" else "txt")

    raise Unreadable(
        f"Format non reconnu ({kind}). Formats lus : Word, Excel, PowerPoint, "
        "PDF, OpenDocument, images, CSV et texte."
    )
