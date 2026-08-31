"""Courtesy must never be recorded as interview content."""
from __future__ import annotations

import pytest

from app.ai import social
from app.ai.engine import run_turn
from app.pca.blueprint import get_plan
from tests.conftest import API, answer, authenticate

FIELD = get_plan("dsi")[0]          # "Nom du Responsable"
GRID = next(q for q in get_plan("dsi") if q.kind == "grid")


@pytest.mark.parametrize(
    "message",
    [
        "bonjour", "Bonjour", "Bonjour !", "bonjour à vous", "BONSOIR",
        "salut", "coucou", "hello", "bjr", "Bonne journée",
        "merci", "Merci beaucoup", "je vous remercie",
        "ok", "d'accord", "très bien", "parfait", "entendu", "c'est parti",
        "au revoir", "ça va ?", "comment allez-vous ?",
    ],
)
def test_courtesy_is_recognised(message):
    category, substance = social.split(message)
    assert category is not None, f"{message!r} should be treated as courtesy"
    assert substance == ""


@pytest.mark.parametrize(
    "message",
    [
        "Mme Sonia Ben Ammar",
        "42 collaborateurs repartis en 4 poles",
        "Comite SI mensuel preside par le DGA",
        "Merci Bank est notre partenaire principal",   # "merci" inside a real answer
        "OK Corral SA, notre prestataire",
    ],
)
def test_real_answers_are_not_mistaken_for_courtesy(message):
    category, substance = social.split(message)
    assert category is None, f"{message!r} is interview content"
    assert substance == message


def test_a_greeting_prefix_is_stripped_and_the_substance_kept():
    category, substance = social.split("Bonjour, le responsable est Mme Ben Ammar")
    assert category is None
    assert substance == "le responsable est Mme Ben Ammar"

    category, substance = social.split("Salut ! Delta Credit | Octroi | V")
    assert category is None
    assert substance == "Delta Credit | Octroi | V"


def test_greeting_records_nothing_and_does_not_advance():
    result = run_turn(
        FIELD, "bonjour", [],
        structure_name="DSI", template_label="dsi", position="1/26",
        existing=None, followups=0,
    )
    assert result.intent == "salutation"
    assert result.has_data is False
    assert result.data == {"value": ""}
    assert result.advance is False, "a greeting must not consume a question"
    assert FIELD.prompt in result.reply, "the question is re-asked"


def test_greeting_on_a_grid_question_leaves_the_table_untouched():
    result = run_turn(
        GRID, "merci", [],
        structure_name="DSI", template_label="dsi", position="5/26",
        existing={"rows": [{"domaine": "Credit"}]}, followups=0,
    )
    assert result.has_data is False
    assert result.data == {"rows": []}
    assert result.advance is False


def test_first_greeting_is_warmer_than_a_later_one():
    first = run_turn(
        FIELD, "bonjour", [],
        structure_name="DSI", template_label="dsi", position="1/26",
        existing=None, followups=0,
    ).reply
    later = run_turn(
        FIELD, "bonjour", [{"role": "user", "body": "Mme Ben Ammar"}],
        structure_name="DSI", template_label="dsi", position="1/26",
        existing=None, followups=0,
    ).reply
    assert "bienvenue" in first.lower()
    assert first != later


def test_greeting_over_the_api_does_not_move_the_interview(client):
    """The reported defect: "bonjour" was stored as the name of the responsable."""
    headers = authenticate(client, "client@example.com")
    structures = client.get(f"{API}/structures", headers=headers).json()
    session_id = client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": structures[0]["id"]}
    ).json()["state"]["id"]

    turn = client.post(
        f"{API}/sessions/{session_id}/messages", headers=headers, json={"message": "bonjour"}
    ).json()

    assert turn["recorded"] is False
    assert turn["intent"] == "salutation"
    assert turn["state"]["answered"] == 0
    assert turn["state"]["cursor"] == 0
    assert turn["state"]["question"]["id"] == "dsi.fiche.responsable"

    answers = client.get(f"{API}/sessions/{session_id}/answers", headers=headers).json()
    responsable = next(a for a in answers if a["question_id"] == "dsi.fiche.responsable")
    assert responsable["value"] in (None, "")
    assert responsable["completeness"] == "vide"


def test_greeting_then_a_real_answer_still_works(client):
    headers = authenticate(client, "client@example.com")
    structures = client.get(f"{API}/structures", headers=headers).json()
    session_id = client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": structures[0]["id"]}
    ).json()["state"]["id"]

    client.post(f"{API}/sessions/{session_id}/messages", headers=headers,
                json={"message": "bonjour"})
    turn = answer(client, headers, session_id, "Bonjour, c'est Mme Sonia Ben Ammar")

    assert turn["recorded"] is True
    assert turn["state"]["answered"] == 1

    answers = client.get(f"{API}/sessions/{session_id}/answers", headers=headers).json()
    value = next(a for a in answers if a["question_id"] == "dsi.fiche.responsable")["value"]
    assert "Ben Ammar" in value
    assert not value.lower().startswith("bonjour"), "the opener must not reach the document"


# --------------------------------------------------------------------------- #
# Regressions from a real interview transcript (2026-08-26)
# --------------------------------------------------------------------------- #
def test_a_stray_character_is_not_an_answer():
    """A lone "x" was consigned as the name of the responsable, which then
    shifted every subsequent answer by one question."""
    result = run_turn(
        FIELD, "x", [{"role": "user", "body": "y"}],
        structure_name="DCR", template_label="entite", position="1/19",
        existing=None, followups=0,
    )
    assert result.has_data is False
    assert result.advance is False


def test_a_negative_answer_is_recorded_not_skipped():
    """"Nous n'avons pas de comites" is an answer. It used to be read as a
    request to skip, and the answer was lost."""
    assert social.classify_navigation("Nous n'avons pas de comites") is None
    assert social.classify_navigation("Aucun comite formel") is None
    # ... while a genuine skip still is one
    assert social.classify_navigation("je ne dispose pas de cette information") == "suivant"
    assert social.classify_navigation("passer") == "suivant"


def test_a_request_for_an_example_is_not_a_glossary_lookup():
    """Asking for an example returned "Periodes critiques" - whichever entry
    happened to share a word."""
    from app.ai import staged
    from app.pca.blueprint import get_plan

    grid = next(q for q in get_plan("entite") if q.kind == "grid")
    reply = staged.answer_definition("Pouvez-vous me donner un exemple ?", grid)
    assert grid.example in reply
    assert "Periodes critiques" not in reply


def test_the_referential_stays_silent_rather_than_answering_adjacently():
    """A message sharing one word with an entry used to trigger a definition."""
    from app.pca import glossary

    assert glossary.search("Des donnees personneles qui sont tres sensibles") == []
    assert glossary.search("5 employes repartis en 4 poles") == []
    # while the term the template itself uses resolves
    assert glossary.search("explique (V, C, MC, PC)")
    assert glossary.search("que signifie la criticite SI")


def test_a_definition_request_is_recognised_however_it_is_typed():
    """Reported from a live test: "que veux tu dire par (V, C, MC, PC)." was
    treated as an attempted table row, so the user got "je n'ai pas reussi a en
    tirer une ligne de tableau" instead of the definition.

    The old pattern only matched typographically perfect spellings, while people
    type without apostrophes and hyphens.
    """
    from app.ai.engine import _asks_something

    for phrasing in [
        "que veux tu dire par (V, C, MC, PC).",
        "que veux-tu dire par V, C, MC, PC",
        "c est quoi la criticite SI",
        "c'est quoi la criticité SI",
        "qu est ce que le PDMA",
        "qu'est-ce que le PDMA",
        "ca veut dire quoi V",
        "que signifie MC",
        "definition de DMIA",
        "a quoi ca sert",
    ]:
        assert _asks_something(phrasing), f"{phrasing!r} should read as a question"

    for answer_text in [
        "Credit | Octroi | Delta Credit | Instruction et deblocage | V",
        "Mme Leila Ben Salah",
        "Nous avons 14 collaborateurs repartis en 3 services",
        "Comite hebdomadaire preside par le DGA",
    ]:
        assert not _asks_something(answer_text), f"{answer_text!r} is an answer"


def test_a_definition_request_on_a_grid_question_records_nothing():
    """The failing case end to end: on a table question the request must serve a
    definition, not fail to parse a row."""
    grid = next(q for q in get_plan("entite") if q.id == "ent.applications.grid")
    result = run_turn(
        grid, "que veux tu dire par (V, C, MC, PC).", [{"role": "user", "body": "y"}],
        structure_name="DFC", template_label="entite", position="5/19",
        existing=None, followups=0,
    )
    assert result.intent == "question"
    assert result.has_data is False
    assert "Vitale" in result.reply
    assert "pas reussi" not in result.reply


def test_a_question_the_classifier_calls_an_answer_is_still_answered():
    """The mirror of the guard above.

    A small classifier that labels a definition request "reponse" sends it to
    the extractor, which mines a document value out of it - reported live as
    "C'est note : 2 ligne(s) enregistree(s)" for "que veux tu dire par
    (V, C, MC, PC)". The flip only happens when the message opens like a
    question AND the referential can answer it, so answers are never diverted.
    """
    from app.ai import social as _social
    from app.ai.engine import _opens_like_a_question
    from app.pca import glossary

    def would_flip(text: str) -> bool:
        return _opens_like_a_question(text) and bool(
            _social.wants_example(text) or glossary.search(text, limit=1)
        )

    for question_text in [
        "que veux tu dire par (V, C, MC, PC)",
        "c est quoi la criticite SI",
        "qu est ce que le PDMA",
        "donne moi un exemple",
    ]:
        assert would_flip(question_text), f"{question_text!r} should be answered"

    for answer_text in [
        "c'est Mme Sonia Ben Ammar qui dirige l'entite",
        "Quelques applications : Delta Credit et la GED",
        "Le processus metier principal est l'octroi de credit",
        "Credit | Octroi | Delta Credit | Instruction | V",
        "Nous n'avons pas de comites",
    ]:
        assert not would_flip(answer_text), f"{answer_text!r} must stay an answer"


def test_a_definition_request_never_produces_table_rows():
    """End to end on the question where it actually happened."""
    apps = next(q for q in get_plan("entite") if q.id == "ent.applications.grid")
    for phrasing in [
        "que veux tu dire par (V, C, MC, PC)",
        "que veux tu dire par (V, C, MC, PC).",
        "que veux-tu dire par V, C, MC, PC ?",
    ]:
        result = run_turn(
            apps, phrasing, [{"role": "user", "body": "y"}],
            structure_name="DFC", template_label="entite", position="5/19",
            existing=None, followups=0,
        )
        assert result.intent == "question", phrasing
        assert result.has_data is False, phrasing
        assert result.data == {"rows": []}, phrasing


# --------------------------------------------------------------------------- #
# Questions about the interview itself
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "message,topic",
    [
        ("qui est tu ?", "identite"),          # the spoken form, as it actually arrived
        ("qui es-tu ?", "identite"),
        ("qui êtes-vous ?", "identite"),
        ("tu es qui", "identite"),
        ("es-tu un robot ?", "identite"),
        ("es tu une IA ?", "identite"),
        ("présente-toi", "identite"),
        ("pourquoi nous faisons cet entretien ?", "objectif"),
        ("pourquoi cet entretien ?", "objectif"),
        ("pourquoi on fait ce questionnaire", "objectif"),
        ("à quoi ça sert ?", "objectif"),
        ("quel est l'objectif de cet atelier ?", "objectif"),
        ("dans quel but ?", "objectif"),
        ("combien de temps ça va prendre ?", "duree"),
        ("combien de questions ?", "duree"),
        ("c'est long ?", "duree"),
        ("que faites-vous de mes réponses ?", "donnees"),
        ("où vont mes données ?", "donnees"),
        ("qui va lire mes réponses ?", "donnees"),
        ("c'est confidentiel ?", "donnees"),
        ("est-ce que je peux m'arrêter ?", "reprise"),
        ("puis-je reprendre plus tard ?", "reprise"),
        ("comment ça marche ?", "fonctionnement"),
        ("aide", "fonctionnement"),
    ],
)
def test_a_question_about_the_interview_is_recognised(message, topic):
    from app.ai import faq

    assert faq.match(message) == topic


@pytest.mark.parametrize(
    "message",
    [
        # Real interview content that must never be mistaken for a meta question.
        "Mme Leila Ben Salah",
        "Le responsable est M. Fabrice HAUHOUOT",
        "qui est le responsable de la structure ?",
        "qui sont nos partenaires principaux ?",
        "Nous n'avons pas de comités formalisés",
        "Que signifie PDMA ?",
        "que veux tu dire par (V, C, MC, PC) ?",
        "Analyse des risques et audit des SI, pour l'ensemble des entités de la banque",
        "bonjour",
    ],
)
def test_interview_content_is_not_mistaken_for_a_meta_question(message):
    from app.ai import faq

    assert faq.match(message) is None, f"{message!r} is interview content"


@pytest.mark.parametrize(
    "message",
    ["qui est tu ?", "pourquoi nous faisons cet entretien ?", "que faites-vous de mes réponses ?"],
)
def test_a_meta_question_is_answered_and_records_nothing(message):
    """It used to reply 'ce terme ne figure pas dans le référentiel' to all three."""
    plan = get_plan("entite")
    result = run_turn(
        plan[0], message, [], structure_name="Audit Technologique",
        template_label="entite", position="question 1 sur 18",
        existing=None, followups=0, total=len(plan),
    )
    assert result.intent == "question"
    assert result.has_data is False, "a question about the workshop is not an answer"
    assert result.advance is False, "and it must not consume a question"
    assert "référentiel" not in result.reply, "it is answered, not deflected"
    assert plan[0].prompt in result.reply, "the interview question is re-asked"


def test_the_length_answer_quotes_the_plan_actually_loaded():
    for kind in ("entite", "dsi"):
        plan = get_plan(kind)
        result = run_turn(
            plan[0], "combien de questions ?", [], structure_name="X",
            template_label=kind, position="1", existing=None, followups=0,
            total=len(plan),
        )
        assert f"{len(plan)} points" in result.reply, kind


# --------------------------------------------------------------------------- #
# Conversation must never consume a question
# --------------------------------------------------------------------------- #
def test_talking_to_the_assistant_never_advances_the_interview():
    """The reported bug: four conversational turns skipped question 1.

    Courtesy and questions were charged against the follow-up allowance, which
    exists for answers the engine could not use. Two of them were enough to
    force the cursor forward onto a question nobody had answered.
    """
    from app.api.chat import _move_cursor

    class _Survey:
        cursor = 0
        followups = 0

    plan = get_plan("entite")
    survey = _Survey()

    for message in [
        "bonjour",
        "qui est tu ?",
        "pourquoi nous faisons cet entretien ?",
        "qui est tu ?",
        "c'est quoi Devoteam ?",
        "combien de temps ça va prendre ?",
        "quel temps fait-il à Tunis ?",
        "merci",
    ]:
        result = run_turn(
            plan[survey.cursor], message, [{"role": "user", "body": "x"}],
            structure_name="Audit Technologique", template_label="entite",
            position="question 1 sur 18", existing=None,
            followups=survey.followups, total=len(plan),
        )
        _move_cursor(survey, result, survey.cursor, len(plan))
        assert result.has_data is False, message

    assert survey.cursor == 0, "the interview must still be on the unanswered question"
    assert survey.followups == 0, "conversation does not burn the follow-up allowance"


def test_the_follow_up_allowance_still_protects_against_looping():
    """It must still advance when the engine cannot use a real answer attempt."""
    from app.ai.engine import MAX_FOLLOWUPS, TurnResult
    from app.api.chat import _move_cursor

    class _Survey:
        cursor = 0
        followups = 0

    survey = _Survey()
    unusable = TurnResult(
        intent="reponse", reply="", has_data=False, data={"value": ""},
        completeness="vide", advance=False, nav="aucun",
    )
    for _ in range(MAX_FOLLOWUPS + 1):
        _move_cursor(survey, unusable, survey.cursor, 18)

    assert survey.cursor == 1, "an unusable answer still moves on eventually"


@pytest.mark.parametrize(
    "message", ["quel temps fait-il à Tunis ?", "tu peux m'écrire un poème ?"]
)
def test_an_off_topic_request_is_declined_with_its_scope(message):
    plan = get_plan("entite")
    result = run_turn(
        plan[0], message, [{"role": "user", "body": "x"}], structure_name="X",
        template_label="entite", position="1", existing=None, followups=0,
        total=len(plan),
    )
    assert result.has_data is False
    assert "sort de mon champ" in result.reply, "it says plainly that it cannot"
    assert "état des lieux" in result.reply, "and what it is for instead"


def test_a_genuine_definition_miss_is_not_treated_as_off_topic():
    """'Que signifie X' deserves the honest referential answer, not a brush-off."""
    plan = get_plan("entite")
    result = run_turn(
        plan[0], "Que signifie le terme zorglub ?", [{"role": "user", "body": "x"}],
        structure_name="X", template_label="entite", position="1",
        existing=None, followups=0, total=len(plan),
    )
    assert "référentiel" in result.reply
    assert "sort de mon champ" not in result.reply


def test_the_assistant_knows_who_runs_the_workshop():
    """Built from deployment config - the names differ per install."""
    from app.ai import faq
    from app.core.config import settings

    org, client = settings.CONSULTING_ORG, settings.CLIENT_NAME
    for phrasing in [f"c'est quoi {org} ?", f"qui est {org}", f"c'est quoi {client} ?"]:
        assert faq.match(phrasing) == "organisateur", phrasing

    plan = get_plan("entite")
    reply = run_turn(
        plan[0], f"c'est quoi {org} ?", [], structure_name="X",
        template_label="entite", position="1", existing=None, followups=0,
        total=len(plan),
    ).reply
    assert org in reply and client in reply
