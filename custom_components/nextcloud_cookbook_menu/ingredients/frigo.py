"""Frigo : ce qui a été acheté pour le menu et pas encore consommé (code pur).

Les quantités sont exprimées dans les mesures de la liste de courses (g, ml, pièce, gousse...).
Le frais expire au bout de 7 jours, l'épicerie au bout de 60 : au-delà, on considère le produit
consommé ou jeté, pour ne jamais croire longtemps à un stock qui n'existe plus.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .aisles import Rayon

DUREE_FRAIS = timedelta(days=7)
DUREE_EPICERIE = timedelta(days=60)
_RAYONS_FRAIS = {Rayon.FRUITS_LEGUMES, Rayon.CREMERIE, Rayon.BOUCHERIE_POISSON, Rayon.BOULANGERIE}


def duree_de_vie(rayon: Rayon) -> timedelta:
    return DUREE_FRAIS if rayon in _RAYONS_FRAIS else DUREE_EPICERIE


def ajouter(
    frigo: dict[str, dict[str, Any]],
    cle: str,
    nom: str,
    quantites: dict[str, float],
    rayon: Rayon,
    jour: date,
) -> None:
    """Range un achat. L'expiration repart de l'achat le plus récent."""
    entree = frigo.setdefault(cle, {"nom": nom, "quantites": {}})
    for mesure, valeur in quantites.items():
        entree["quantites"][mesure] = round(entree["quantites"].get(mesure, 0) + valeur, 4)
    entree["expire"] = (jour + duree_de_vie(rayon)).isoformat()


def retirer(frigo: dict[str, dict[str, Any]], cle: str, quantites: dict[str, float]) -> None:
    """Retire des quantités ; le produit disparaît quand il ne reste plus rien."""
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
    """Retire les produits expirés. Renvoie leurs noms."""
    expires = [c for c, e in frigo.items() if e.get("expire") and date.fromisoformat(e["expire"]) < jour]
    noms = [frigo[c]["nom"] for c in expires]
    for c in expires:
        del frigo[c]
    return noms


def manque(besoin: dict[str, float], stock: dict[str, float]) -> dict[str, float]:
    """Ce qu'il reste à acheter, par mesure (vide si le stock couvre tout)."""
    return {m: round(v - stock.get(m, 0), 4) for m, v in besoin.items() if v - stock.get(m, 0) > 1e-6}
