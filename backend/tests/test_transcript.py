"""The on-disk conversation log: one machine-readable file per entity."""
from __future__ import annotations

import json
import os

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


def _only_file(directory) -> dict:
    files = list(directory.iterdir())
    assert len(files) == 1, [f.name for f in files]
    return json.loads(files[0].read_text(encoding="utf-8"))


def _answer_for(document: dict, label_fragment: str) -> dict:
    return next(a for a in document["answers"] if label_fragment in a["label"])


def _values(document: dict) -> str:
    """Every recorded answer value, flattened - for 'is this text anywhere' checks."""
    return json.dumps([a["answer"] for a in document["answers"]], ensure_ascii=False)


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
    assert "_DSI_" in names[0], names           # entity code, then the session id
    assert names[0].endswith(".json"), names
    assert " " not in names[0], "must be safe to type and to glob"


def test_the_file_is_valid_json_a_consumer_can_version_check(client, logging_to):
    """The point of this format: another tool can load it without guessing."""
    headers = authenticate(client, "client@example.com")
    _open_session(client, headers)

    document = _only_file(logging_to)
    assert document["schema"] == transcript.SCHEMA
    assert document["version"] == transcript.SCHEMA_VERSION
    assert document["generated_at"].endswith("+00:00"), "ISO 8601 UTC, not local prose"


def test_the_log_carries_the_conversation_and_the_answers(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")

    document = _only_file(logging_to)
    assert document["entity"]["name"] == state["structure"]["name"]
    assert document["participant"]["email"] == "client@example.com"
    assert "Mme Sonia Ben Ammar" in _values(document), "the answer as recorded"

    speakers = {turn["speaker"] for turn in document["conversation"]}
    assert {"Participant", "Argus"} <= speakers, "both speakers"
    assert [t["seq"] for t in document["conversation"]] == sorted(
        t["seq"] for t in document["conversation"]
    ), "the conversation stays in order"


def test_it_is_rewritten_in_place_rather_than_appended(client, logging_to):
    """Every turn rewrites the same file, so it never drifts from the database."""
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]

    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")
    first = _only_file(logging_to)
    answer(client, headers, state["id"], "Direction des systèmes d'information")
    second = _only_file(logging_to)

    assert second != first
    assert len(second["conversation"]) > len(first["conversation"]), "it grew"
    assert "Mme Sonia Ben Ammar" in _values(second), "earlier turns are still there"


def test_a_correction_replaces_the_superseded_answer(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")

    question_id = state["question"]["id"]
    client.put(
        f"{API}/sessions/{state['id']}/answers", headers=headers,
        json={"question_id": question_id, "value": "M. Karim Trabelsi"},
    )

    document = _only_file(logging_to)
    recorded = next(a for a in document["answers"] if a["question_id"] == question_id)
    assert recorded["answer"]["value"] == "M. Karim Trabelsi", "the correction is recorded"
    assert recorded["revision"] >= 2, "the revision count moved"
    assert "Mme Sonia Ben Ammar" not in _values(document), "the superseded value is gone"
    # It is still in the conversation - the log keeps what was said.
    assert any(
        "Mme Sonia Ben Ammar" in turn["text"] for turn in document["conversation"]
    )


def test_blank_points_are_listed_and_the_closure_is_recorded(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    answer(client, headers, state["id"], "Mme Sonia Ben Ammar")
    finish(client, headers, state["id"])

    document = _only_file(logging_to)
    assert document["unanswered"], "the points nobody filled in are listed"
    assert document["session"]["status"] == "completed"
    assert document["session"]["completed_at"] is not None


def test_a_draft_is_marked_as_unconfirmed(client, logging_to):
    headers = authenticate(client, "client@example.com")
    state = _open_session(client, headers)["state"]
    client.post(
        f"{API}/sessions/{state['id']}/messages", headers=headers,
        json={"message": "M. Karim Trabelsi"},
    )

    document = _only_file(logging_to)
    drafts = [a for a in document["answers"] if a["answered"] and not a["confirmed"]]
    assert drafts, "the draft is kept, and flagged as absent from the document"


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
        id = "1b1554d6aad24e59b3b34782a1cacfbd"

    name = transcript.filename_for(_Survey())
    assert name == "Direction_des_Systemes_d_Information_Reseaux_SI_1_1b1554d6.json"
    assert os.path.basename(name) == name, "no path separators can leak in"


def test_two_interviews_for_one_entity_do_not_overwrite_each_other():
    """A retired account leaves its sessions behind; a finished interview must
    not be clobbered by a later one for the same entity."""
    class _Structure:
        name = "Cash Management"
        code = "CMG"

    class _Survey:
        structure = _Structure()

        def __init__(self, ident):
            self.id = ident

    first = transcript.filename_for(_Survey("be4afbb62cf64f9391f24293fe76867f"))
    second = transcript.filename_for(_Survey("efdc8e7efa7349f8a507ad55235d77f5"))

    assert first != second
    assert first.startswith("Cash_Management_CMG_"), "the entity still leads"
