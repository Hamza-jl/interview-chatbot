"""What a blank in a document looks like, whatever the format it came from.

A *slot* is one place an answer will be written, plus enough context to ask a
sensible question about it. Discovering slots is deterministic: a model is never
asked where the blanks are, because getting that wrong writes an answer into the
wrong cell of a document somebody signs.

Two shapes cover the overwhelming majority of real forms:

``cell``   one label, one value. "Nom du responsable" followed by an empty cell.
``grid``   a header row over empty rows. Repeating data - applications, contacts,
           incidents - where the number of entries is not known in advance.

The ``target`` dictionary is the write address, and its keys differ per format.
Nothing outside the format's own reader and writer should interpret it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# A cell that holds one of these is empty in every way that matters: a dotted
# fill, an underscore rule, a bracketed instruction left in by the author.
_PLACEHOLDER = re.compile(
    r"^[\s.．_\-–—…·:;/\\|]*$"                       # rules and separators
    r"|^[\[\(<{].{0,60}[\]\)>}]$"                    # [à compléter], (nom)
    r"|^(?:n/?a|néant|neant|nc|ras|xxx+|aaa+|\?+)$", # explicit nothings
    re.IGNORECASE,
)

# Text that announces a value rather than being one. Used to tell a label column
# from a value column when both happen to contain something.
_LABELISH = re.compile(r":\s*$|^\s*\d+[.)]\s+")


def is_blank(text: Optional[str]) -> bool:
    """True when a cell carries no answer, only furniture."""
    if text is None:
        return True
    stripped = text.strip()
    return not stripped or bool(_PLACEHOLDER.match(stripped))


def looks_like_label(text: str) -> bool:
    return bool(_LABELISH.search(text or ""))


@dataclass
class Slot:
    """One answerable blank, addressed precisely enough to write back into."""

    id: str
    kind: str                                   # "cell" | "grid"
    label: str
    target: Dict[str, Any]
    # Headings and nearby text, nearest last. This is what lets a question be
    # phrased usefully: "Effectif" alone means little, "Effectif" under
    # "2. Organisation et moyens humains" means something.
    context: List[str] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    # Anything already in the document at this position - an example row, a
    # pre-filled default. Kept because it is the best possible hint about the
    # shape of the expected answer, and because overwriting it silently is rude.
    existing: Optional[str] = None
    min_rows: int = 1

    @property
    def section(self) -> str:
        return self.context[-1] if self.context else ""

    def describe(self) -> str:
        """A compact line for a model prompt or a log."""
        where = " > ".join(self.context[-2:]) if self.context else "(sans section)"
        if self.kind == "grid":
            return f"[tableau] {self.label} — colonnes : {' | '.join(self.columns)} — dans : {where}"
        return f"[champ] {self.label} — dans : {where}"


@dataclass
class DocumentPlan:
    """Everything discovered in one uploaded file."""

    filename: str
    kind: str                                   # docx | xlsx | pptx | pdf
    title: str
    slots: List[Slot] = field(default_factory=list)
    # Why a document yielded fewer slots than expected - a scanned PDF, a
    # protected sheet. Surfaced to the user rather than silently swallowed.
    notes: List[str] = field(default_factory=list)

    @property
    def cells(self) -> List[Slot]:
        return [s for s in self.slots if s.kind == "cell"]

    @property
    def grids(self) -> List[Slot]:
        return [s for s in self.slots if s.kind == "grid"]

    def summary(self) -> str:
        return (
            f"{self.filename} — {len(self.cells)} champ(s), {len(self.grids)} tableau(x)"
        )
