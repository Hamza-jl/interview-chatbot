"""Show the interview a document would produce, without running one.

    python -m app.scripts.preview_interview mon-fichier.docx

Point it at any .docx, .xlsx, .pptx or fillable .pdf and it prints, in order,
every question the chatbot would ask - with the hint, the example, and the exact
place in the document each answer would be written.

The write-back is not built yet, so this is the honest half: it shows what was
understood. Two things are worth looking at in the output.

  The addresses. "table 4, ligne 2, colonne 1" is where an answer lands. If the
  wrong blank was found, it shows here, before anything can be written wrongly.

  The questions. Phrasing is the only part a model decides, so it is the only
  part that can be subjectively wrong.

Use --sans-modele for structure only. It answers in well under a second and
tells you whether a disappointing result is the reader's fault or the model's.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Optional

from app.ingest import questions, reader
from app.ingest.slots import DocumentPlan, Slot

_KIND = {"docx": "Word", "xlsx": "Excel", "pptx": "PowerPoint", "pdf": "PDF"}


def _where(slot: Slot) -> str:
    """The write address, in words, so a wrong one is obvious."""
    t = slot.target
    mode = t.get("mode")
    if mode == "cell" and "table" in t:
        return f"tableau {t['table']}, ligne {t['row']}, colonne {t['col'] + 1}"
    if mode == "grid" and "table" in t:
        return f"tableau {t['table']}, lignes sous l'en-tete"
    if mode == "cell" and "sheet" in t:
        return f"feuille « {t['sheet']} », ligne {t['row']}, colonne {t['col']}"
    if mode == "grid" and "sheet" in t:
        return f"feuille « {t['sheet']} », sous la ligne {t['header_row']}"
    if mode == "grid" and "slide" in t:
        return f"diapositive {t['slide']}, tableau"
    if mode == "text":
        return f"diapositive {t['slide']}, zone de texte"
    if mode == "widget":
        return f"page {t['page'] + 1}, champ « {t.get('field_name', '?')} »"
    return str(t)


def _wrap(text: str, width: int, indent: str) -> str:
    import textwrap

    return textwrap.fill(
        text, width=width, initial_indent=indent, subsequent_indent=indent
    )


def show(plan: DocumentPlan, use_model: bool, limit: int, width: int) -> List[dict]:
    print()
    print(f"  Fichier   : {plan.filename}")
    print(f"  Format    : {_KIND.get(plan.kind, plan.kind)}")
    print(f"  Titre     : {plan.title[:70]}")
    print(f"  Detecte   : {len(plan.cells)} champ(s), {len(plan.grids)} tableau(x)")
    if plan.notes:
        print()
        for note in plan.notes:
            print(_wrap(note, width, "  ! "))
    if not plan.slots:
        print()
        return []

    slots = plan.slots[:limit] if limit else plan.slots
    if len(slots) < len(plan.slots):
        print(f"  (aperçu limite aux {len(slots)} premiers ; --tout pour la suite)")
    print()
    print("  " + "─" * (width - 4))

    out: List[dict] = []
    for index, slot in enumerate(slots, 1):
        generated = (
            questions.generate(slot) if use_model else questions.fallback(slot)
        )
        badge = "TABLEAU" if slot.kind == "grid" else "CHAMP"
        timing = f"  ({generated.seconds}s)" if generated.seconds else ""

        print()
        print(f"  {index:2}. [{badge}] {slot.section or '—'}{timing}")
        print(_wrap(generated.question, width, "      "))
        if generated.help:
            print(_wrap(generated.help, width, "      · "))
        if slot.kind == "grid":
            print(f"      colonnes : {' | '.join(slot.columns)}")
        if generated.example:
            print(_wrap(f"ex. {generated.example}", width, "      → "))
        print(f"      écrit dans : {_where(slot)}")

        out.append(
            {
                "slot": slot.id,
                "kind": slot.kind,
                "label": slot.label,
                "section": slot.section,
                "question": generated.question,
                "aide": generated.help,
                "exemple": generated.example,
                "colonnes": slot.columns,
                "cible": slot.target,
                "moteur": generated.engine,
                "secondes": generated.seconds,
            }
        )

    print()
    print("  " + "─" * (width - 4))
    engines = {r["moteur"] for r in out}
    total = round(sum(r["secondes"] for r in out), 1)
    print(f"  {len(out)} question(s) — moteur : {', '.join(sorted(engines))}"
          + (f" — {total}s" if total else ""))
    print()
    return out


def main(argv: Optional[List[str]] = None) -> int:
    # A French questionnaire is full of accents and this draws box rules, but a
    # Windows console defaults to cp1252 and raises on both. Printing the plan
    # is the whole point of the script, so it must not die on its own output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fichier", nargs="+", help=".docx, .xlsx, .pptx ou .pdf")
    parser.add_argument("--sans-modele", action="store_true", dest="no_model",
                        help="structure seule, sans inference (instantane)")
    parser.add_argument("--tout", action="store_true",
                        help="toutes les questions, pas seulement les premieres")
    parser.add_argument("--limite", type=int, default=12)
    parser.add_argument("--largeur", type=int, default=84)
    parser.add_argument("--json", metavar="CHEMIN", help="ecrit le detail")
    args = parser.parse_args(argv)

    everything = []
    for path in args.fichier:
        if not os.path.exists(path):
            print(f"  Fichier introuvable : {path}", file=sys.stderr)
            return 1
        try:
            plan = reader.read(path, os.path.basename(path))
        except reader.UnsupportedDocument as refused:
            print()
            print(f"  {os.path.basename(path)}")
            print(_wrap(str(refused), args.largeur, "  ! "))
            print()
            continue
        rows = show(plan, not args.no_model, 0 if args.tout else args.limite, args.largeur)
        everything.append({"fichier": plan.filename, "questions": rows})

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(everything, handle, ensure_ascii=False, indent=2)
        print(f"  Detail ecrit dans {args.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
