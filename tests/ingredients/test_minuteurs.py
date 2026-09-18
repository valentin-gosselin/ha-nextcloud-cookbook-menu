"""Durées des étapes (minuteurs de la fiche recette)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.nextcloud_cookbook_menu.ingredients.minuteurs import trouver_minuteurs


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("compter 25 mn de cuisson", [("25 mn", 1500)]),
        ("cuire 40 à 45 minutes", [("40 à 45 minutes", 2400)]),
        ("1-2 minutes de chaque côté", [("1-2 minutes", 60)]),
        ("2 ou 3 min", [("2 ou 3 min", 120)]),
        ("laisser reposer 1/2 heure", [("1/2 heure", 1800)]),
        ("mijoter 1 h 30 puis 30 secondes", [("1 h 30", 5400), ("30 secondes", 30)]),
        ("1h", [("1h", 3600)]),
        ("une heure au frais", [("une heure", 3600)]),
        ("12 heures au réfrigérateur", [("12 heures", 43200)]),
        ("thermostat 6, 200 g de farine, 4 personnes", []),
        ("chacun 2 s", []),
        ("cuire ½ heure", [("½ heure", 1800)]),
        ("0 minute de pause", []),
        ("", []),
    ],
)
def test_durees(texte, attendu) -> None:
    assert [(m.texte, m.secondes) for m in trouver_minuteurs(texte)] == attendu


def test_positions_pour_decouper_le_texte() -> None:
    texte = "Remettez au feu : comptez 10 mn de cuisson"
    [minuteur] = trouver_minuteurs(texte)
    assert texte[minuteur.debut : minuteur.fin] == "10 mn"


def test_etapes_reelles() -> None:
    recettes = json.loads((Path(__file__).parents[1] / "fixtures" / "instructions_recettes.json").read_text())
    minuteurs = [m for r in recettes for e in (r["recipeInstructions"] or []) for m in trouver_minuteurs(e)]
    assert len(minuteurs) >= 100
    assert all(0 < m.secondes <= 12 * 3600 for m in minuteurs)
