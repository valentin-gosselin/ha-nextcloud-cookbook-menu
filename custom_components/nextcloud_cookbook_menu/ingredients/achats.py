"""Unités d'achat : ramener les quantités d'une recette à ce qu'on achète vraiment.

Les recettes mélangent les unités pour un même produit (« 10 g d'ail », « 2 gousses d'ail »,
« 1 c. à café d'ail haché »). Pour la liste de courses, chaque produit courant a une mesure
d'achat (pièce, gramme, bouquet...) et des équivalences approximatives. Les valeurs sont des
ordres de grandeur de cuisine : l'objectif est une ligne lisible et suffisante, pas une pesée.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Profil:
    """Mesure d'achat d'un produit et équivalences depuis les autres mesures."""

    achat: str
    conversions: dict[str, float] = field(default_factory=dict)
    nom: str | None = None


def _piece(poids: float, **autres: float) -> Profil:
    """Produit acheté à la pièce, d'un poids moyen en grammes."""
    return Profil("pièce", {"g": 1 / poids, **autres})


def _poids(**conversions: float) -> Profil:
    """Produit acheté au poids (conversions en grammes)."""
    return Profil("g", conversions)


_HERBE = Profil(
    "bouquet",
    {"brin": 0.1, "branche": 0.1, "feuille": 0.05, "poignée": 0.5, "c. à s.": 0.2, "c. à c.": 0.1,
     "g": 1 / 30, "pièce": 1, "botte": 1},
)  # fmt: skip

PROFILS: dict[str, Profil] = {
    # Légumes et fruits à la pièce (poids moyens)
    "oignon": _piece(100),
    "oignon rouge": _piece(100),
    "oignon blanc": _piece(100),
    "echalote": _piece(30),
    "carotte": _piece(100),
    "tomate": _piece(120),
    "courgette": _piece(250),
    "aubergine": _piece(300),
    "poivron rouge": _piece(150),
    "poivron vert": _piece(150),
    "poireau": _piece(250),
    "navet": _piece(100),
    "pomme": _piece(150),
    "concombre": _piece(300),
    "avocat": _piece(200),
    "oignon nouveau": _piece(20),
    "salade": Profil("pièce", {"feuille": 1 / 15, "g": 1 / 300}),
    "orange": _piece(200, rondelle=0.1, ml=1 / 80),
    "citron": _piece(120, ml=1 / 30, **{"c. à s.": 0.5, "c. à c.": 1 / 6}),
    "citron vert": _piece(70, ml=1 / 20, **{"c. à s.": 0.75, "c. à c.": 0.25}),
    # Au poids
    "pomme terre": _poids(pièce=150),
    "champignon": _poids(pièce=20),
    "beurre": _poids(**{"c. à s.": 15, "c. à c.": 5, "noix": 10, "noisette": 5}),
    "creme fraiche": _poids(cl=10, ml=1, **{"c. à s.": 15, "c. à c.": 5}),
    "parmesan": _poids(**{"c. à s.": 6, "c. à c.": 2}),
    "gruyere": _poids(**{"c. à s.": 6, "poignée": 30}),
    "cacahuete": _poids(poignée=30, **{"c. à s.": 10}),
    # Ail : acheté en têtes, compté en gousses
    "ail": Profil("gousse", {"g": 1 / 5, "ml": 1 / 5, "c. à c.": 0.5, "c. à s.": 1.5, "pièce": 1, "tête": 10}),
    "gingembre": Profil("morceau", {"c. à c.": 0.2, "c. à s.": 0.5, "g": 1 / 50, "pièce": 1}),
    # Conditionnements
    "levure chimique": Profil("sachet", {"g": 1 / 11, "c. à c.": 0.45, "c. à s.": 1.35}),
    "sucre vanille": Profil("sachet", {"g": 1 / 7.5, "c. à c.": 0.6}),
    "lait coco": Profil("boîte", {"ml": 1 / 400, "c. à s.": 15 / 400, "c. à c.": 5 / 400}),
    "concentre tomate": Profil("boîte", {"g": 1 / 70, "c. à s.": 15 / 70, "c. à c.": 5 / 70, "pièce": 1}),
    "vin blanc sec": Profil("ml", {"verre": 150}),
    # Herbes fraîches : un bouquet couvre plusieurs recettes
    "persil": _HERBE,
    "persil plat": _HERBE,
    "coriandre": _HERBE,
    "ciboulette": _HERBE,
    "menthe": _HERBE,
    "basilic": _HERBE,
    "aneth": _HERBE,
    "estragon": _HERBE,
}

# Produits écrits autrement mais achetés comme un autre produit.
ALIAS: dict[str, tuple[str, dict[str, float], str]] = {
    "blanc oeuf": ("oeuf", {"g": 1 / 30, "pièce": 1}, "Œufs"),
    "jaune oeuf": ("oeuf", {"g": 1 / 20, "pièce": 1}, "Œufs"),
    "jus citron": ("citron", {"ml": 1 / 30, "c. à s.": 0.5, "c. à c.": 1 / 6, "pièce": 1}, "Citron"),
    "jus citron vert": (
        "citron vert",
        {"ml": 1 / 20, "c. à s.": 0.75, "c. à c.": 0.25, "pièce": 1},
        "Citron vert",
    ),
    "zeste citron": ("citron", {"pièce": 1}, "Citron"),
    "oignon emince": ("oignon", {}, "Oignon"),
}

# Équivalences génériques quand un produit n'a pas de profil : cuillères et noix vers g ou ml.
_GENERIQUE = {"c. à s.": 15, "c. à c.": 5, "noix": 10, "noisette": 5}


def convertir(cle: str, mesure: str, valeur: float) -> tuple[str, str, float, str | None]:
    """(clé produit, mesure, valeur, nom imposé) après alias et unité d'achat."""
    nom: str | None = None
    if cle in ALIAS:
        cible, conversions, nom = ALIAS[cle]
        if mesure in conversions:
            profil = PROFILS.get(cible)
            return cible, profil.achat if profil else "pièce", valeur * conversions[mesure], nom
        cle = cible
    profil = PROFILS.get(cle)
    if profil is not None and mesure in profil.conversions:
        return cle, profil.achat, valeur * profil.conversions[mesure], profil.nom or nom
    return cle, mesure, valeur, nom


def fusionner_mesures(quantites: dict[str, float]) -> dict[str, float]:
    """Sans profil : les cuillères et noix rejoignent les grammes ou millilitres déjà présents."""
    cible = "g" if "g" in quantites else "ml" if "ml" in quantites else None
    if cible is None:
        return quantites
    resultat = dict(quantites)
    for mesure, facteur in _GENERIQUE.items():
        if mesure in resultat:
            resultat[cible] += resultat.pop(mesure) * facteur
    return resultat
