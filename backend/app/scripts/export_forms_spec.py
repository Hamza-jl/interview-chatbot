"""Emit the question plan as JSON, for the Google Forms generator.

The forms and the chatbot must ask exactly the same questions in exactly the
same order, or the two collection routes produce documents that disagree. So
the forms are generated *from* the blueprint rather than transcribed from it:
this script is the only bridge, and re-running it is how a change to the plan
reaches the forms.

    python -m app.scripts.export_forms_spec ../google-forms/Questions.gs

Writes an Apps Script file declaring `var SPEC = {...}` - Apps Script has no
way to read a local JSON file, so the spec ships as source. Pass `--json` to
get plain JSON instead, for anything else that wants it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any, Dict, List

from app.pca.blueprint import TEMPLATE_FILES, Question, get_plan, sections
from app.scripts.seed import STRUCTURES

TEMPLATE_LABEL = {
    "dsi": "Direction des Systèmes d'Information",
    "entite": "Entité",
}


def _column(column) -> Dict[str, Any]:
    return {
        "id": column.id,
        "label": column.label,
        "hint": column.hint,
        "choices": list(column.choices) if column.choices else None,
        "required": bool(column.required),
    }


def _question(question: Question, index: int) -> Dict[str, Any]:
    return {
        "id": question.id,
        "index": index,
        "kind": question.kind,            # field | open | grid
        "section": question.section,
        "label": question.label,
        "prompt": question.prompt,
        "help": question.help,
        "example": question.example,
        "optional": bool(question.optional),
        "minRows": question.min_rows,
        "columns": [_column(c) for c in question.columns],
    }


def build_spec() -> Dict[str, Any]:
    plans: Dict[str, Any] = {}
    for kind in TEMPLATE_FILES:
        plan = get_plan(kind)
        plans[kind] = {
            "label": TEMPLATE_LABEL.get(kind, kind),
            "sections": list(sections(kind)),
            "questions": [_question(q, i) for i, q in enumerate(plan)],
        }

    return {
        "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "note": "Généré depuis app/pca/blueprint.py - ne pas modifier à la main.",
        "plans": plans,
        "structures": [
            {"code": code, "name": name, "parent": parent, "templateKind": kind}
            for code, name, parent, kind in STRUCTURES
        ],
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="output file (.gs or .json)")
    parser.add_argument("--json", action="store_true", help="write plain JSON")
    args = parser.parse_args(argv)

    spec = build_spec()
    payload = json.dumps(spec, ensure_ascii=False, indent=2)

    if args.json or args.target.endswith(".json"):
        body = payload
    else:
        body = (
            "/**\n"
            " * Question plan for the état des lieux forms.\n"
            " *\n"
            " * GENERATED FILE - do not edit. Regenerate with:\n"
            " *   python -m app.scripts.export_forms_spec google-forms/Questions.gs\n"
            f" * Generated: {spec['generated']}\n"
            " */\n\n"
            f"var SPEC = {payload};\n"
        )

    os.makedirs(os.path.dirname(os.path.abspath(args.target)) or ".", exist_ok=True)
    with open(args.target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)

    counts = ", ".join(
        f"{kind} {len(plan['questions'])}" for kind, plan in spec["plans"].items()
    )
    print(f"wrote {args.target}")
    print(f"  plans      : {counts}")
    print(f"  structures : {len(spec['structures'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
