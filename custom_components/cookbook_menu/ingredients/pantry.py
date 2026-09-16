"""Placard : produits de base qu'on a toujours et qu'on n'ajoute pas à chaque recette."""

from __future__ import annotations

from collections.abc import Iterable

from .normalize import cle

# Placard par défaut, resserré sur l'universel (party mode du 16/09/2026). Le reste s'ajoute dans les options.
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

# Familles où toute variante reste un produit de placard (« poivre du moulin », « vinaigre de cidre »).
_FAMILLES = {"sel", "poivre", "huile", "vinaigre", "laurier"}


def cles_placard(noms: Iterable[str]) -> set[str]:
    """Clés de fusion des produits du placard."""
    return {c for c in (cle(nom) for nom in noms) if c}


def est_au_placard(cle_produit: str, placard: set[str]) -> bool:
    """Vrai si le produit est au placard, directement ou par sa famille.

    Exemple : « huile » au placard couvre aussi « huile de sésame ».
    """
    if cle_produit in placard:
        return True
    premier = cle_produit.split(" ", 1)[0]
    return premier in _FAMILLES and premier in placard
