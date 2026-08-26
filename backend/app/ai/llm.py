"""Model access layer.

Two backends, one interface:

* **Anthropic** (`claude-opus-5`) - a single schema-constrained call resolves
  routing and extraction together.
* **Ollama** (`qwen2.5:3b` by default) - fully local, nothing leaves the bank's
  network. A 3B model cannot fill an eight-field schema in one pass, so
  ``app.ai.engine`` drives it as several small single-purpose calls instead.
  Both are constrained by JSON schema, so neither can return prose where the
  pipeline expects a document value.

Neither backend is given tools. The model cannot read the database, reach the
network or touch the filesystem; the only consequence of a turn is text written
into the client's own deliverable.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger("pca.llm")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MAX_USER_CHARS = 8000


class LLMUnavailable(RuntimeError):
    pass


def sanitize(text: str) -> str:
    """Strip control characters and cap length before anything sees the text."""
    cleaned = _CONTROL.sub("", text or "").strip()
    return cleaned[:MAX_USER_CHARS]


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #
class AnthropicBackend:
    name = "anthropic"

    def __init__(self) -> None:
        self._client = None

    @property
    def available(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    @property
    def label(self) -> str:
        return settings.LLM_MODEL

    def _ensure(self):
        if self._client is None:
            if not self.available:
                raise LLMUnavailable("ANTHROPIC_API_KEY is not configured")
            import anthropic  # imported lazily so the app boots without the key

            self._client = anthropic.Anthropic(
                api_key=settings.ANTHROPIC_API_KEY, timeout=90.0, max_retries=2
            )
        return self._client

    def structured(
        self,
        *,
        system: str,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        client = self._ensure()
        response = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            # Stable prefix, cached across every turn of every interview.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={
                "effort": settings.LLM_EFFORT,
                "format": {"type": "json_schema", "schema": schema},
            },
        )

        if getattr(response, "stop_reason", None) == "refusal":
            detail = getattr(response, "stop_details", None)
            logger.warning("model declined the turn: %s", getattr(detail, "category", None))
            raise LLMUnavailable("model declined to process this turn")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise LLMUnavailable("empty response from model")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - schema makes this rare
            logger.error("unparseable structured output (request_id=%s)", response._request_id)
            raise LLMUnavailable("model returned malformed JSON") from exc


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #
class OllamaBackend:
    """Local inference over Ollama's /api/chat with schema-constrained decoding.

    Uses urllib rather than a client library: one endpoint, one payload shape,
    and no extra dependency to vet for a deployment inside a bank.
    """

    name = "ollama"

    def __init__(self) -> None:
        self._checked: Optional[bool] = None

    @property
    def label(self) -> str:
        return f"{settings.OLLAMA_MODEL} (local)"

    @property
    def available(self) -> bool:
        if self._checked is None:
            self._checked = self._probe()
        return self._checked

    def _probe(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=3
            ) as response:
                tags = json.loads(response.read())
        except Exception as exc:  # noqa: BLE001 - any failure means "not usable"
            logger.warning("Ollama unreachable at %s (%s)", settings.OLLAMA_BASE_URL, exc)
            return False

        installed = {m.get("name", "") for m in tags.get("models", [])}
        if settings.OLLAMA_MODEL not in installed:
            logger.error(
                "Ollama model %r is not installed. Run: ollama pull %s",
                settings.OLLAMA_MODEL, settings.OLLAMA_MODEL,
            )
            return False
        return True

    def structured(
        self,
        *,
        system: str,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload = {
            "model": settings.OLLAMA_MODEL,
            "stream": False,
            "format": schema,          # constrained decoding: output always validates
            "options": {
                "temperature": 0,      # extraction must be reproducible
                "num_ctx": settings.OLLAMA_NUM_CTX,
                "num_predict": max_tokens or 800,
            },
            "messages": [{"role": "system", "content": system}, *messages],
        }
        request = urllib.request.Request(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.OLLAMA_TIMEOUT) as response:
                body = json.loads(response.read())
        except urllib.error.URLError as exc:
            self._checked = None       # re-probe on the next turn
            raise LLMUnavailable(f"Ollama call failed: {exc}") from exc
        except TimeoutError as exc:
            raise LLMUnavailable("Ollama call timed out") from exc

        content = (body.get("message") or {}).get("content")
        if not content:
            raise LLMUnavailable("empty response from Ollama")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMUnavailable("Ollama returned malformed JSON") from exc


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
anthropic_backend = AnthropicBackend()
ollama_backend = OllamaBackend()


def active_backend():
    """Returns the backend to use for this turn, or None for the offline engine."""
    choice = settings.LLM_PROVIDER

    if choice == "off":
        return None
    if choice == "anthropic":
        return anthropic_backend if anthropic_backend.available else None
    if choice == "ollama":
        return ollama_backend if ollama_backend.available else None

    # auto
    if anthropic_backend.available:
        return anthropic_backend
    if ollama_backend.available:
        return ollama_backend
    return None


def active_label() -> str:
    backend = active_backend()
    return backend.label if backend else "moteur deterministe"
