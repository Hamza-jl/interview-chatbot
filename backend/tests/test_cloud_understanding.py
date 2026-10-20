"""The cloud step: what may leave, what may not, and what happens when it fails.

Two of these tests exist for reasons that have nothing to do with features.
`test_an_interview_answer_is_never_sent_out` guards the promise the whole design
rests on. `test_a_reference_the_model_invented_is_refused` guards against a
hallucinated cell address putting an answer in the wrong row of a signed
document - the one failure in this package that is both silent and serious.
"""
from __future__ import annotations

import pytest

from app.ai import openrouter
from app.ingest import extract, outbound, understand
from app.ingest.slots import DocumentPlan, Slot


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #
def test_identifiers_are_stripped_before_anything_leaves():
    text = ("Responsable : leila.bensalah@mansabank.tn, poste +216 71 123 456. "
            "Portail : https://intranet.mansabank.tn/pca")
    cleaned, counts = outbound.redact(text)

    assert "leila.bensalah@" not in cleaned
    assert "71 123 456" not in cleaned
    assert "intranet" not in cleaned
    assert counts["EMAIL"] == 1 and counts["URL"] == 1


def test_client_names_are_stripped_when_configured(monkeypatch):
    monkeypatch.setattr(outbound.settings, "OPENROUTER_REDACT_TERMS",
                        "MANSA Bank, STAR Assurances", raising=False)
    cleaned, counts = outbound.redact(
        "Fiche PCA de la STAR Assurances, validée par MANSA BANK.")

    assert "STAR" not in cleaned and "MANSA" not in cleaned
    assert counts["CLIENT"] == 2


def test_the_consultant_is_told_what_was_removed():
    """A silent substitution is one nobody checks."""
    sent = outbound.prepare("fiche.docx", "docx",
                            "Contact : a.b@c.tn et d.e@f.tn")
    assert "2 email" in sent.summary()


# --------------------------------------------------------------------------- #
# The invariant
# --------------------------------------------------------------------------- #
def test_an_interview_answer_is_never_sent_out():
    """The promise the feature is sold on, enforced rather than intended."""
    answers = ["Le plan de reprise repose sur le site de secours de Charguia",
               "Mme Leila Ben Salah"]

    with pytest.raises(outbound.OutboundRefused):
        outbound.prepare(
            "fiche.docx", "docx",
            "Contexte : le plan de reprise repose sur le site de secours de "
            "Charguia, confirmé en comité.",
            answers=answers)


def test_a_short_answer_does_not_trip_the_guard():
    """"oui", "42" or a surname occur in ordinary template wording."""
    sent = outbound.prepare("fiche.docx", "docx",
                            "Effectif de la direction : 42 personnes.",
                            answers=["42", "oui", "Salah"])
    assert "42" in sent.text


def test_a_long_document_is_capped():
    sent = outbound.prepare("gros.docx", "docx", "a" * 90_000)
    assert sent.truncated and sent.size_chars == outbound.MAX_OUTBOUND_CHARS


# --------------------------------------------------------------------------- #
# Fallback chain
# --------------------------------------------------------------------------- #
class _Chain:
    """Stands in for the network: each model either raises or answers."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.seen = []

    def __call__(self, model, system, user, schema, max_tokens, key=None):
        self.seen.append(model)
        outcome = self.behaviour.get(model, "ok")
        if outcome == "ok":
            return {"titre": "Fiche", "nature": "questionnaire",
                    "remplissable": True, "champs": [], "remarques": []}
        raise outcome


@pytest.fixture()
def cloud_on(monkeypatch):
    monkeypatch.setattr(openrouter.settings, "OPENROUTER_ENABLED", True, raising=False)
    monkeypatch.setattr(openrouter.settings, "OPENROUTER_API_KEY", "k1,k2", raising=False)
    monkeypatch.setattr(openrouter.settings, "OPENROUTER_MODELS",
                        "model-a,model-b,model-c", raising=False)


def test_the_first_model_that_answers_wins(cloud_on, monkeypatch):
    chain = _Chain({})
    monkeypatch.setattr(openrouter, "_post", chain)

    result = openrouter.structured(system="s", user="u", schema={})

    assert result.model == "model-a"
    assert chain.seen == ["model-a"], "les suivants ne doivent pas être appelés"


def test_an_unavailable_model_falls_through_to_the_next(cloud_on, monkeypatch):
    import urllib.error

    down = urllib.error.HTTPError("u", 429, "rate limited", {}, None)
    chain = _Chain({"model-a": down, "model-b": down})
    monkeypatch.setattr(openrouter, "_post", chain)

    result = openrouter.structured(system="s", user="u", schema={})

    assert result.model == "model-c"
    assert result.attempts == ["model-a", "model-b", "model-c"]


def test_a_bad_key_stops_the_chain_instead_of_trying_every_model(cloud_on, monkeypatch):
    """A 401 fails identically everywhere; walking the list only wastes time."""
    import urllib.error

    chain = _Chain({"model-a": urllib.error.HTTPError("u", 401, "no", {}, None)})
    monkeypatch.setattr(openrouter, "_post", chain)

    with pytest.raises(openrouter.OpenRouterUnavailable, match="clé OpenRouter"):
        openrouter.structured(system="s", user="u", schema={})

    assert chain.seen == ["model-a"]


def test_exhausting_the_chain_says_so(cloud_on, monkeypatch):
    import urllib.error

    down = urllib.error.HTTPError("u", 503, "down", {}, None)
    chain = _Chain({"model-a": down, "model-b": down, "model-c": down})
    monkeypatch.setattr(openrouter, "_post", chain)

    with pytest.raises(openrouter.OpenRouterUnavailable, match="Aucun des 3 modèles"):
        openrouter.structured(system="s", user="u", schema={})


def test_the_cloud_is_off_unless_switched_on(monkeypatch):
    monkeypatch.setattr(openrouter.settings, "OPENROUTER_ENABLED", False, raising=False)
    assert not openrouter.available()
    with pytest.raises(openrouter.OpenRouterUnavailable, match="n'est pas configuré"):
        openrouter.structured(system="s", user="u", schema={})


# --------------------------------------------------------------------------- #
# Turning an answer into a plan
# --------------------------------------------------------------------------- #
def _extraction_with_targets():
    plan = DocumentPlan(
        filename="fiche.docx", kind="docx", title="Fiche",
        slots=[
            Slot(id="docx.t1.r0", kind="cell", label="Nom du responsable",
                 target={"table": 1, "mode": "cell", "row": 0, "col": 1},
                 context=["1. Identité"]),
            Slot(id="docx.t2.grid", kind="grid", label="Applications",
                 target={"table": 2, "mode": "grid", "header_rows": 1},
                 columns=["Application", "Criticité"], context=["2. SI"]),
        ])
    return extract.Extraction(kind="docx", text="…", fillable=True, plan=plan)


def test_a_matched_reference_keeps_the_real_write_address(cloud_on, monkeypatch):
    answer = {"titre": "Fiche PCA", "nature": "questionnaire", "remplissable": True,
              "remarques": [],
              "champs": [{"ref": "docx.t1.r0", "libelle": "Responsable de l'entité",
                          "section": "1. Identité", "type": "cellule", "colonnes": []}]}
    monkeypatch.setattr(openrouter, "_post",
                        lambda *a, **k: answer)

    result = understand.understand(_extraction_with_targets(), "fiche.docx")
    slot = result.plan.slots[0]

    assert result.matched == 1
    assert slot.target == {"table": 1, "mode": "cell", "row": 0, "col": 1}
    # the model's wording is kept, its geometry is not consulted
    assert slot.label == "Responsable de l'entité"


def test_a_reference_the_model_invented_is_refused(cloud_on, monkeypatch):
    """A hallucinated address would write an answer into the wrong cell."""
    answer = {"titre": "Fiche", "nature": "questionnaire", "remplissable": True,
              "remarques": [],
              "champs": [{"ref": "docx.t9.r4", "libelle": "Effectif",
                          "section": "1. Identité", "type": "cellule", "colonnes": []}]}
    monkeypatch.setattr(openrouter, "_post", lambda *a, **k: answer)

    result = understand.understand(_extraction_with_targets(), "fiche.docx")

    assert result.invented == 1
    assert result.plan.slots[0].target == {}, "aucune adresse inventée ne survit"
    assert any("non écrites automatiquement" in n for n in result.plan.notes)


def test_the_columns_of_a_real_table_come_from_the_file(cloud_on, monkeypatch):
    """The model may rename a table; it may not redefine its columns."""
    answer = {"titre": "Fiche", "nature": "questionnaire", "remplissable": True,
              "remarques": [],
              "champs": [{"ref": "docx.t2.grid", "libelle": "Applications métier",
                          "section": "2. SI", "type": "tableau",
                          "colonnes": ["Nom", "Éditeur", "Version"]}]}
    monkeypatch.setattr(openrouter, "_post", lambda *a, **k: answer)

    result = understand.understand(_extraction_with_targets(), "fiche.docx")

    assert result.plan.slots[0].columns == ["Application", "Criticité"]


# --------------------------------------------------------------------------- #
# Key rotation — free models are rate-limited per key, not per model
# --------------------------------------------------------------------------- #
class _Keyed:
    """Fails a given number of times with 429, then answers."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = []

    def __call__(self, model, system, user, schema, max_tokens, key=None):
        self.calls.append((model, key))
        if len(self.calls) <= self.failures:
            import urllib.error
            raise urllib.error.HTTPError("u", 429, "rate limited", {}, None)
        return {"titre": "ok", "nature": "fiche", "remplissable": True,
                "champs": [], "remarques": []}


def test_a_saturated_key_moves_to_the_next_key_not_the_next_model(cloud_on, monkeypatch):
    """A 429 means this key is spent, not that the model is unusable."""
    keyed = _Keyed(failures=1)
    monkeypatch.setattr(openrouter, "_post", keyed)

    result = openrouter.structured(system="s", user="u", schema={})

    assert [c[0] for c in keyed.calls] == ["model-a", "model-a"], "même modèle"
    assert [c[1] for c in keyed.calls] == ["k1", "k2"], "clé suivante"
    assert result.model == "model-a", "le modèle préféré reste en jeu"


def test_every_key_saturated_demotes_the_model(cloud_on, monkeypatch):
    keyed = _Keyed(failures=2)
    monkeypatch.setattr(openrouter, "_post", keyed)

    result = openrouter.structured(system="s", user="u", schema={})

    assert [c[0] for c in keyed.calls] == ["model-a", "model-a", "model-b"]
    assert result.model == "model-b"


def test_an_empty_message_counts_as_a_failure(cloud_on, monkeypatch):
    """A reasoning model that spends its budget thinking returns no content."""
    def empty_then_ok(model, system, user, schema, max_tokens, key=None):
        if model == "model-a":
            raise openrouter.OpenRouterUnavailable(f"{model}: message vide")
        return {"titre": "ok", "nature": "fiche", "remplissable": True,
                "champs": [], "remarques": []}

    monkeypatch.setattr(openrouter, "_post", empty_then_ok)
    assert openrouter.structured(system="s", user="u", schema={}).model == "model-b"


def test_a_single_cell_never_gains_columns(cloud_on, monkeypatch):
    """Observed live: the model answers a cell with its own label as a column,
    which would turn one blank into a one-column table in the interview."""
    answer = {"titre": "Fiche", "nature": "questionnaire", "remplissable": True,
              "remarques": [],
              "champs": [{"ref": "docx.t1.r0", "libelle": "Nom du responsable",
                          "section": "1. Identité", "type": "cellule",
                          "colonnes": ["Nom du responsable"]}]}
    monkeypatch.setattr(openrouter, "_post", lambda *a, **k: answer)

    result = understand.understand(_extraction_with_targets(), "fiche.docx")

    assert result.plan.slots[0].kind == "cell"
    assert result.plan.slots[0].columns == []
