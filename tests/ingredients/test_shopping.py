"""Calcul de la liste de courses (code pur)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.cookbook_menu.ingredients.aisles import Rayon, rayon
from custom_components.cookbook_menu.ingredients.shopping import (
    Contribution,
    augmentation,
    calculer,
    formater_quantites,
)

CORPUS = {
    str(r["id"]): r
    for r in json.loads((Path(__file__).parents[1] / "fixtures" / "corpus_recettes.json").read_text())
}


def recette(identifiant: str, couverts: int) -> Contribution:
    r = CORPUS[identifiant]
    return Contribution(r["name"], couverts, couverts / r["yield"], tuple(r["ingredients"]))


def par_cle(lignes):
    return {ligne.cle: ligne for ligne in lignes}


def test_salade_cesar_pour_deux() -> None:
    """Critère de la story 2.2 : recette pour 4 ramenée à 2."""
    lignes, _ = calculer([recette("69603", 2)])
    produits = par_cle(lignes)
    assert produits["escalope poulet"].libelle == "Escalope de poulet (1)"
    assert produits["salade"].libelle == "Salade verte (1)"
    assert produits["citron"].libelle == "Citron (1)"  # 0,5 + 0,5 pour 4, soit 0,5 pour 2, arrondi à 1
    assert "Parmesan" in produits["parmesan"].libelle
    assert produits["parmesan"].sources == {"Salade César au poulet": 2}


def test_fusion_entre_recettes_et_sources() -> None:
    lignes, _ = calculer([recette("2176038", 2), recette("68238", 2)])
    tomates = par_cle(lignes)["tomate"]
    assert tomates.sources == {"Carry de poulet": 2, "Couscous": 2}
    assert tomates.libelle == "Tomates (2)"  # 70 g ramenés à la pièce, plus 1


def test_ordre_par_rayon_sans_tenir_compte_des_accents() -> None:
    lignes, _ = calculer([recette("69603", 2), recette("2176038", 2)])
    rayons = [ligne.rayon for ligne in lignes]
    assert rayons == sorted(rayons)
    fruits = [ligne.nom for ligne in lignes if ligne.rayon is Rayon.FRUITS_LEGUMES]
    assert fruits.index("Échalote") < fruits.index("Gingembre")


def test_placard_ecarte() -> None:
    lignes, ecartes = calculer([recette("68238", 2)], placard={"huile olive", "epice couscous", "harissa"})
    cles = set(par_cle(lignes))
    assert not cles & {"huile olive", "epice couscous", "harissa"}
    assert ecartes == ["Épices à couscous", "Harissa", "Huile d'olive"]


def test_sans_quantite_et_sections() -> None:
    lignes, _ = calculer([Contribution("Test", 2, 1, ("Pour la sauce", "huile d'olive", "", "Meringue :"))])
    [huile] = lignes
    assert huile.sans_quantite
    assert huile.libelle == "Huile d'olive"


@pytest.mark.parametrize(
    ("quantites", "attendu"),
    [
        ({"g": 42}, "50 g"),
        ({"g": 420}, "450 g"),
        ({"g": 1250}, "1,3 kg"),
        ({"g": 2000}, "2 kg"),
        ({"ml": 42}, "50 ml"),
        ({"ml": 250}, "25 cl"),
        ({"ml": 1500}, "1,5 l"),
        ({"c. à c.": 1}, "1 c. à c."),
        ({"c. à c.": 1.2}, "1,5 c. à c."),
        ({"c. à c.": 6}, "2 c. à s."),
        ({"pièce": 0.25}, "1"),
        ({"pièce": 2.0}, "2"),
        ({"gousse": 1.5}, "2 gousses"),
        ({"boîte": 1}, "1 boîte"),
        ({"noix": 3}, "3 noix"),
        ({"g": 100, "pièce": 1}, "100 g + 1"),
        ({}, ""),
    ],
)
def test_formatage(quantites, attendu) -> None:
    assert formater_quantites(quantites) == attendu


def test_augmentation() -> None:
    assert augmentation({"g": 100}, {"g": 150}) == {"g": 50}
    assert augmentation({"g": 150}, {"g": 100}) == {}
    assert augmentation({"g": 100}, {"g": 100, "pièce": 1}) == {"pièce": 1}
    assert augmentation({}, {}) == {}


def test_quantite_max_utilisee_pour_les_plages() -> None:
    lignes, _ = calculer([Contribution("Test", 1, 1, ("7-8 navets",))])
    assert lignes[0].libelle == "Navets (8)"


@pytest.mark.parametrize(
    ("cle", "attendu"),
    [
        ("tomate", Rayon.FRUITS_LEGUMES),
        ("blanc oeuf", Rayon.CREMERIE),
        ("blanc poulet", Rayon.BOUCHERIE_POISSON),
        ("lait coco", Rayon.EPICERIE_SALEE),
        ("lait", Rayon.CREMERIE),
        ("glace vanille", Rayon.SURGELES),
        ("raisin sec", Rayon.EPICERIE_SUCREE),
        ("raisin", Rayon.FRUITS_LEGUMES),
        ("vodka", Rayon.BOISSONS),
        ("pain mie", Rayon.BOULANGERIE),
        ("truc inconnu", Rayon.AUTRE),
        ("", Rayon.AUTRE),
    ],
)
def test_rayons(cle, attendu) -> None:
    assert rayon(cle) is attendu


def test_aucun_produit_du_corpus_sans_rayon() -> None:
    """Tous les produits alimentaires du corpus réel ont un rayon connu."""
    lignes, _ = calculer(
        [recette(i, r["yield"]) for i, r in CORPUS.items() if r["category"] != "Produits Ménagers"]
    )
    assert [ligne.cle for ligne in lignes if ligne.rayon is Rayon.AUTRE] == []
