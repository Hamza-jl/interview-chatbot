"""Engine wiring: backend selection and the prompts built for small models.

These run offline - no Anthropic key, no Ollama process.
"""
from __future__ import annotations

import json

import pytest

from app.ai import staged
from app.ai.llm import active_backend, active_label, sanitize
from app.core.config import settings
from app.pca.blueprint import TEMPLATE_FILES, get_plan
from tests.conftest import unaccented


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #
def test_provider_off_uses_the_deterministic_engine():
    assert settings.LLM_PROVIDER == "off"
    assert active_backend() is None
    assert active_label() == "moteur deterministe"


def test_anthropic_backend_is_unavailable_without_a_key(monkeypatch):
    from app.ai.llm import anthropic_backend

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    assert anthropic_backend.available is False

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test")
    assert anthropic_backend.available is True


def test_ollama_backend_reports_unavailable_when_unreachable(monkeypatch):
    from app.ai.llm import OllamaBackend

    backend = OllamaBackend()
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:9")  # discard port
    assert backend.available is False


def test_control_characters_are_stripped_and_length_capped():
    assert sanitize("bonjour\x00\x07 monde") == "bonjour monde"
    assert len(sanitize("a" * 50_000)) == 8000


# --------------------------------------------------------------------------- #
# Prompts for small local models
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", sorted(TEMPLATE_FILES))
def test_every_grid_example_maps_cleanly_onto_its_columns(kind):
    """The worked JSON example is derived from `Question.example`.

    If an example ever gains or loses a `|` segment it would silently stop being
    emitted, and a small model would go back to shifting values between columns.
    """
    for question in get_plan(kind):
        if question.kind != "grid":
            continue
        segments = [s.strip() for s in question.example.split("|")]
        assert len(segments) == len(question.columns), (
            f"{question.id}: example has {len(segments)} segments for "
            f"{len(question.columns)} columns"
        )

        block = staged._example_row(question)
        assert block, f"{question.id}: no worked example produced"

        payload = json.loads(block.split("-> rows: ")[1])[0]
        assert list(payload) == [c.id for c in question.columns]
        assert payload[question.columns[0].id] == segments[0]


@pytest.mark.parametrize("kind", sorted(TEMPLATE_FILES))
def test_rows_schema_constrains_columns_that_have_fixed_values(kind):
    for question in get_plan(kind):
        if question.kind != "grid":
            continue
        properties = staged.rows_schema(question)["properties"]["rows"]["items"]["properties"]
        for column in question.columns:
            spec = properties[column.id]
            if column.choices:
                # The empty string must stay allowed: "not stated" is a valid answer
                # and is far better than an invented criticality rating.
                assert spec["enum"] == [*column.choices, ""]
            else:
                assert "enum" not in spec


def test_definitions_are_served_verbatim_from_the_referential():
    question = get_plan("dsi")[0]

    known = staged.answer_definition("que veut dire criticite SI ?", question)
    assert "Vitale (V)" in known
    assert question.prompt in known, "the interview question must be re-asked"

    unknown = staged.answer_definition("que signifie le terme zorglub ?", question)
    assert "referentiel" in unaccented(unknown)
    assert "Vitale" not in unknown


def test_classifier_prompt_covers_every_intent_it_can_return():
    enum = staged.CLASSIFY_SCHEMA["properties"]["intent"]["enum"]
    for intent in enum:
        assert intent in staged.CLASSIFY_SYSTEM, f"{intent} is unexplained in the prompt"


def test_audit_records_which_engine_produced_a_turn(client):
    """An auditor must be able to attribute an extraction to a model."""
    import json as _json

    from sqlalchemy import select

    from app.db.models import AuditLog
    from app.db.session import SessionLocal
    from tests.conftest import API, authenticate

    headers = authenticate(client, "client@example.com")
    structures = client.get(f"{API}/structures", headers=headers).json()
    session_id = client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": structures[0]["id"]}
    ).json()["state"]["id"]

    client.post(
        f"{API}/sessions/{session_id}/messages", headers=headers,
        json={"message": "Mme Sonia Ben Ammar"},
    )

    with SessionLocal() as db:
        # The extraction is logged when the draft is produced - that is the
        # moment a model decided something.
        turn = db.execute(
            select(AuditLog).where(AuditLog.action == "survey.draft")
            .order_by(AuditLog.seq.desc()).limit(1)
        ).scalar_one()
        meta = _json.loads(turn.meta)

    assert meta["engine"] == "moteur deterministe"
    assert meta["question_id"] == "dsi.fiche.responsable"
    assert "Ben Ammar" not in turn.meta, "audit metadata must never carry answers"


# --------------------------------------------------------------------------- #
# Guided-grid input bypasses the model entirely
# --------------------------------------------------------------------------- #
def test_pipe_separated_rows_are_mapped_without_a_model():
    question = next(q for q in get_plan("dsi") if q.id == "dsi.activites.grid")

    rows = staged.parse_pipe_rows(
        "Production informatique | Exploitation | Supervision des batchs de nuit\n"
        "Monetique | Gestion des cartes | Emission",
        question,
    )
    assert rows == [
        {
            "domaine": "Production informatique",
            "processus": "Exploitation",
            "macro_activite": "Supervision des batchs de nuit",
        },
        {"domaine": "Monetique", "processus": "Gestion des cartes", "macro_activite": "Emission"},
    ]


def test_short_pipe_rows_pad_the_missing_columns():
    question = next(q for q in get_plan("dsi") if q.id == "dsi.activites.grid")
    rows = staged.parse_pipe_rows("Credit | Octroi", question)
    assert rows == [{"domaine": "Credit", "processus": "Octroi", "macro_activite": ""}]


def test_prose_and_overlong_rows_fall_through_to_the_model():
    question = next(q for q in get_plan("dsi") if q.id == "dsi.activites.grid")

    # No pipes at all - the model has to interpret it.
    assert staged.parse_pipe_rows("En production on fait de l'exploitation.", question) == []

    # More segments than columns is ambiguous; do not guess an alignment.
    assert staged.parse_pipe_rows("a | b | c | d", question) == []


def test_extract_rows_uses_the_direct_path_and_never_calls_the_backend():
    question = next(q for q in get_plan("dsi") if q.id == "dsi.activites.grid")

    class Exploding:
        def structured(self, **_kwargs):  # pragma: no cover - must not be reached
            raise AssertionError("the model must not be called for pipe-separated input")

    rows = staged.extract_rows(
        Exploding(), "Credit | Octroi | Instruction des dossiers", question, []
    )
    assert rows == [
        {"domaine": "Credit", "processus": "Octroi", "macro_activite": "Instruction des dossiers"}
    ]


def test_rows_accumulate_across_turns_without_duplicates():
    question = next(q for q in get_plan("dsi") if q.id == "dsi.activites.grid")
    first = staged.parse_pipe_rows("Credit | Octroi | Instruction", question)

    class Exploding:
        def structured(self, **_kwargs):  # pragma: no cover
            raise AssertionError("unexpected model call")

    # Same row again plus a new one: the duplicate must not be appended twice.
    merged = staged.extract_rows(
        Exploding(),
        "Credit | Octroi | Instruction\nMonetique | Cartes | Emission",
        question,
        first,
    )
    assert len(merged) == 2
    assert merged[0] == first[0]


def test_classifier_is_taught_that_a_bare_name_is_an_answer():
    """Regression guard.

    Introducing the "salutation" category made qwen2.5:3b label bare names as
    greetings - "Mme Sonia Ben Ammar" came back as courtesy and was dropped.
    Names are the most common fiche de suivi answer, so the negative examples
    and the explicit carve-out must stay in the prompt.
    """
    prompt = staged.CLASSIFY_SYSTEM
    assert "jamais une salutation" in prompt
    assert '"Mme Sonia Ben Ammar" -> reponse' in prompt
    assert '"M. Karim Trabelsi, Responsable Production" -> reponse' in prompt


def test_field_extraction_prompt_forbids_inventing_a_title():
    """qwen2.5:3b turned "Karim Trabelsi" into "M. Karim Trabelsi" - a fabricated
    honorific in an audit document."""
    assert "N'ajoute jamais un titre absent" in staged.FIELD_SYSTEM
    assert '"Karim Trabelsi" -> "Karim Trabelsi"' in staged.FIELD_SYSTEM


def test_field_extraction_falls_back_to_the_typed_text():
    """If the model returns nothing usable, the interlocutor's words are kept."""
    question = get_plan("dsi")[0]

    class Empty:
        def structured(self, **_kwargs):
            return {"value": ""}

    class Rambling:
        def structured(self, **_kwargs):
            return {"value": "Le responsable de cette entite bancaire est " + "tres " * 40}

    assert staged.extract_field(Empty(), "Mme Ines Gharbi", question) == "Mme Ines Gharbi"
    assert staged.extract_field(Rambling(), "Mme Ines Gharbi", question) == "Mme Ines Gharbi"
