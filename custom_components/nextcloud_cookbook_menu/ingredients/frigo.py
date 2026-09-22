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
# Seuls ces rayons se gardent longtemps. Un produit non reconnu est traité comme du frais :
# au pire il est oublié trop tôt et revient dans les courses, alors qu'une viande gardée
# 60 jours ferait croire qu'on l'a encore.
_RAYONS_LONGS = {Rayon.EPICERIE_SALEE, Rayon.EPICERIE_SUCREE, Rayon.SURGELES, Rayon.BOISSONS, Rayon.MAISON}


# Durées de conservation par produit, quand le rayon ne suffit pas : l'ail et les pommes de terre
# tiennent des semaines, la viande et la salade quelques jours.
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
    """Durée de conservation : la table par produit d'abord, le rayon ensuite."""
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
    """Range un achat. L'expiration repart de l'achat le plus récent."""
    entree = frigo.setdefault(cle, {"nom": nom, "quantites": {}})
    for mesure, valeur in quantites.items():
        entree["quantites"][mesure] = round(entree["quantites"].get(mesure, 0) + valeur, 4)
    entree["expire"] = (jour + duree_de_vie(rayon, cle)).isoformat()


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
