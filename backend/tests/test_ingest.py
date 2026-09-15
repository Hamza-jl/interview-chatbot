"""Discovering the blanks in an uploaded document.

Structure discovery is deterministic by design, so it is testable by design.
These tests build documents whose correct answer is known, then assert the
reader finds exactly that - because the failure mode being guarded against is
not "no slots found", it is "a slot pointing at the wrong cell", which is
invisible until an answer lands in the wrong place in a signed document.
"""
from __future__ import annotations

import pytest
from docx import Document
from openpyxl import Workbook

from app.ingest import questions, read_docx, read_xlsx, reader
from app.ingest.slots import Slot, is_blank
from tests.conftest import needs_templates


# --------------------------------------------------------------------------- #
# Telling a blank from an answer
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    ["", "   ", "…", "....", "___", "-----", "[à compléter]", "(nom)", "N/A", "néant", "xxx"],
)
def test_furniture_counts_as_blank(text):
    assert is_blank(text)


@pytest.mark.parametrize("text", ["Mme Leila Ben Salah", "12", "Comptabilité", "0"])
def test_a_real_answer_is_not_blank(text):
    assert not is_blank(text)


# --------------------------------------------------------------------------- #
# Word
# --------------------------------------------------------------------------- #
def _docx_with_keyvalue(tmp_path, header: bool):
    document = Document()
    document.add_heading("1. Fiche de suivi", level=1)
    rows = ["Nom du responsable", "Direction"]
    table = document.add_table(rows=len(rows) + (1 if header else 0), cols=2)
    offset = 0
    if header:
        table.rows[0].cells[0].text = "Question"
        table.rows[0].cells[1].text = "Réponse"
        offset = 1
    for i, label in enumerate(rows):
        table.rows[i + offset].cells[0].text = label
    path = tmp_path / f"kv-{'header' if header else 'plain'}.docx"
    document.save(path)
    return path


@pytest.mark.parametrize("header", [False, True])
def test_a_label_beside_an_empty_cell_becomes_a_question(tmp_path, header):
    """'Question | Réponse' is how these templates are really written."""
    plan = read_docx.read(str(_docx_with_keyvalue(tmp_path, header)))

    labels = [s.label for s in plan.cells]
    assert labels == ["Nom du responsable", "Direction"], labels
    assert all(s.target["mode"] == "cell" for s in plan.cells)
    assert all(s.target["col"] == 1 for s in plan.cells), "answers go in column 2"


def test_the_header_row_is_never_asked_about(tmp_path):
    plan = read_docx.read(str(_docx_with_keyvalue(tmp_path, header=True)))
    assert "Question" not in [s.label for s in plan.cells]


def test_a_header_over_empty_rows_becomes_one_table_question(tmp_path):
    document = Document()
    document.add_heading("5. Applications", level=1)
    table = document.add_table(rows=4, cols=3)
    for i, name in enumerate(["Domaine", "Application", "Criticité"]):
        table.rows[0].cells[i].text = name
    path = tmp_path / "grid.docx"
    document.save(path)

    plan = read_docx.read(str(path))
    assert len(plan.grids) == 1 and not plan.cells
    grid = plan.grids[0]
    assert grid.columns == ["Domaine", "Application", "Criticité"]
    assert grid.context[-1] == "5. Applications", "the heading gives the question meaning"


def test_a_filled_table_is_not_mistaken_for_a_form(tmp_path):
    """Data already in the document must not be turned into questions."""
    document = Document()
    table = document.add_table(rows=3, cols=2)
    for row, (a, b) in enumerate([("Domaine", "Responsable"),
                                  ("Crédit", "Mme Ben Salah"),
                                  ("Risques", "M. Trabelsi")]):
        table.rows[row].cells[0].text = a
        table.rows[row].cells[1].text = b
    path = tmp_path / "filled.docx"
    document.save(path)

    plan = read_docx.read(str(path))
    assert not plan.slots
    assert plan.notes, "a document with nothing to fill says so"


def test_an_author_instruction_is_a_hint_not_an_answer(tmp_path):
    """'N.B. : template envoyé séparément' is guidance left in the answer cell."""
    document = Document()
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Question"
    table.rows[0].cells[1].text = "Réponse"
    table.rows[1].cells[0].text = "Liste des documents critiques"
    table.rows[1].cells[1].text = "N.B. : template spécifique envoyé par mail"
    path = tmp_path / "hint.docx"
    document.save(path)

    plan = read_docx.read(str(path))
    assert len(plan.cells) == 1, "the row is still a question"
    assert "template" in (plan.cells[0].existing or ""), "the note is kept as a hint"


@needs_templates
def test_the_real_templates_yield_the_sections_they_contain():
    """The strongest available evidence that discovery works on real documents."""
    plan = read_docx.read("templates/etat_des_lieux_entite.docx")

    labels = [s.label for s in plan.cells]
    assert "Nom du Responsable" in labels
    assert "Entité" in labels

    sections = {s.context[-1] for s in plan.grids if s.context}
    assert any("Activités" in s for s in sections)
    assert plan.grids, "the repeating tables must be found"
    assert all(len(g.columns) >= 2 for g in plan.grids)


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #
def test_a_spreadsheet_form_is_read_even_when_column_b_is_empty(tmp_path):
    """openpyxl reports max_column == 1 for a blank answer column."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Fiche"
    for row, label in enumerate(["Nom du responsable", "Direction"], start=1):
        sheet.cell(row=row, column=1, value=label)
    path = tmp_path / "form.xlsx"
    book.save(path)

    plan = read_xlsx.read(str(path))
    assert [s.label for s in plan.cells] == ["Nom du responsable", "Direction"]
    assert all(s.target["col"] == 2 for s in plan.cells)


def test_a_sheet_with_only_a_header_is_still_a_table(tmp_path):
    """The commonest shape of a blank grid has no rows under the header at all."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Applications"
    for column, name in enumerate(["Domaine", "Application", "Criticité"], start=1):
        sheet.cell(row=1, column=column, value=name)
    path = tmp_path / "grid.xlsx"
    book.save(path)

    plan = read_xlsx.read(str(path))
    assert len(plan.grids) == 1
    assert plan.grids[0].columns == ["Domaine", "Application", "Criticité"]


# --------------------------------------------------------------------------- #
# Choosing a reader
# --------------------------------------------------------------------------- #
def test_the_format_is_detected_from_content_not_the_extension(tmp_path):
    """An .xlsx renamed .docx must not reach the Word reader."""
    book = Workbook()
    book.active["A1"] = "Nom"
    disguised = tmp_path / "piege.docx"
    book.save(disguised)

    assert reader.detect(str(disguised)) == "xlsx"


@pytest.mark.parametrize("name,fragment", [
    ("vieux.doc", "97-2003"),
    ("donnees.csv", "CSV"),
    ("notes.txt", "texte"),
])
def test_an_unsupported_format_is_refused_with_a_reason(tmp_path, name, fragment):
    path = tmp_path / name
    path.write_bytes(b"pas une archive")
    with pytest.raises(reader.UnsupportedDocument) as refused:
        reader.detect(str(path), name)
    assert fragment.lower() in str(refused.value).lower()


# --------------------------------------------------------------------------- #
# Phrasing a question
# --------------------------------------------------------------------------- #
def _grid_slot() -> Slot:
    return Slot(
        id="t1.grid", kind="grid", label="Applications",
        columns=["Domaine", "Application", "Criticité"],
        context=["5. Applications"], target={},
    )


def test_a_table_example_always_matches_the_column_count():
    """The row parser downstream needs this exact, so it is not left to a model.

    Measured on the real templates, qwen2.5:3b returned the right number of
    cells 37% of the time and qwen3:4b 14%. Padding here makes it 100%.
    """
    slot = _grid_slot()
    for cells in ([], ["Crédit"], ["a", "b", "c"], ["a", "b", "c", "d", "e"]):
        row = questions.example_row(slot, cells)
        assert len(row.split(" | ")) == len(slot.columns), cells


def test_a_pipe_inside_a_cell_cannot_forge_a_column():
    row = questions.example_row(_grid_slot(), ["Crédit | Risque", "Delta", "V"])
    assert len(row.split(" | ")) == 3


def test_the_fallback_question_works_with_no_model_at_all():
    """Inference being down must not make an upload unusable."""
    generated = questions.fallback(_grid_slot())
    assert "Applications" in generated.question
    assert generated.engine == "deterministe"
    assert len(generated.example.split(" | ")) == 3


def test_the_prompt_names_the_columns_in_order():
    prompt = questions.prompt_for(_grid_slot())
    assert "Domaine | Application | Criticité" in prompt
    assert "5. Applications" in prompt


def test_the_parser_tolerates_prose_around_the_json():
    parsed = questions.parse(
        'Voici :\n```json\n{"question": "Quel domaine ?", "aide": "a", "cellules": ["x"]}\n```'
    )
    assert parsed and parsed["question"] == "Quel domaine ?"
    assert parsed["valeurs"] == ["x"]


def test_an_answer_with_no_question_is_rejected():
    assert questions.parse('{"aide": "a", "exemple": "b"}') is None
    assert questions.parse("pas du json") is None


# --------------------------------------------------------------------------- #
# Writing the answers back
# --------------------------------------------------------------------------- #
def _round_trip(path, answers):
    """Read a document, fill it, read the result back. The only honest check."""
    from app.ingest import write_back

    plan = reader.read(str(path), path.name)
    filled = write_back.fill(path.read_bytes(), plan, answers)
    out = path.with_name("rempli-" + path.name)
    out.write_bytes(filled)
    return plan, reader.read(str(out), out.name), out


def test_a_word_answer_lands_in_the_cell_it_was_addressed_to(tmp_path):
    path = _docx_with_keyvalue(tmp_path, header=True)
    plan = read_docx.read(str(path))
    target = next(s for s in plan.cells if s.label == "Direction")

    from app.ingest import write_back
    filled = write_back.fill(
        path.read_bytes(), plan, {target.id: {"value": "Risques & Contrôle"}}
    )

    out = tmp_path / "rempli.docx"
    out.write_bytes(filled)
    document = Document(str(out))
    table = document.tables[0]
    row = target.target["row"]
    assert table.rows[row].cells[1].text.strip() == "Risques & Contrôle"
    # The neighbouring field must be untouched.
    other = next(s for s in plan.cells if s.label == "Nom du responsable")
    assert not table.rows[other.target["row"]].cells[1].text.strip()


def test_a_word_table_grows_to_fit_the_answers(tmp_path):
    document = Document()
    document.add_heading("5. Applications", level=1)
    table = document.add_table(rows=2, cols=3)
    for i, name in enumerate(["Domaine", "Application", "Criticité"]):
        table.rows[0].cells[i].text = name
    path = tmp_path / "grid.docx"
    document.save(path)

    plan = read_docx.read(str(path))
    grid = plan.grids[0]
    rows = [
        {"Domaine": "Crédit", "Application": "Delta", "Criticité": "V"},
        {"Domaine": "Risques", "Application": "SAB", "Criticité": "C"},
        {"Domaine": "RH", "Application": "Sage", "Criticité": "MC"},
    ]

    from app.ingest import write_back
    filled = write_back.fill(path.read_bytes(), plan, {grid.id: {"rows": rows}})
    out = tmp_path / "rempli.docx"
    out.write_bytes(filled)

    written = Document(str(out)).tables[0]
    body = [
        [c.text.strip() for c in r.cells]
        for r in written.rows[1:]
        if any(c.text.strip() for c in r.cells)
    ]
    assert body == [["Crédit", "Delta", "V"], ["Risques", "SAB", "C"], ["RH", "Sage", "MC"]]


def test_an_unanswered_slot_stays_blank(tmp_path):
    """A gap in the document must remain a gap, not become an empty string."""
    path = _docx_with_keyvalue(tmp_path, header=True)
    plan = read_docx.read(str(path))

    from app.ingest import write_back
    filled = write_back.fill(path.read_bytes(), plan, {})
    out = tmp_path / "vide.docx"
    out.write_bytes(filled)

    again = read_docx.read(str(out))
    assert len(again.cells) == len(plan.cells), "every blank is still a blank"


def test_an_excel_round_trip_writes_both_shapes(tmp_path):
    book = Workbook()
    fiche = book.active
    fiche.title = "Fiche"
    fiche.cell(row=1, column=1, value="Nom du responsable")
    grid = book.create_sheet("Applications")
    for column, name in enumerate(["Domaine", "Application"], start=1):
        grid.cell(row=1, column=column, value=name)
    path = tmp_path / "form.xlsx"
    book.save(path)

    plan = read_xlsx.read(str(path))
    cell = next(s for s in plan.cells)
    table = next(s for s in plan.grids)

    from app.ingest import write_back
    filled = write_back.fill(
        path.read_bytes(), plan,
        {
            cell.id: {"value": "Mme Ben Salah"},
            table.id: {"rows": [{"Domaine": "Crédit", "Application": "Delta"}]},
        },
    )
    out = tmp_path / "rempli.xlsx"
    out.write_bytes(filled)

    from openpyxl import load_workbook
    written = load_workbook(str(out))
    assert written["Fiche"].cell(row=1, column=2).value == "Mme Ben Salah"
    assert written["Applications"].cell(row=2, column=1).value == "Crédit"
    assert written["Applications"].cell(row=2, column=2).value == "Delta"


def test_the_original_formatting_survives(tmp_path):
    """The deliverable must look like the client's document, not a rebuild."""
    document = Document()
    document.add_heading("Section conservée", level=1)
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Question"
    table.rows[0].cells[1].text = "Réponse"
    table.rows[1].cells[0].text = "Responsable"
    document.add_paragraph("Instruction pré-imprimée à conserver.")
    path = tmp_path / "styled.docx"
    document.save(path)

    plan = read_docx.read(str(path))
    from app.ingest import write_back
    filled = write_back.fill(
        path.read_bytes(), plan, {plan.cells[0].id: {"value": "Mme Ben Salah"}}
    )
    out = tmp_path / "rempli.docx"
    out.write_bytes(filled)

    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "Section conservée" in text
    assert "Instruction pré-imprimée à conserver." in text


def test_a_flat_pdf_is_refused_rather_than_drawn_on(tmp_path):
    """Guessed coordinates in a signed document are worse than a refusal."""
    import fitz

    from app.ingest import write_back

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 100), "Rapport")
    path = tmp_path / "flat.pdf"
    document.save(str(path))
    document.close()

    plan = reader.read(str(path), path.name)
    assert not plan.slots
    assert any("formulaire" in n for n in plan.notes)

    with pytest.raises(write_back.WriteBackError) as refused:
        write_back.fill(path.read_bytes(), plan, {})
    assert "source" in str(refused.value)


# --------------------------------------------------------------------------- #
# An uploaded document becomes an ordinary questionnaire
# --------------------------------------------------------------------------- #
def test_a_discovered_document_registers_as_a_plan(tmp_path):
    """The whole point: get_plan works, so every existing call site works."""
    from app.ingest import plan as ingest_plan
    from app.pca.blueprint import get_plan, sections

    document = Document()
    document.add_heading("1. Fiche", level=1)
    kv = document.add_table(rows=1, cols=2)
    kv.rows[0].cells[0].text = "Nom du responsable"
    document.add_heading("2. Applications", level=1)
    grid = document.add_table(rows=2, cols=2)
    for i, name in enumerate(["Domaine", "Application"]):
        grid.rows[0].cells[i].text = name
    path = tmp_path / "plan.docx"
    document.save(path)

    discovered = read_docx.read(str(path))
    built = ingest_plan.build("test1", discovered, {})
    kind = ingest_plan.template_kind("test1")

    try:
        assert get_plan(kind) == built
        assert len(sections(kind)) == 2, "the rail groups by the document's headings"

        # "field", like a cell of the prepared templates: the extraction prompt
        # only tells the model to copy an answer verbatim for that kind.
        cell = next(q for q in get_plan(kind) if q.kind == "field")
        assert cell.target.mode == "cell"
        table = next(q for q in get_plan(kind) if q.kind == "grid")
        assert table.target.mode == "rows"
        assert [c.id for c in table.columns] == ["Domaine", "Application"]
    finally:
        ingest_plan.forget("test1")


def test_a_generated_question_is_never_mandatory(tmp_path):
    """A blank the author never meant to fill must not block the review gate."""
    from app.ingest import plan as ingest_plan

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Champ facultatif"
    path = tmp_path / "opt.docx"
    document.save(path)

    built = ingest_plan.build("test2", read_docx.read(str(path)), {})
    try:
        assert all(q.optional for q in built)
    finally:
        ingest_plan.forget("test2")


def test_forgetting_a_document_removes_its_plan():
    from app.ingest import plan as ingest_plan

    ingest_plan.register("test3", [])
    assert ingest_plan.is_registered("test3")
    ingest_plan.forget("test3")
    assert not ingest_plan.is_registered("test3")


def test_the_document_title_is_the_title_not_the_first_section(tmp_path):
    """Word's own Title style is spelled "Title" in English, "Titre" in French.

    Missing it means the document gets named after its first section heading,
    which is what the uploader then sees in their list of documents.
    """
    document = Document()
    document.add_heading("Fiche de recensement PCA", level=0)
    document.add_heading("1. Identification", level=1)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Nom de l'entité"
    path = tmp_path / "titled.docx"
    document.save(path)

    plan = read_docx.read(str(path))

    assert plan.title == "Fiche de recensement PCA"
    # ... and the section trail still points at the section, not the title.
    assert plan.cells[0].section == "1. Identification"


# --------------------------------------------------------------------------- #
# Rejecting a bad phrasing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        # The real failure, observed on qwen2.5:3b against a "Processus |
        # Criticite | Delai" table: two questions welded together, about a
        # process that appears nowhere in the document.
        "Quelle est la criticite du processus de gestion des retours d'articles "
        "dans votre entreprise ? Quel est le delai maximal d'interruption ?",
        "Pouvez-vous " + "detailler " * 40 + "?",
    ],
)
def test_a_bad_phrasing_is_rejected(text):
    assert not questions.acceptable(text)


@pytest.mark.parametrize(
    "text",
    [
        "Quel est le nom du responsable de l'entite ?",
        "Pouvez-vous lister les processus metier critiques ?",
        "Combien de collaborateurs l'entite compte-t-elle ?",
    ],
)
def test_a_good_phrasing_is_kept(text):
    assert questions.acceptable(text)


def test_a_rejected_phrasing_falls_back_rather_than_being_asked():
    """Two bad generations must not reach the interviewee."""

    class Stubborn:
        label = "stub"

        def structured(self, **_):
            return {"question": "Une question ? Et une deuxieme ?", "aide": "", "exemple": ""}

    slot = Slot(id="s1", kind="cell", label="Effectif", target={}, context=["1. Identite"])
    generated = questions.generate(slot, Stubborn())

    assert generated.engine == "deterministe"
    assert "Effectif" in generated.question


@pytest.mark.parametrize(
    "text",
    [
        # Asking a person about a file they have never seen.
        "Quelle est la valeur du champ 'Site principal' ?",
        "Quel est le suppleant mentionne dans la cellule de la colonne 'Suppleant' ?",
        "Que faut-il inscrire dans ce tableau ?",
    ],
)
def test_a_question_about_the_document_is_rejected(text):
    assert not questions.acceptable(text)


def test_a_row_sent_as_one_value_is_unpacked_into_its_columns():
    """Observed: the model answers with whole rows instead of cells."""
    slot = Slot(
        id="g1", kind="grid", label="Processus critiques", target={},
        columns=["Processus", "Criticite", "Delai"],
    )

    example = questions.example_row(
        slot,
        ["Facturation / Critique / 24 heures",
         "Paie / Normale / 72 heures",
         "Recouvrement / Critique / 48 heures"],
    )

    assert example == "Facturation | Critique | 24 heures"


def test_one_value_per_column_is_left_alone():
    slot = Slot(id="g2", kind="grid", label="Applications", target={},
                columns=["Application", "Editeur"])

    assert questions.example_row(slot, ["Sage", "Sage SA"]) == "Sage | Sage SA"


def test_a_short_answer_is_padded_to_the_column_count():
    slot = Slot(id="g3", kind="grid", label="Applications", target={},
                columns=["Application", "Editeur"])

    assert questions.example_row(slot, ["Sage"]) == "Sage | <Editeur>"
