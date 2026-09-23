"""Fridge: what was bought for the menu and not consumed yet (pure code).

Quantities are expressed in the shopping list's measures (g, ml, piece, clove...). Fresh
items expire after 7 days, pantry items after 60: beyond that, the product is considered
consumed or thrown out, so we never trust stock that no longer exists for long.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .aisles import Rayon

DUREE_FRAIS = timedelta(days=7)
DUREE_EPICERIE = timedelta(days=60)
# Only these aisles keep for a long time. An unrecognized product is treated as fresh:
# at worst it is forgotten too early and comes back on the shopping list, whereas meat kept
# for 60 days would make us think we still have it.
_RAYONS_LONGS = {Rayon.EPICERIE_SALEE, Rayon.EPICERIE_SUCREE, Rayon.SURGELES, Rayon.BOISSONS, Rayon.MAISON}


# Shelf life per product, when the aisle is not enough: garlic and potatoes keep for weeks,
# meat and lettuce only a few days.
DUREES_PRODUITS: dict[str, int] = {
    "ail": 30,
    "oignon": 30,
    "echalote": 30,
    "pomme terre": 30,
    "patate douce": 30,
    "courge": 30,
    "potimarron": 30,
    "butternut": 30,
    "gingembre": 21,
    "citron": 21,
    "orange": 14,
    "pomme": 14,
    "carotte": 14,
    "chou": 14,
    "oeuf": 21,
    "fromage": 14,
    "comte": 21,
    "parmesan": 30,
    "beurre": 30,
    "lardon": 10,
    "salade": 5,
    "tomate": 5,
    "champignon": 5,
    "herbe": 5,
    "persil": 5,
    "coriandre": 5,
    "basilic": 5,
    "menthe": 5,
    "poisson": 2,
    "saumon": 2,
    "crevette": 2,
    "viande hachee": 2,
    "boeuf hache": 2,
    "pain": 3,
}


def duree_de_vie(rayon: Rayon, cle: str | None = None) -> timedelta:
    """Shelf life: the per-product table first, then the aisle."""
    if cle:
        mots = cle.split()
        for longueur in range(len(mots), 0, -1):
            if (jours := DUREES_PRODUITS.get(" ".join(mots[:longueur]))) is not None:
                return timedelta(days=jours)
    return DUREE_EPICERIE if rayon in _RAYONS_LONGS else DUREE_FRAIS


def ajouter(
    frigo: dict[str, dict[str, Any]],
    cle: str,
    nom: str,
    quantites: dict[str, float],
    rayon: Rayon,
    jour: date,
) -> None:
    """Files away a purchase. The expiry date resets from the most recent purchase."""
    entree = frigo.setdefault(cle, {"nom": nom, "quantites": {}})
    for mesure, valeur in quantites.items():
        entree["quantites"][mesure] = round(entree["quantites"].get(mesure, 0) + valeur, 4)
    entree["expire"] = (jour + duree_de_vie(rayon, cle)).isoformat()


def retirer(frigo: dict[str, dict[str, Any]], cle: str, quantites: dict[str, float]) -> None:
    """Removes quantities; the product disappears once nothing is left."""
    entree = frigo.get(cle)
    if entree is None:
        return
    for mesure, valeur in quantites.items():
        if mesure in entree["quantites"]:
            reste = round(entree["quantites"][mesure] - valeur, 4)
            if reste > 1e-6:
                entree["quantites"][mesure] = reste
            else:
                del entree["quantites"][mesure]
    if not entree["quantites"]:
        del frigo[cle]


def expirer(frigo: dict[str, dict[str, Any]], jour: date) -> list[str]:
    """Removes expired products. Returns their names."""
    expires = [c for c, e in frigo.items() if e.get("expire") and date.fromisoformat(e["expire"]) < jour]
    noms = [frigo[c]["nom"] for c in expires]
    for c in expires:
        del frigo[c]
    return noms


def manque(besoin: dict[str, float], stock: dict[str, float]) -> dict[str, float]:
    """What is still left to buy, per measure (empty if stock covers everything)."""
    return {m: round(v - stock.get(m, 0), 4) for m, v in besoin.items() if v - stock.get(m, 0) > 1e-6}
