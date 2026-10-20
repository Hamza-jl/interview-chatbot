"""OpenRouter: one big model, reached through a list of them.

Used for a single job - reading an uploaded file well enough to write questions
from it. That job needs a model no bank server will host, and it runs once per
document rather than once per sentence, so the cost and the latency are
acceptable where they would not be inside the interview.

The fallback chain is the point. A hosted model is not a dependency you control:
it is rate-limited on somebody else's schedule, retired with a blog post, and
briefly unavailable for reasons nobody explains. Pinning one would mean an
upload that worked on Tuesday fails on Wednesday. So `structured()` walks the
configured list and returns the first model that answers, recording which one it
was - the consultant is told, because "which model read my document" is a fair
question in a bank.

What is NOT here: any path that sends an interview answer. Everything outbound
is built by `app.ingest.outbound`, which refuses payloads containing client
replies. This module takes text that has already been through that gate.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger("pca.openrouter")


class OpenRouterUnavailable(RuntimeError):
    """Every model in the chain failed."""


@dataclass
class CloudResult:
    data: Dict[str, Any]
    model: str                 # the one that actually answered
    attempts: List[str]        # everything tried, in order
    seconds: float


def models() -> List[str]:
    raw = settings.OPENROUTER_MODELS or ""
    return [m.strip() for m in raw.split(",") if m.strip()]


def keys() -> List[str]:
    """Free models are rate-limited per key, so several keys buy throughput."""
    raw = settings.OPENROUTER_API_KEY or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def available() -> bool:
    return bool(settings.OPENROUTER_ENABLED and keys() and models())


# HTTP statuses where trying the next model is the right move. A 401 is a
# configuration mistake and will fail identically on every model, so it stops
# the chain instead of hammering the whole list.
_FALL_THROUGH = {408, 409, 413, 500, 502, 503, 504}
# Epuisement de quota : la cle est en cause, pas le modele.
_PER_KEY = {402, 429}
_FATAL = {400, 401, 403}


def _post(model: str, system: str, user: str, schema: Dict[str, Any],
          max_tokens: int, key: str) -> Dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "document", "strict": True, "schema": schema},
        },
    }
    request = urllib.request.Request(
        f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # OpenRouter asks callers to identify themselves; it also keeps the
            # usage dashboard legible when several tools share one key.
            "HTTP-Referer": "https://devoteam.com",
            "X-Title": "SMART PCA Collect",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=settings.OPENROUTER_TIMEOUT) as response:
        body = json.loads(response.read().decode("utf-8"))

    choices = body.get("choices") or []
    if not choices:
        raise OpenRouterUnavailable(f"{model}: réponse sans contenu")
    content = (choices[0].get("message") or {}).get("content") or ""
    # Some providers return the message as a list of parts rather than a string.
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content
                          if isinstance(part, dict))
    if not content.strip():
        # A reasoning model that spent its whole budget thinking answers with an
        # empty message and no error. Treat it as a failure so the chain moves on.
        raise OpenRouterUnavailable(
            f"{model}: message vide (budget de tokens probablement épuisé par le "
            "raisonnement)")
    try:
        return json.loads(content)
    except ValueError as exc:
        # Some models wrap JSON in prose despite the schema. One rescue attempt,
        # then it counts as a failure and the chain moves on.
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except ValueError:
                pass
        raise OpenRouterUnavailable(f"{model}: JSON illisible") from exc


def structured(*, system: str, user: str, schema: Dict[str, Any],
               max_tokens: Optional[int] = None) -> CloudResult:
    """Walk the chain until something answers. Raises only if nothing does.

    Two loops, not one. The outer walks the models; the inner walks the keys,
    because on the free tier a 429 says "this key is spent for now", not "this
    model is unusable". Rotating the key first keeps a preferred model in play
    instead of demoting it over a quota that resets in a minute.
    """
    if not available():
        raise OpenRouterUnavailable(
            "OpenRouter n'est pas configuré (clé absente ou option désactivée)."
        )

    chain, credentials = models(), keys()
    budget = max_tokens or settings.OPENROUTER_MAX_TOKENS
    attempts: List[str] = []
    started = time.perf_counter()
    last: Optional[str] = None

    for model in chain:
        attempts.append(model)
        for index, key in enumerate(credentials):
            try:
                data = _post(model, system, user, schema, budget, key)
                elapsed = round(time.perf_counter() - started, 1)
                if len(attempts) > 1 or index:
                    logger.info("openrouter: %s a répondu (clé %d) après %d tentative(s)",
                                model, index + 1, len(attempts) - 1 + index)
                return CloudResult(data=data, model=model, attempts=attempts,
                                   seconds=elapsed)

            except urllib.error.HTTPError as exc:
                last = f"{model}: HTTP {exc.code}"
                if exc.code in _FATAL:
                    logger.error("openrouter: %s — clé ou requête invalide", last)
                    raise OpenRouterUnavailable(
                        f"Appel refusé ({exc.code}). Vérifiez la clé OpenRouter."
                    ) from exc
                if exc.code in _PER_KEY and index + 1 < len(credentials):
                    logger.info("openrouter: %s saturé sur la clé %d, clé suivante",
                                model, index + 1)
                    continue
                logger.info("openrouter: %s indisponible (%s), modèle suivant",
                            model, exc.code)
                break

            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = f"{model}: {exc}"
                logger.info("openrouter: %s injoignable, modèle suivant", model)
                break

            except OpenRouterUnavailable as exc:
                last = str(exc)
                logger.info("openrouter: %s", exc)
                break

    raise OpenRouterUnavailable(
        f"Aucun des {len(chain)} modèles n'a répondu. Dernière erreur — {last}"
    )
