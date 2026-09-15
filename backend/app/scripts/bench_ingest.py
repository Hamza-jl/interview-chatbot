"""Compare local models on the one job the ingestion path gives them.

    python -m app.scripts.bench_ingest --models qwen2.5:3b qwen3:4b

The task is not "read a document" - it is "phrase a question about one blank,
as JSON". That is what the pipeline actually asks for, so it is what gets
measured. Slots come from the real templates rather than invented examples,
because a benchmark on made-up input tells you about the made-up input.

Scored on what would make a generated interview unusable:

  valide      the answer parsed as the required JSON at all
  francais    French, not the English a Qwen model drifts into under pressure
  question    reads as a question, not a restatement of the label
  original    does not merely echo the label back
  colonnes    for tables: the example has the right number of columns, which is
              what the deterministic row parser needs downstream
  secondes    median, because one slow call among forty is noise and a slow
              median is a slow interview

No aggregate score is printed. The failures differ in cost - a wrong column
count breaks parsing, an English question is merely embarrassing - so the
columns stay separate and the choice stays yours.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import unicodedata
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.ingest import questions, read_docx
from app.ingest.slots import Slot

# Words that are common in French and rare in English, and vice versa. Crude on
# purpose: it only has to catch a model answering the wrong language outright.
_FR = {"quel", "quelle", "quels", "quelles", "votre", "vos", "pouvez", "decrivez",
       "precisez", "indiquez", "listez", "entite", "ligne", "par", "les", "des",
       "dans", "pour", "une", "est", "sont", "avec"}
_EN = {"what", "which", "please", "describe", "provide", "list", "your", "the",
       "and", "for", "with", "are", "is", "each", "row"}


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def is_french(text: str) -> bool:
    words = set(_fold(text).replace("'", " ").split())
    return len(words & _FR) >= len(words & _EN)


def reads_as_question(text: str) -> bool:
    folded = _fold(text).strip()
    if folded.endswith("?"):
        return True
    # An imperative is a perfectly good way to ask for something.
    return folded.startswith((
        "decrivez", "precisez", "indiquez", "listez", "detaillez", "citez",
        "donnez", "renseignez", "completez", "pouvez",
    ))


def echoes_label(text: str, label: str) -> bool:
    """A question that is the label with a question mark bolted on."""
    q = _fold(text).strip(" ?«».:")
    l = _fold(label).strip(" ?«».:")
    return q == l or (len(q) <= len(l) + 12 and l in q and len(q) - len(l) < 10)


def column_count_ok(parsed: Dict[str, Any], slot: Slot) -> Optional[bool]:
    """None when it does not apply; the grid parser downstream needs this exact.

    Measured on what the model returned, not on the padded result - padding is
    the safety net, and a benchmark that scores the safety net tells you nothing
    about the model.
    """
    if slot.kind != "grid" or not slot.columns:
        return None
    return len(parsed.get("cellules") or []) == len(slot.columns)


def call(model: str, slot: Slot, timeout: float) -> Dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": questions.SYSTEM},
            {"role": "user", "content": questions.prompt_for(slot)},
        ],
        "format": questions.schema_for(slot),
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 4096},
        # Qwen3 reasons before answering unless told not to; the thinking is
        # pure latency for a task this small, and it wraps the JSON in prose.
        "think": False,
    }
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=body)
            response.raise_for_status()
            raw = response.json()["message"]["content"]
    except Exception as exc:                                   # noqa: BLE001
        return {"ok": False, "seconds": time.perf_counter() - started, "error": str(exc)[:90]}
    return {"ok": True, "seconds": time.perf_counter() - started, "raw": raw}


def evaluate(model: str, slots: List[Slot], timeout: float, verbose: bool) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for index, slot in enumerate(slots, 1):
        result = call(model, slot, timeout)
        parsed = questions.parse(result.get("raw", "")) if result["ok"] else None

        row = {
            "slot": slot.id,
            "kind": slot.kind,
            "seconds": result["seconds"],
            "valid": parsed is not None,
            "french": False,
            "question": False,
            "original": False,
            "columns": None,
            "text": "",
        }
        if parsed:
            q = parsed["question"]
            row.update(
                french=is_french(q),
                question=reads_as_question(q),
                original=not echoes_label(q, slot.label),
                columns=column_count_ok(parsed, slot),
                text=q,
            )
        rows.append(row)
        if verbose:
            mark = "ok " if row["valid"] else "KO "
            print(f"    {mark}{index:2}/{len(slots)}  {row['seconds']:5.1f}s  {row['text'][:72]}")
        else:
            print(".", end="", flush=True)

    if not verbose:
        print()

    graded = [r for r in rows if r["valid"]]
    grids = [r for r in rows if r["columns"] is not None]
    total = len(rows)

    def pct(n: int, d: int) -> str:
        return f"{100 * n // d}%" if d else "—"

    return {
        "model": model,
        "n": total,
        "valide": pct(sum(r["valid"] for r in rows), total),
        "francais": pct(sum(r["french"] for r in graded), len(graded)),
        "question": pct(sum(r["question"] for r in graded), len(graded)),
        "original": pct(sum(r["original"] for r in graded), len(graded)),
        "colonnes": pct(sum(1 for r in grids if r["columns"]), len(grids)),
        "mediane_s": round(statistics.median(r["seconds"] for r in rows), 1),
        "total_s": round(sum(r["seconds"] for r in rows), 1),
        "rows": rows,
    }


def gather_slots(paths: List[str], limit: int) -> List[Slot]:
    slots: List[Slot] = []
    for path in paths:
        plan = read_docx.read(path, path.rsplit("/", 1)[-1])
        # Interleave cells and grids so a truncated run still covers both.
        cells, grids = plan.cells, plan.grids
        for i in range(max(len(cells), len(grids))):
            if i < len(cells):
                slots.append(cells[i])
            if i < len(grids):
                slots.append(grids[i])
    return slots[:limit] if limit else slots


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["qwen2.5:3b", "qwen3:4b"])
    parser.add_argument("--templates", nargs="+",
                        default=["templates/etat_des_lieux_entite.docx"])
    parser.add_argument("--limit", type=int, default=16, help="slots per model (0 = all)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", metavar="PATH", help="write the full results")
    args = parser.parse_args(argv)

    slots = gather_slots(args.templates, args.limit)
    if not slots:
        print("Aucun champ trouve dans les modeles fournis.", file=sys.stderr)
        return 1

    print(f"\n  {len(slots)} champ(s) reels "
          f"({sum(1 for s in slots if s.kind == 'grid')} tableaux), "
          f"{len(args.models)} modele(s)\n")

    results = []
    for model in args.models:
        print(f"  {model}")
        results.append(evaluate(model, slots, args.timeout, args.verbose))
        print()

    headers = ["modele", "valide", "francais", "question", "original", "colonnes",
               "mediane_s", "total_s"]
    widths = [max(len(h), max(len(str(r[h.replace('modele', 'model')])) for r in results))
              for h in headers]

    print("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in results:
        cells = [str(r[h.replace("modele", "model")]) for h in headers]
        print("  " + "  ".join(c.ljust(w) for c, w in zip(cells, widths)))
    print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2)
        print(f"  Detail ecrit dans {args.json}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
