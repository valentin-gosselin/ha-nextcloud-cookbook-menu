"""Recherche de recettes par nom, sur les 59 noms réels."""

from __future__ import annotations

import pytest

from custom_components.cookbook_menu.matching import chercher, est_ambigu, lien_automatique, score


@pytest.mark.parametrize(
    ("requete", "attendu"),
    [
        ("salade cesar", "Salade César au poulet"),
        ("Salade César végétarienne", "Salade César végétarienne (façon Rachel)"),
        ("carry", "Carry de poulet"),
        ("chili", "Chili con carne"),
        ("CHILI CON CARNE", "Chili con carne"),
        ("tartiflette", "Tartiflette"),
        ("ratatouile", "Ratatouille"),
        ("boeuf a la coreenne", "Bœuf à la coréenne"),
        ("mafé", "Mafé et riz blanc"),
        ("crepes", "Crèpes"),
        ("dahl lentilles", "Dahl de lentilles corail"),
        ("wraps au thon", "Wraps au thon, salade et avocat"),
    ],
)
def test_meilleure_recette(recettes, requete, attendu) -> None:
    candidats = chercher(requete, list(recettes.values()))
    assert candidats[0].recette.name == attendu


@pytest.mark.parametrize(
    ("requete", "lie"),
    [
        ("salade césar", "Salade César au poulet"),
        ("tartiflette", "Tartiflette"),
        ("gratin", None),  # trois gratins : ambigu
        ("pizza surgelée", None),  # plat libre
        ("", None),
    ],
)
def test_lien_automatique(recettes, requete, lie) -> None:
    recette, _ = lien_automatique(requete, list(recettes.values()))
    assert (recette.name if recette else None) == lie


def test_ambiguite(recettes) -> None:
    gratins = chercher("gratin", list(recettes.values()))
    assert est_ambigu(gratins)
    assert {c.recette.name for c in gratins[:3]} >= {"Gratin Dauphinois", "Gratin de courgettes"}
    assert not est_ambigu(chercher("tartiflette", list(recettes.values())))
    assert not est_ambigu(gratins[:1])


def test_scores_limites() -> None:
    assert score("", "Tartiflette") == 0
    assert score("de la", "Tartiflette") == 0
    assert score("Tartiflette", "tartiflette") == 1
    assert score("xyz", "Tartiflette") == 0
