"""Index des produits de placard (story 2.11)."""

from __future__ import annotations

import pytest

from custom_components.cookbook_menu.ingredients.catalogue_placard import (
    PRODUITS_PLACARD,
    est_produit_de_placard,
)
from custom_components.cookbook_menu.ingredients.normalize import cle


@pytest.mark.parametrize(
    "texte",
    ["Ras el hanout", "ras-el-hanout", "Riz basmati", "riz basmati bio", "Huile d'olive vierge extra",
     "Pâtes", "des lentilles corail", "Sauce soja", "Levure chimique", "Pignons de pin"],
)  # fmt: skip
def test_produits_reconnus(texte: str) -> None:
    assert est_produit_de_placard(cle(texte))


@pytest.mark.parametrize(
    "texte", ["Papier toilette", "Poêle", "Carotte", "Beurre", "Crème fraîche", "Lessive", "Poulet", ""]
)
def test_produits_hors_placard(texte: str) -> None:
    assert not est_produit_de_placard(cle(texte))


def test_index_sans_doublon_ni_cle_vide() -> None:
    cles = [cle(nom) for nom in PRODUITS_PLACARD]
    assert all(cles)
    assert len(PRODUITS_PLACARD) > 250
