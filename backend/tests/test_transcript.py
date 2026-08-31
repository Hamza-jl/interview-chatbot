"""The on-disk conversation log: one readable file per entity."""
from __future__ import annotations

import os
import re

import pytest

from app.core.config import settings
from app.pca import transcript
from tests.conftest import API, answer, authenticate, finish


@pytest.fixture()
def logging_to(tmp_path, monkeypatch):
    """Point the writer at a scratch directory and switch it on."""
    monkeypatch.setattr(settings, "TRANSCRIPT_ENABLED", True)
    monkeypatch.setattr(settings, "TRANSCRIPT_DIR", str(tmp_path))
    return tmp_path


def _open_session(client, headers, code: str = "DSI") -> dict:
    structures = client.get(f"{API}/structures", headers=headers).json()
    target = next(s for s in structures if s["code"] == code)
    return client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": target["id"]}
    ).json()


def _only_file(directory) -> str:
    files = list(directory.iterdir())
    assert len(files) == 1, [f.name for f in files]
    return files[0].read_text(encoding="utf-8")


def test_nothing_is_written_unless_it_is_switched_on(client, tmp_path, monkeypatch):
    """It is off by default: these files are plaintext."""
    monkeypatch.setattr(settings, "TRANSCRIPT_ENABLED", False)
    monkeypatch.setattr(settings, "TRANSCRIPT_DIR", str(tmp_path))

    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")

    assert list(tmp_path.iterdir()) == []


def test_the_file_is_named_after_the_structure(client, logging_to):
    headers = authenticate(client, "client@example.com")
    _open_session(client, headers)

    names = [f.name for f in logging_to.iterdir()]
    assert len(names) == 1
    assert names[0].endswith("_DSI.md"), names
    assert " " not in names[0], "must be safe to type and to glob"


def test_the_log_carries_the_conversation_and_the_answers(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")

    body = _only_file(logging_to)
    assert "## Conversation" in body
    assert "## Réponses enregistrées" in body
    assert "Mme Sonia Ben Ammar" in body, "the answer as recorded"
    assert "**Participant**" in body and "**Argus**" in body, "both speakers"
    assert state["structure"]["name"] in body


def test_it_is_rewritten_in_place_rather_than_appended(client, logging_to):
    """Every turn rewrites the same file, so it never drifts from the database."""
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]

    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")
    first = _only_file(logging_to)
    answer(client, headers, state["id"], "Direction des systèmes d'information")
    second = _only_file(logging_to)

    assert second != first
    assert second.count("## Conversation") == 1, "one document, not an append log"
    assert "Mme Sonia Ben Ammar" in second, "earlier turns are still there"


def test_a_correction_replaces_the_superseded_answer(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")

    question_id = state["question"]["id"]
    client.put(
        f"{API}/sessions/{state['id']}/answers", headers=headers,
        json={"question_id": question_id, "value": "M. Karim Trabelsi"},
    )

    body = _only_file(logging_to)
    answers_section = body.split("## Réponses enregistrées", 1)[1]
    assert "M. Karim Trabelsi" in answers_section, "the correction is what is recorded"
    assert "Mme Sonia Ben Ammar" not in answers_section, "the superseded value is gone"
    # It is still in the conversation above - the transcript keeps what was said.
    assert "Mme Sonia Ben Ammar" in body
    assert re.search(r"révision [2-9]", answers_section), "the revision count moved"


def test_blank_points_are_listed_and_the_closure_is_recorded(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")
    finish(client, headers, state["id"])

    body = _only_file(logging_to)
    assert "## Points sans réponse" in body
    assert "clôturé le" in body


def test_a_draft_is_marked_as_absent_from_the_document(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    client.post(
        f"{API}/sessions/{state['id']}/messages", headers=headers,
        json={"message": "M. Karim Trabelsi"},
    )

    body = _only_file(logging_to)
    assert "Brouillon non confirmé" in body


def test_a_write_failure_never_breaks_the_interview(client, monkeypatch, tmp_path):
    """The turn is already committed by the time we run."""
    monkeypatch.setattr(settings, "TRANSCRIPT_ENABLED", True)
    monkeypatch.setattr(settings, "TRANSCRIPT_DIR", str(tmp_path / "logs"))

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(transcript, "render", explode)

    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    turn = answer(client, headers, state["id"], "Mme Sonia Ben Ammar")

    assert turn["state"]["answered"] == 1, "the answer is still recorded"


def test_the_name_survives_accents_and_punctuation():
    class _Structure:
        name = "Direction des Systèmes d'Information & Réseaux"
        code = "SI/1"

    class _Survey:
        structure = _Structure()

    name = transcript.filename_for(_Survey())
    assert name == "Direction_des_Systemes_d_Information_Reseaux_SI_1.md"
    assert os.path.basename(name) == name, "no path separators can leak in"
