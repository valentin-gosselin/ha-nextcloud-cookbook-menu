"""Analyse des demandes vocales (code pur)."""

from __future__ import annotations

import pytest

from custom_components.cookbook_menu.voix import Demande, analyser_demande, langue


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
