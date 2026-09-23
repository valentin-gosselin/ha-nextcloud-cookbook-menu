"""Parsing of voice requests (pure code)."""

from __future__ import annotations

import pytest

from custom_components.nextcloud_cookbook_menu.voix import Demande, analyser_demande, detecter_langue, langue


@pytest.mark.parametrize(
    ("texte", "code", "attendu"),
    [
        ("une salade césar jeudi pour quatre", "fr", Demande("salade césar", "jeudi", 4)),
        ("le carry de poulet pour 6 personnes demain", "fr", Demande("carry de poulet", "demain", 6)),
        (
            "une tartiflette pour le dimanche prochain",
            "fr",
            Demande("tartiflette", "dimanche prochain", None),
        ),
        ("des crêpes ce soir", "fr", Demande("crêpes", "ce soir", None)),
        ("du chili", "fr-FR", Demande("chili", None, None)),
        ("de la ratatouille aujourd’hui", "fr", Demande("ratatouille", "aujourd'hui", None)),
        (
            "l'aperol spritz après-demain pour deux couverts",
            "fr",
            Demande("aperol spritz", "après-demain", 2),
        ),
        ("a caesar salad on thursday for four", "en", Demande("caesar salad", "thursday", 4)),
        ("the chili for 3 people tomorrow", "en-US", Demande("chili", "tomorrow", 3)),
        ("pizza next friday", "en", Demande("pizza", "next friday", None)),
        ("  ", "fr", Demande("", None, None)),
    ],
)
def test_analyser_demande(texte, code, attendu) -> None:
    assert analyser_demande(texte, code) == attendu


def test_langue() -> None:
    assert langue("fr-CA") == "fr"
    assert langue("en") == "en"
    assert langue(None) == "en"
    assert langue("de") == "en"


@pytest.mark.parametrize(
    ("texte", "code_langue", "attendu"),
    [
        # The sentence's language takes precedence over the pipeline's (Home Assistant in English).
        ("Ajoute une salade César au menu jeudi pour quatre", "en", "fr"),
        ("Add a caesar salad to the menu on thursday for four", "fr", "en"),
        ("Il n'y a plus d'huile d'olive", "en", "fr"),
        ("we're out of eggs", "fr", "en"),
        ("Qu'est-ce qu'on mange ce soir", "en", "fr"),
        ("what's for dinner", "fr", "en"),
        # Nothing decisive: keep the pipeline's language.
        ("pizza", "fr", "fr"),
        ("pizza", "en", "en"),
        ("", None, "en"),
    ],
)
def test_detecter_langue(texte: str, code_langue: str | None, attendu: str) -> None:
    assert detecter_langue(texte, code_langue) == attendu
