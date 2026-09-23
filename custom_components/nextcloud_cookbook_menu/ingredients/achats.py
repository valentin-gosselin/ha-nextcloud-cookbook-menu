"""Purchase units: bring a recipe's quantities back to what you actually buy.

Recipes mix units for the same product ("10 g garlic", "2 cloves garlic", "1 tsp chopped
garlic"). For the shopping list, each common product has a purchase measure (piece, gram,
bunch...) and rough equivalences. The values are kitchen-level orders of magnitude: the goal
is a readable, sufficient line, not a precise weighing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Profil:
    """Purchase measure for a product, and equivalences from other measures."""

    achat: str
    conversions: dict[str, float] = field(default_factory=dict)
    nom: str | None = None


def _piece(poids: float, **autres: float) -> Profil:
    """Product bought by the piece, with an average weight in grams."""
    return Profil("pièce", {"g": 1 / poids, **autres})


def _poids(**conversions: float) -> Profil:
    """Product bought by weight (conversions in grams)."""
    return Profil("g", conversions)


_HERBE = Profil(
    "bouquet",
    {"brin": 0.1, "branche": 0.1, "feuille": 0.05, "poignée": 0.5, "c. à s.": 0.2, "c. à c.": 0.1,
     "g": 1 / 30, "pièce": 1, "botte": 1},
)  # fmt: skip

# Packaging sizes: what you actually buy in store. A recipe that calls for 10 g of butter
# means buying a whole stick, with the rest going into later dishes. Product key -> {measure: package}.
CONDITIONNEMENTS: dict[str, dict[str, float]] = {
    "beurre": {"g": 250},
    "beurre allege": {"g": 250},
    "beurre demi sel": {"g": 250},
    "margarine": {"g": 250},
    "creme fraiche": {"g": 200, "ml": 200},
    "creme liquide": {"ml": 200},
    "creme": {"g": 200, "ml": 200},
    "lait": {"ml": 1000},
    "lait amande": {"ml": 1000},
    "lait vegetal": {"ml": 1000},
    "yaourt": {"pièce": 4},
    "fromage blanc": {"g": 500},
    "mascarpone": {"g": 250},
    "ricotta": {"g": 250},
    "parmesan": {"g": 100},
    "parmesan rape": {"g": 100},
    "gruyere": {"g": 200},
    "emmental": {"g": 200},
    "fromage rape": {"g": 200},
    "comte": {"g": 200},
    "feta": {"g": 200},
    "mozzarella": {"g": 125},
    "chevre": {"g": 150},
    "oeuf": {"pièce": 6},
    "lardon": {"g": 200},
    "lardon fume": {"g": 200},
    "chorizo": {"g": 150},
    "jambon": {"pièce": 4, "g": 200},
    "saumon fume": {"g": 150},
    "thon": {"boîte": 1, "g": 140},
    "pomme terre": {"g": 1000},
    "carotte": {"g": 500},
    "champignon paris": {"g": 250},
    "haricot vert frais": {"g": 500},
    "salade verte": {"pièce": 1},
    "vinaigre": {"ml": 500},
    "sauce soja": {"ml": 250},
    "moutarde": {"g": 200},
    "mayonnaise": {"g": 250},
    "ketchup": {"g": 300},
}


def conditionnement(cle: str, mesure: str) -> float | None:
    """Package size bought for this product in this measure, if known."""
    paquets = CONDITIONNEMENTS.get(cle)
    return paquets.get(mesure) if paquets else None


PROFILS: dict[str, Profil] = {
    # Vegetables and fruit bought by the piece (average weights)
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
    # By weight
    "pomme terre": _poids(pièce=150),
    "champignon": _poids(pièce=20),
    "beurre": _poids(**{"c. à s.": 15, "c. à c.": 5, "noix": 10, "noisette": 5}),
    "creme fraiche": _poids(cl=10, ml=1, **{"c. à s.": 15, "c. à c.": 5}),
    "parmesan": _poids(**{"c. à s.": 6, "c. à c.": 2}),
    "gruyere": _poids(**{"c. à s.": 6, "poignée": 30}),
    "cacahuete": _poids(poignée=30, **{"c. à s.": 10}),
    # Garlic: bought by the head, counted by the clove
    "ail": Profil("gousse", {"g": 1 / 5, "ml": 1 / 5, "c. à c.": 0.5, "c. à s.": 1.5, "pièce": 1, "tête": 10}),
    "gingembre": Profil("morceau", {"c. à c.": 0.2, "c. à s.": 0.5, "g": 1 / 50, "pièce": 1}),
    # Packaged products
    "levure chimique": Profil("sachet", {"g": 1 / 11, "c. à c.": 0.45, "c. à s.": 1.35}),
    "sucre vanille": Profil("sachet", {"g": 1 / 7.5, "c. à c.": 0.6}),
    "lait coco": Profil("boîte", {"ml": 1 / 400, "c. à s.": 15 / 400, "c. à c.": 5 / 400}),
    "concentre tomate": Profil("boîte", {"g": 1 / 70, "c. à s.": 15 / 70, "c. à c.": 5 / 70, "pièce": 1}),
    "vin blanc sec": Profil("ml", {"verre": 150}),
    # Fresh herbs: one bunch covers several recipes
    "persil": _HERBE,
    "persil plat": _HERBE,
    "coriandre": _HERBE,
    "ciboulette": _HERBE,
    "menthe": _HERBE,
    "basilic": _HERBE,
    "aneth": _HERBE,
    "estragon": _HERBE,
}

# Products written differently but bought as another product.
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

# Generic equivalences when a product has no profile: spoons and knobs to g or ml.
_GENERIQUE = {"c. à s.": 15, "c. à c.": 5, "noix": 10, "noisette": 5}


def convertir(cle: str, mesure: str, valeur: float) -> tuple[str, str, float, str | None]:
    """(product key, measure, value, forced name) after alias and purchase unit."""
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
    """Without a profile: spoons and knobs merge into the grams or millilitres already present."""
    cible = "g" if "g" in quantites else "ml" if "ml" in quantites else None
    if cible is None:
        return quantites
    resultat = dict(quantites)
    for mesure, facteur in _GENERIQUE.items():
        if mesure in resultat:
            resultat[cible] += resultat.pop(mesure) * facteur
    return resultat
