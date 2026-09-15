"""The optional rewrite: it improves the document, never the record."""
from __future__ import annotations

from app.ai import polish as answer_polish
from app.pca.blueprint import get_plan


class _Backend:
    def __init__(self, text: str = "Version reformulee de la reponse.") -> None:
        self.text = text
        self.calls = 0

    def structured(self, **_: object) -> dict:
        self.calls += 1
        return {"texte": self.text}


class _Broken:
    def structured(self, **_: object) -> dict:
        raise RuntimeError("the model is down")


LONG = "cette reponse est assez longue pour meriter une reformulation propre"


def _plan():
    plan = get_plan("entite")
    grid = next(q for q in plan if q.kind == "grid")
    prose = next(q for q in plan if q.kind != "grid")
    return plan, grid, prose


def test_prose_is_rewritten(monkeypatch):
    backend = _Backend()
    monkeypatch.setattr(answer_polish.llm, "active_backend", lambda: backend)
    plan, _, prose = _plan()

    out, count = answer_polish.polish_answers({prose.id: {"value": LONG}}, plan)

    assert out[prose.id]["value"] == "Version reformulee de la reponse."
    assert count == 1


def test_tables_are_never_rewritten(monkeypatch):
    """A grid cell is a system name or a criticality letter. A model asked to
    improve one invents a better-sounding system that does not exist."""
    backend = _Backend()
    monkeypatch.setattr(answer_polish.llm, "active_backend", lambda: backend)
    plan, grid, _ = _plan()
    rows = {"rows": [{"a": "Delta Credit", "b": "V"}]}

    out, count = answer_polish.polish_answers({grid.id: rows}, plan)

    assert out[grid.id] == rows
    assert count == 0
    assert backend.calls == 0, "the model was not even asked"


def test_a_one_word_answer_is_left_alone(monkeypatch):
    """Handed "Aucun", a model writes a paragraph around it."""
    backend = _Backend()
    monkeypatch.setattr(answer_polish.llm, "active_backend", lambda: backend)
    plan, _, prose = _plan()

    out, count = answer_polish.polish_answers({prose.id: {"value": "Aucun"}}, plan)

    assert out[prose.id]["value"] == "Aucun"
    assert count == 0
    assert backend.calls == 0


def test_a_model_failure_keeps_the_original(monkeypatch):
    """A document that loses a section because the model stumbled is far worse
    than one whose prose was left as typed."""
    monkeypatch.setattr(answer_polish.llm, "active_backend", lambda: _Broken())
    plan, _, prose = _plan()
    answers = {prose.id: {"value": LONG}}

    out, count = answer_polish.polish_answers(answers, plan)

    assert out == answers
    assert count == 0


def test_without_a_backend_everything_is_returned_untouched(monkeypatch):
    monkeypatch.setattr(answer_polish.llm, "active_backend", lambda: None)
    plan, grid, prose = _plan()
    answers = {prose.id: {"value": LONG}, grid.id: {"rows": []}}

    out, count = answer_polish.polish_answers(answers, plan)

    assert out == answers
    assert count == 0


def test_no_answer_is_ever_dropped(monkeypatch):
    """Whatever happens, the document keeps every section it had."""
    monkeypatch.setattr(answer_polish.llm, "active_backend", lambda: _Broken())
    plan, grid, prose = _plan()
    answers = {prose.id: {"value": LONG}, grid.id: {"rows": [{"a": "b"}]}}

    out, _ = answer_polish.polish_answers(answers, plan)

    assert set(out) == set(answers)
