"""Pick the right reader for an uploaded file, and refuse the rest clearly."""
from __future__ import annotations

import os
import zipfile
from typing import Callable, Dict

from .slots import DocumentPlan

# The extension is a hint, never the decision: an .xlsx renamed .docx must not
# reach the Word reader and raise a confusing parser error.
SUPPORTED = {".docx": "docx", ".xlsx": "xlsx", ".xlsm": "xlsx", ".pptx": "pptx", ".pdf": "pdf"}

# Each modern Office format is a zip holding one telltale part.
_ZIP_MARKERS = (
    ("word/document.xml", "docx"),
    ("xl/workbook.xml", "xlsx"),
    ("ppt/presentation.xml", "pptx"),
)

# Formats people will try, with the reason each is refused rather than guessed.
_REFUSED = {
    ".doc": "Format Word 97-2003. Enregistrez-le en .docx et réessayez.",
    ".xls": "Format Excel 97-2003. Enregistrez-le en .xlsx et réessayez.",
    ".ppt": "Format PowerPoint 97-2003. Enregistrez-le en .pptx et réessayez.",
    ".odt": "Format OpenDocument. Exportez-le en .docx et réessayez.",
    ".ods": "Format OpenDocument. Exportez-le en .xlsx et réessayez.",
    ".csv": "Un CSV n'a pas de mise en forme à préserver : convertissez-le en .xlsx.",
    ".txt": "Un fichier texte n'a pas d'emplacements à remplir.",
}


class UnsupportedDocument(Exception):
    """Raised with a message meant to be shown to the person who uploaded."""


def detect(path: str, filename: str = "") -> str:
    name = filename or os.path.basename(path)
    extension = os.path.splitext(name)[1].lower()

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        for marker, kind in _ZIP_MARKERS:
            if marker in names:
                return kind
        raise UnsupportedDocument(
            "Archive non reconnue. Attendu : Word, Excel ou PowerPoint récents."
        )

    with open(path, "rb") as handle:
        if handle.read(5) == b"%PDF-":
            return "pdf"

    if extension in _REFUSED:
        raise UnsupportedDocument(_REFUSED[extension])
    raise UnsupportedDocument(
        f"Format non pris en charge ({extension or 'sans extension'}). "
        "Formats acceptés : .docx, .xlsx, .pptx, .pdf."
    )


def read(path: str, filename: str = "") -> DocumentPlan:
    kind = detect(path, filename)

    readers: Dict[str, Callable[..., DocumentPlan]] = {}
    from . import read_docx, read_pdf, read_pptx, read_xlsx

    readers = {
        "docx": read_docx.read,
        "xlsx": read_xlsx.read,
        "pptx": read_pptx.read,
        "pdf": read_pdf.read,
    }
    return readers[kind](path, filename or os.path.basename(path))
