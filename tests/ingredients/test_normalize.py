"""Clés de fusion."""

from __future__ import annotations

import pytest

from custom_components.nextcloud_cookbook_menu.ingredients.normalize import cle, singulier


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Oeufs entiers", "œuf"),
        ("Jaunes d'oeufs", "jaune d'œuf"),
        ("Citron(s)", "citrons"),
        ("Coriandre fraîche", "coriandre"),
        ("Sucre en poudre", "sucre semoule"),
        ("Poudre d'amande", "amandes en poudre"),
        ("Oignon émincés", "oignons"),
        ("Gingembre frais", "gingembre"),
        ("Beurre très mou", "beurre doux"),
        ("Belles fraises mûres", "fraises"),
        ("Crème fraiche épaisse", "crème fraîche"),
        ("Pommes de terre à chair ferme", "pomme de terre"),
        ("Boeuf haché", "boeuf hâchée"),
        ("Salade verte", "laitue"),
        ("Ail hâché", "ail"),
        ("Gros piments", "piment"),
        ("Carottes moyennes râpées", "carotte"),
    ],
)
def test_memes_produits(a, b) -> None:
    assert cle(a) == cle(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Crème fraîche", "crème liquide"),
        ("Boeuf haché", "boeuf"),
        ("Sucre glace", "sucre"),
        ("Poivre", "poivron"),
        ("Huile d'olive", "huile de tournesol"),
        ("Pomme de terre", "pomme"),
        ("Fraises", "frais"),
    ],
)
def test_produits_differents(a, b) -> None:
    assert cle(a) != cle(b)


@pytest.mark.parametrize(
    ("mot", "attendu"),
    [
        ("tomates", "tomate"),
        ("poireaux", "poireau"),
        ("choux", "chou"),
        ("cristaux", "cristal"),
        ("radis", "radis"),
        ("couscous", "couscous"),
        ("pois", "pois"),
        ("roux", "roux"),
        ("riz", "riz"),
        ("ses", "ses"),
        ("mass", "mass"),
    ],
)
def test_singulier(mot, attendu) -> None:
    assert singulier(mot) == attendu


def test_nom_fait_uniquement_de_qualificatifs() -> None:
    assert cle("Frais") == "frais"
    assert cle("Crème fraîche") == "creme fraiche"
    assert cle("") == ""
