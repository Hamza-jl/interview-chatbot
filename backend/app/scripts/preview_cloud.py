"""Read any file through the hosted model and show what came back.

    python -m app.scripts.preview_cloud mon-fichier.pdf

Point it at anything - a Word questionnaire, a spreadsheet, a scan, a
photograph of a form, a CSV - and it prints three things:

  What would be sent.   The exact payload, after redaction. This is the review
                        step: if a client name survives into it, you want to
                        know here and not from a provider's logs.

  Which model answered. The chain is walked in order and the first model that
                        responds wins. "Which model read my document" is a fair
                        question in a bank, so it is recorded.

  What it understood.   Every field, and crucially whether each one can be
                        written back into the original file or only collected.

Use --envoi to see the payload in full before anything leaves, and --sec to
stop after that, without calling out at all.
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
from typing import List, Optional


def _wrap(text: str, width: int, indent: str) -> str:
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fichier", nargs="+")
    parser.add_argument("--envoi", action="store_true",
                        help="afficher le contenu exact qui serait envoyé")
    parser.add_argument("--sec", action="store_true",
                        help="s'arrêter avant l'appel distant")
    parser.add_argument("--largeur", type=int, default=84)
    args = parser.parse_args(argv)

    from app.ai import openrouter
    from app.ingest import extract, outbound, understand

    width = args.largeur

    for path in args.fichier:
        name = os.path.basename(path)
        print()
        print("=" * width)
        print(f"  {name}")
        print("=" * width)

        if not os.path.exists(path):
            print("  Fichier introuvable.")
            continue

        # ---- lecture locale -------------------------------------------- #
        try:
            ex = extract.read(path, name)
        except extract.Unreadable as refus:
            print(_wrap(str(refus), width, "  ! "))
            continue
        except Exception as exc:                            # noqa: BLE001
            print(f"  Lecture impossible : {exc}")
            continue

        deterministes = len(ex.plan.slots) if ex.plan else 0
        print(f"\n  Format          {ex.kind}")
        print(f"  Remplissable    {'oui, sur place' if ex.fillable else 'non — réponses dans un nouveau document'}")
        print(f"  Repéré en local {deterministes} emplacement(s)")
        if ex.images:
            print(f"  Images          {ex.images} (lecture par modèle visuel)")
        for note in ex.notes:
            print(_wrap(note, width, "  · "))

        # ---- ce qui partirait ------------------------------------------- #
        sent = outbound.prepare(name, ex.kind, ex.text, images=ex.images)
        print(f"\n  CE QUI SERAIT ENVOYÉ")
        print(f"  {sent.summary()}")
        if args.envoi:
            print("  " + "-" * (width - 4))
            for line in sent.text.splitlines()[:60]:
                print("  | " + line[:width - 6])
            if len(sent.text.splitlines()) > 60:
                print("  | …")
            print("  " + "-" * (width - 4))

        if args.sec:
            print("\n  (--sec : aucun appel distant)")
            continue

        if not openrouter.available():
            print("\n  OpenRouter n'est pas activé : définissez OPENROUTER_ENABLED "
                  "et OPENROUTER_API_KEY.")
            continue

        # ---- appel distant ---------------------------------------------- #
        try:
            u = understand.understand(ex, name)
        except openrouter.OpenRouterUnavailable as exc:
            print(_wrap(str(exc), width, "  ! "))
            continue
        except outbound.OutboundRefused as exc:
            print(_wrap(str(exc), width, "  ! REFUS : "))
            continue

        print(f"\n  Modèle          {u.model}")
        if len(u.attempts) > 1:
            print(f"  Tentatives      {' → '.join(u.attempts)}")
        print(f"  Durée           {u.seconds}s")
        print(f"  Titre           {u.plan.title[:width - 20]}")
        print(f"  Champs          {len(u.plan.slots)}  "
              f"(rattachés : {u.matched}, inventés refusés : {u.invented})")

        if u.plan.slots:
            print()
            for index, slot in enumerate(u.plan.slots, 1):
                cible = "écrit sur place" if slot.target else "collecté seulement"
                genre = "TABLEAU" if slot.kind == "grid" else "CHAMP  "
                print(f"  {index:2}. [{genre}] {slot.label[:width - 36]}")
                if slot.section:
                    print(f"      section : {slot.section[:width - 18]}")
                if slot.columns:
                    print(_wrap("colonnes : " + " | ".join(slot.columns),
                                width, "      "))
                print(f"      → {cible}")

        for note in u.plan.notes[len(ex.notes):]:
            print(_wrap(note, width, "  ! "))

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
