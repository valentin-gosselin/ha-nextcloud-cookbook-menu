"""Unités d'achat et fusions (story 2.9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.nextcloud_cookbook_menu.ingredients.achats import convertir, fusionner_mesures
from custom_components.nextcloud_cookbook_menu.ingredients.pantry import PLACARD_PAR_DEFAUT, cles_placard
from custom_components.nextcloud_cookbook_menu.ingredients.shopping import Contribution, calculer

CORPUS = json.loads((Path(__file__).parents[1] / "fixtures" / "corpus_recettes.json").read_text())


def libelles(*lignes: str) -> dict[str, str]:
    resultat, _ = calculer([Contribution("Test", 1, 1, lignes)])
    return {ligne.cle: ligne.libelle for ligne in resultat}


@pytest.mark.parametrize(
    ("lignes", "cle", "attendu"),
    [
        (("10 g d'ail", "2 gousses d'ail", "1 c. à café d'ail haché"), "ail", "Ail (5 gousses)"),
        (("12 gousses d'ail",), "ail", "Ail (2 têtes)"),
        (
            ("2 brins de persil plat", "1 poignée de persil plat", "1 c. à soupe de persil plat"),
            "persil plat",
            "Persil plat (1 bouquet)",
        ),
        (("400 g d'oignons", "2 oignons"), "oignon", "Oignons (6)"),
        (("2 blancs d'oeuf", "50 g blanc d'oeuf", "3 oeufs", "2 jaunes d'œufs"), "oeuf", "Œufs (9)"),
        (("30 ml de jus de citron", "0,5 citron", "Zeste de 1/2 citron"), "citron", "Citron (2)"),
        (("1 noix de beurre", "1 c. à soupe de beurre", "100 g de beurre"), "beurre", "Beurre (150 g)"),
        (("1 boîte de lait de coco", "20 cl de lait de coco"), "lait coco", "Lait de coco (2 boîtes)"),
        (("3 morceaux de gingembre",), "gingembre", "Gingembre (3 morceaux)"),
        (("1 verre de vin blanc sec", "20 cl de vin blanc sec"), "vin blanc sec", "Vin blanc sec (35 cl)"),
        (("100 g de chocolat", "2 c. à soupe de chocolat"), "chocolat", "Chocolat (150 g)"),
        (("2 cubes de bouillon",), "bouillon", "Bouillon (2 cubes)"),
    ],
)
def test_unites_d_achat(lignes, cle, attendu) -> None:
    assert libelles(*lignes)[cle] == attendu


def test_alias_sans_quantite_et_nom_impose() -> None:
    resultat = libelles("Zeste de citron", "blanc d'oeuf")
    assert resultat["citron"] == "Citron"
    assert resultat["oeuf"] == "Œufs"


def test_convertir_mesure_inconnue_du_profil() -> None:
    assert convertir("citron", "tranche", 2) == ("citron", "tranche", 2, None)
    assert convertir("jaune oeuf", "c. à c.", 1) == ("oeuf", "c. à c.", 1, "Œufs")
    assert convertir("inconnu", "g", 5) == ("inconnu", "g", 5, None)


def test_fusion_generique() -> None:
    assert fusionner_mesures({"g": 100, "c. à c.": 2, "noix": 1}) == {"g": 120}
    assert fusionner_mesures({"ml": 100, "c. à c.": 1}) == {"ml": 105}
    assert fusionner_mesures({"pièce": 2, "c. à c.": 1}) == {"pièce": 2, "c. à c.": 1}


def test_toutes_les_recettes_ensemble() -> None:
    """Simulation demandée par Valentin : les 57 recettes au menu, pour 2."""
    recettes = [r for r in CORPUS if r["category"] != "Produits Ménagers"]
    lignes, ecartes = calculer(
        [Contribution(r["name"], 2, 2 / r["yield"], tuple(r["ingredients"])) for r in recettes],
        cles_placard(PLACARD_PAR_DEFAUT),
    )
    par_cle = {ligne.cle: ligne.libelle for ligne in lignes}
    assert par_cle["ail"] == "Ail (3 têtes)"
    assert par_cle["oeuf"].startswith("Œufs (")
    assert "blanc oeuf" not in par_cle and "jus citron" not in par_cle and "miel liquide" not in par_cle
    assert "eau" not in par_cle and "laurier" not in par_cle
    assert not any("morceaus" in libelle for libelle in par_cle.values())
    melanges = [libelle for libelle in par_cle.values() if " + " in libelle]
    assert len(melanges) <= 3, melanges
    assert "Eau" in ecartes
