"""Pantry: staple products we always have and do not add for every recipe."""

from __future__ import annotations

from collections.abc import Iterable

from .normalize import cle

# Default pantry, narrowed down to the universal staples (party mode on 16/09/2026). The rest is added in the options.
PLACARD_PAR_DEFAUT: tuple[str, ...] = (
    "Sel",
    "Poivre",
    "Huile",
    "Huile d'olive",
    "Huile de tournesol",
    "Vinaigre",
    "Sucre",
    "Farine",
    "Cumin",
    "Curry",
    "Curcuma",
    "Paprika",
    "Cannelle",
    "Muscade",
    "Piment de Cayenne",
    "Herbes de Provence",
    "Origan",
    "Eau",
    "Laurier",
)

# Families where every variant stays a pantry product ("peppercorns from the mill", "cider vinegar").
_FAMILLES = {"sel", "poivre", "huile", "vinaigre", "laurier"}


def cles_placard(noms: Iterable[str]) -> set[str]:
    """Merge keys of the pantry products."""
    return {c for c in (cle(nom) for nom in noms) if c}


def est_au_placard(cle_produit: str, placard: set[str]) -> bool:
    """True if the product is in the pantry, directly or through its family.

    Example: "huile" (oil) in the pantry also covers "huile de sésame" (sesame oil).
    """
    if cle_produit in placard:
        return True
    premier = cle_produit.split(" ", 1)[0]
    return premier in _FAMILLES and premier in placard
