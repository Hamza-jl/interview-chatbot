"""Upload a document, answer its questions, get it back filled.

The round trip is the only assertion that matters here. Every intermediate step
can look correct while the answer still lands in the wrong cell, so these tests
open the *produced* file and read the cell the answer was supposed to reach.
"""
from __future__ import annotations

import io

import pytest
from docx import Document
from openpyxl import Workbook, load_workbook

from tests.conftest import API, authenticate, confirm, say


@pytest.fixture()
def headers(client):
    return authenticate(client, "client@example.com")


def _questionnaire(tmp_path):
    """Two blanks and one empty table - the shape these templates really have."""
    document = Document()
    document.add_heading("Fiche d'identité de l'entité", level=1)
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Nom du responsable"
    table.rows[1].cells[0].text = "Effectif"

    document.add_heading("Applications utilisées", level=1)
    grid = document.add_table(rows=3, cols=2)
    grid.rows[0].cells[0].text = "Application"
    grid.rows[0].cells[1].text = "Criticité"

    path = tmp_path / "questionnaire.docx"
    document.save(path)
    return path


def _upload(client, headers, path):
    with open(path, "rb") as handle:
        res = client.post(
            f"{API}/documents", headers=headers,
            files={"file": (path.name, handle.read())},
        )
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def test_an_upload_reports_what_it_found(client, headers, tmp_path):
    body = _upload(client, headers, _questionnaire(tmp_path))

    assert body["kind"] == "docx"
    assert body["slots"] == 3, body["preview"]
    assert body["grids"] == 1
    assert "Nom du responsable" in [p["label"] for p in body["preview"]]


def test_a_format_we_cannot_fill_is_refused_with_a_reason(client, headers, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Rien a lire ici.", encoding="utf-8")

    with open(path, "rb") as handle:
        res = client.post(
            f"{API}/documents", headers=headers, files={"file": ("notes.txt", handle.read())}
        )

    assert res.status_code == 415
    # The refusal has to say what to send instead, or the user just retries.
    assert "Word" in res.json()["detail"] or "Excel" in res.json()["detail"]


def test_a_document_belongs_to_the_account_that_uploaded_it(client, headers, tmp_path):
    body = _upload(client, headers, _questionnaire(tmp_path))
    other = authenticate(client, "staff@example.org")

    res = client.get(f"{API}/documents/{body['id']}", headers=other)
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
# The interview
# --------------------------------------------------------------------------- #
def test_questions_are_written_for_every_blank(client, headers, tmp_path):
    body = _upload(client, headers, _questionnaire(tmp_path))

    res = client.post(f"{API}/documents/{body['id']}/questions", headers=headers)
    assert res.status_code == 200, res.text
    questions = res.json()["questions"]

    assert len(questions) == 3
    assert all(q["question"].strip() for q in questions)
    grid = next(q for q in questions if q["kind"] == "grid")
    assert grid["columns"] == ["Application", "Criticité"]


def test_the_interview_runs_on_the_ordinary_chat_endpoints(client, headers, tmp_path):
    """The whole point of registering under doc:<id>: nothing else changes."""
    body = _upload(client, headers, _questionnaire(tmp_path))
    client.post(f"{API}/documents/{body['id']}/questions", headers=headers)

    res = client.post(f"{API}/documents/{body['id']}/session", headers=headers)
    assert res.status_code == 201, res.text
    detail = res.json()
    session_id = detail["state"]["id"]
    assert detail["state"]["total"] == 3

    turn = say(client, headers, session_id, "Mme Leila Ben Salah")
    assert turn["pending"] is not None
    confirm(client, headers, session_id, turn["pending"])

    state = client.get(f"{API}/sessions/{session_id}", headers=headers).json()["state"]
    assert state["answered"] == 1


def test_a_second_start_resumes_rather_than_duplicating(client, headers, tmp_path):
    body = _upload(client, headers, _questionnaire(tmp_path))
    client.post(f"{API}/documents/{body['id']}/questions", headers=headers)

    first = client.post(f"{API}/documents/{body['id']}/session", headers=headers).json()
    second = client.post(f"{API}/documents/{body['id']}/session", headers=headers).json()

    assert first["state"]["id"] == second["state"]["id"]


# --------------------------------------------------------------------------- #
# The deliverable
# --------------------------------------------------------------------------- #
def _run_interview(client, headers, document_id, answers):
    client.post(f"{API}/documents/{document_id}/questions", headers=headers)
    detail = client.post(f"{API}/documents/{document_id}/session", headers=headers).json()
    session_id = detail["state"]["id"]
    for reply in answers:
        turn = say(client, headers, session_id, reply)
        if turn.get("pending"):
            confirm(client, headers, session_id, turn["pending"])
    return session_id


def _download(client, headers, produced):
    res = client.get(f"{API}/exports/{produced['download_token']}", headers=headers)
    assert res.status_code == 200, res.text
    return res


def test_the_answers_land_in_the_cells_they_were_read_from(client, headers, tmp_path):
    body = _upload(client, headers, _questionnaire(tmp_path))
    _run_interview(client, headers, body["id"], ["Mme Leila Ben Salah", "42 personnes"])

    produced = client.post(f"{API}/documents/{body['id']}/fill", headers=headers)
    assert produced.status_code == 200, produced.text
    produced = produced.json()
    assert produced["filename"] == "rempli_questionnaire.docx"
    assert produced["answers"] == 2

    filled = Document(io.BytesIO(_download(client, headers, produced).content))
    table = filled.tables[0]
    assert table.rows[0].cells[1].text.strip() == "Mme Leila Ben Salah"
    assert "42" in table.rows[1].cells[1].text
    # The label column is never touched: it is the document's own wording.
    assert table.rows[0].cells[0].text.strip() == "Nom du responsable"


def test_an_unanswered_blank_stays_blank(client, headers, tmp_path):
    body = _upload(client, headers, _questionnaire(tmp_path))
    _run_interview(client, headers, body["id"], ["Mme Leila Ben Salah"])

    produced = client.post(f"{API}/documents/{body['id']}/fill", headers=headers).json()
    filled = Document(io.BytesIO(_download(client, headers, produced).content))

    assert produced["blanks"] == 2
    assert filled.tables[0].rows[1].cells[1].text.strip() == ""


def test_filling_before_any_answer_is_refused(client, headers, tmp_path):
    body = _upload(client, headers, _questionnaire(tmp_path))
    client.post(f"{API}/documents/{body['id']}/questions", headers=headers)
    client.post(f"{API}/documents/{body['id']}/session", headers=headers)

    res = client.post(f"{API}/documents/{body['id']}/fill", headers=headers)
    assert res.status_code == 409
    assert "identique" in res.json()["detail"]


def test_an_excel_comes_back_as_excel(client, headers, tmp_path):
    """Serving a workbook as Word makes Excel refuse to open its own file."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Contacts"
    sheet["A1"], sheet["A2"] = "Responsable PCA", "Suppléant"
    path = tmp_path / "contacts.xlsx"
    book.save(path)

    body = _upload(client, headers, path)
    assert body["kind"] == "xlsx"
    _run_interview(client, headers, body["id"], ["Karim Trabelsi"])

    produced = client.post(f"{API}/documents/{body['id']}/fill", headers=headers).json()
    response = _download(client, headers, produced)

    assert "spreadsheetml" in response.headers["content-type"]
    filled = load_workbook(io.BytesIO(response.content))
    assert filled["Contacts"]["B1"].value == "Karim Trabelsi"


def test_deleting_a_document_takes_its_questions_with_it(client, headers, tmp_path):
    from app.ingest import plan as ingest_plan

    body = _upload(client, headers, _questionnaire(tmp_path))
    client.post(f"{API}/documents/{body['id']}/questions", headers=headers)
    assert ingest_plan.is_registered(body["id"])

    assert client.delete(f"{API}/documents/{body['id']}", headers=headers).status_code == 204
    assert not ingest_plan.is_registered(body["id"])
    assert client.get(f"{API}/documents/{body['id']}", headers=headers).status_code == 404


def test_a_discovered_blank_is_a_cell_not_a_free_answer(client, headers, tmp_path):
    """The extraction prompt only says "copy it verbatim" for a field.

    Mapped to "open", the model reformulates: "42 collaborateurs" came back as
    "nettoye pour 42 collaborateurs", and that is what was written into the
    client's own document.
    """
    body = _upload(client, headers, _questionnaire(tmp_path))
    client.post(f"{API}/documents/{body['id']}/questions", headers=headers)
    detail = client.post(f"{API}/documents/{body['id']}/session", headers=headers).json()

    kinds = {q["question_id"]: q["kind"] for q in
             client.get(f"{API}/sessions/{detail['state']['id']}/answers",
                        headers=headers).json()}

    assert "open" not in kinds.values(), kinds
    assert sorted(set(kinds.values())) == ["field", "grid"]
