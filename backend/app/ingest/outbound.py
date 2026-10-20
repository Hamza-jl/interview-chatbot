"""The only place in the application where client material may leave the building.

Everything that reaches OpenRouter passes through `prepare()`. Nothing else may
call the network with document content, and nothing may call it with an
interview answer at all - `assert_no_answers` is the mechanical guarantee, and
it raises rather than redacts, because a leak you quietly scrub is a leak you
stop noticing.

The split the design rests on:

    the uploaded file      -> may be sent, after redaction and human review
    what a client answered -> never sent, under any configuration

A blank template is a form. It describes what has to be collected, not what
anybody said. That asymmetry is what makes the cloud step acceptable at all, and
the moment it stops holding the feature stops being acceptable.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger("pca.ingest.outbound")


class OutboundRefused(RuntimeError):
    """Raised when something that must not leave was found in a payload."""


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #
# Identifiers that have no bearing on a document's *structure* and therefore no
# business crossing the network. The cloud model is asked to find blanks and
# label them; it does not need to know whose form this is.
_RULES: List[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    # Nine digits or more, however the typist spaced them, with or without a
    # country code. The lower bound keeps years, headcounts and token counts
    # out of it - "8 192 tokens" is not a telephone number.
    ("TEL", re.compile(r"(?<![\d+])\+?(?:\d[ .\-]?){8,14}\d(?!\d)")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("URL", re.compile(r"\bhttps?://\S+", re.IGNORECASE)),
]


def _client_terms() -> List[str]:
    raw = settings.OPENROUTER_REDACT_TERMS or ""
    return [t.strip() for t in raw.split(",") if t.strip()]


def redact(text: str) -> tuple[str, Dict[str, int]]:
    """Blank out identifiers. Returns the cleaned text and what was removed.

    The counts are reported to the consultant, not just logged: "3 e-mails et
    1 nom de client retirés" is a sentence somebody can check, where a silent
    substitution is not.
    """
    counts: Dict[str, int] = {}
    cleaned = text or ""

    for term in _client_terms():
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        cleaned, n = pattern.subn("[CLIENT]", cleaned)
        if n:
            counts["CLIENT"] = counts.get("CLIENT", 0) + n

    for label, pattern in _RULES:
        cleaned, n = pattern.subn(f"[{label}]", cleaned)
        if n:
            counts[label] = counts.get(label, 0) + n

    return cleaned, counts


# --------------------------------------------------------------------------- #
# The invariant
# --------------------------------------------------------------------------- #
def assert_no_answers(payload: str, answers: List[str]) -> None:
    """Refuse to send if anything a client typed appears in the payload.

    Called with every confirmed answer of the session before any outbound
    request. In the normal flow this can never fire: understanding runs at
    upload time, before a single question has been asked. It exists for the
    flow nobody has written yet - a re-analysis of a half-filled document, a
    retry after the interview started - where the mistake would be easy to make
    and impossible to see.
    """
    haystack = (payload or "").lower()
    for answer in answers:
        needle = (answer or "").strip().lower()
        # Short strings produce false positives: "oui", "42", a single surname
        # that also appears in the template's own wording.
        if len(needle) < 12:
            continue
        if needle in haystack:
            raise OutboundRefused(
                "Une réponse d'entretien a été trouvée dans un envoi sortant. "
                "L'envoi est annulé."
            )


# --------------------------------------------------------------------------- #
# The payload
# --------------------------------------------------------------------------- #
@dataclass
class Outbound:
    """What would be sent, ready to be shown to a human before it is."""

    filename: str
    kind: str
    text: str
    redactions: Dict[str, int] = field(default_factory=dict)
    truncated: bool = False
    images: int = 0

    @property
    def size_chars(self) -> int:
        return len(self.text)

    def summary(self) -> str:
        bits = [f"{self.size_chars} caractères"]
        if self.images:
            bits.append(f"{self.images} image(s)")
        if self.truncated:
            bits.append("tronqué")
        if self.redactions:
            bits.append("retiré : " + ", ".join(
                f"{n} {label.lower()}" for label, n in sorted(self.redactions.items())))
        return " · ".join(bits)


# A document far longer than this is a report, not a form. Sending all of it
# costs tokens and buys nothing: the blanks are what matter.
MAX_OUTBOUND_CHARS = 60_000


def prepare(filename: str, kind: str, text: str,
            answers: Optional[List[str]] = None, images: int = 0) -> Outbound:
    """Build the payload for the cloud step: redact, cap, and check the invariant."""
    cleaned, counts = redact(text)

    truncated = len(cleaned) > MAX_OUTBOUND_CHARS
    if truncated:
        cleaned = cleaned[:MAX_OUTBOUND_CHARS]

    assert_no_answers(cleaned, answers or [])

    out = Outbound(filename=filename, kind=kind, text=cleaned,
                   redactions=counts, truncated=truncated, images=images)
    logger.info("outbound prepared: %s (%s)", filename, out.summary())
    return out
