"""Administration: seeing where every entity stands, and undoing a bad start."""
from __future__ import annotations

import pytest

from app.pca.blueprint import get_plan
from tests.conftest import API, answer, authenticate, finish


def _open_session(client, headers, code: str = "DSI") -> dict:
    structures = client.get(f"{API}/structures", headers=headers).json()
    target = next(s for s in structures if s["code"] == code)
    return client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": target["id"]}
    ).json()


def _row_for(payload: dict, code: str) -> dict:
    return next(r for r in payload["rows"] if r["code"] == code)


# --------------------------------------------------------------------------- #
# Who may look
# --------------------------------------------------------------------------- #
def test_an_interviewee_cannot_see_the_progress_of_others(client):
    headers = authenticate(client, "client@example.com")
    assert client.get(f"{API}/admin/progress", headers=headers).status_code == 403


def test_an_interviewee_cannot_reset_an_interview(client):
    interviewee = authenticate(client, "client@example.com")
    state = _open_session(client, interviewee)["state"]
    answer(client, interviewee, state["id"], "Mme Sonia Ben Ammar")

    refused = client.post(f"{API}/admin/sessions/{state['id']}/reset", headers=interviewee)
    assert refused.status_code == 403

    # and nothing was destroyed
    detail = client.get(f"{API}/sessions/{state['id']}", headers=interviewee).json()
    assert detail["state"]["answered"] == 1


# --------------------------------------------------------------------------- #
# Progress
# --------------------------------------------------------------------------- #
def test_progress_lists_every_structure_even_untouched_ones(client):
    """An entity nobody has opened is the one an administrator most needs."""
    staff = authenticate(client, "staff@example.org")
    payload = client.get(f"{API}/admin/progress", headers=staff).json()

    assert payload["structures"] == len(payload["rows"]) > 0
    assert payload["not_started"] >= 1
    untouched = [r for r in payload["rows"] if r["status"] == "non_demarre"]
    assert untouched, "structures with no interview must still appear"
    assert untouched[0]["session_id"] is None
    assert untouched[0]["percent"] == 0


def test_progress_follows_a_real_interview(client):
    interviewee = authenticate(client, "client@example.com")
    staff = authenticate(client, "staff@example.org")

    state = _open_session(client, interviewee)["state"]
    answer(client, interviewee, state["id"], "Mme Sonia Ben Ammar")

    row = _row_for(client.get(f"{API}/admin/progress", headers=staff).json(), "DSI")
    assert row["status"] == "in_progress"
    assert row["answered"] == 1
    assert row["total"] == len(get_plan("dsi"))
    assert row["percent"] > 0
    assert row["participant"]["email"] == "client@example.com"
    assert row["missing"], "the outstanding points are named"


def test_progress_reports_a_closed_interview(client):
    interviewee = authenticate(client, "client@example.com")
    staff = authenticate(client, "staff@example.org")

    state = _open_session(client, interviewee)["state"]
    answer(client, interviewee, state["id"], "Mme Sonia Ben Ammar")
    finish(client, interviewee, state["id"])

    row = _row_for(client.get(f"{API}/admin/progress", headers=staff).json(), "DSI")
    assert row["status"] == "completed"
    assert row["completed_at"]


def test_progress_never_exposes_what_was_answered(client):
    """Counts and labels only - the content stays encrypted."""
    interviewee = authenticate(client, "client@example.com")
    staff = authenticate(client, "staff@example.org")

    state = _open_session(client, interviewee)["state"]
    answer(client, interviewee, state["id"], "Mme Sonia Ben Ammar")

    body = client.get(f"{API}/admin/progress", headers=staff).text
    assert "Ben Ammar" not in body


# --------------------------------------------------------------------------- #
# Reset
# --------------------------------------------------------------------------- #
def test_reset_returns_an_interview_to_its_first_question(client):
    interviewee = authenticate(client, "client@example.com")
    staff = authenticate(client, "staff@example.org")

    state = _open_session(client, interviewee)["state"]
    answer(client, interviewee, state["id"], "Mme Sonia Ben Ammar")
    answer(client, interviewee, state["id"], "Direction des systèmes d'information")

    report = client.post(f"{API}/admin/sessions/{state['id']}/reset", headers=staff)
    assert report.status_code == 200, report.text
    assert report.json()["answers_deleted"] >= 2

    detail = client.get(f"{API}/sessions/{state['id']}", headers=interviewee).json()
    assert detail["state"]["answered"] == 0
    assert detail["state"]["cursor"] == 0
    assert detail["state"]["status"] == "in_progress"
    # It reopens on its greeting, exactly like a new interview.
    assert len(detail["messages"]) == 1
    assert "Bonjour" in detail["messages"][0]["body"]

    body = client.get(f"{API}/sessions/{state['id']}/answers", headers=interviewee).json()
    assert all(row["completeness"] == "vide" for row in body)


def test_reset_reopens_a_closed_interview_so_the_entity_can_be_redone(client):
    """The one-interview-per-entity rule reads the same status, so this undoes it."""
    interviewee = authenticate(client, "client@example.com")
    staff = authenticate(client, "staff@example.org")

    state = _open_session(client, interviewee)["state"]
    answer(client, interviewee, state["id"], "Mme Sonia Ben Ammar")
    finish(client, interviewee, state["id"])

    structures = client.get(f"{API}/structures", headers=interviewee).json()
    target = next(s for s in structures if s["code"] == "DSI")
    blocked = client.post(f"{API}/sessions", headers=interviewee, json={"structure_id": target["id"]})
    assert blocked.status_code == 409, "closed interviews cannot be restarted"

    client.post(f"{API}/admin/sessions/{state['id']}/reset", headers=staff)

    reopened = client.post(f"{API}/sessions", headers=interviewee, json={"structure_id": target["id"]})
    assert reopened.status_code in (200, 201)
    assert reopened.json()["state"]["answered"] == 0


def test_reset_is_written_to_the_audit_log(client):
    interviewee = authenticate(client, "client@example.com")
    staff = authenticate(client, "staff@example.org")

    state = _open_session(client, interviewee)["state"]
    answer(client, interviewee, state["id"], "Mme Sonia Ben Ammar")
    client.post(f"{API}/admin/sessions/{state['id']}/reset", headers=staff)

    entries = client.get(f"{API}/admin/audit?limit=20", headers=staff).json()
    reset = next((e for e in entries if e["action"] == "admin.session_reset"), None)
    assert reset is not None, "a destructive act must be traceable"
    assert reset["target"] == state["id"]
    assert reset["meta"]["answers_deleted"] >= 1

    # The reset entry must not break the hash chain it is written into.
    assert client.get(f"{API}/admin/audit/verify", headers=staff).json()["valid"] is True


def test_resetting_an_unknown_session_is_a_404(client):
    staff = authenticate(client, "staff@example.org")
    assert client.post(f"{API}/admin/sessions/nope/reset", headers=staff).status_code == 404
