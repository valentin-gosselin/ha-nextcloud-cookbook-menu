"""Shopping list computation: menu + recipes -> products to buy.

Pure, deterministic code (same inputs, same output), so recomputing on every change is
predictable and fully testable.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from .achats import ALIAS, PROFILS, conditionnement, convertir, fusionner_mesures
from .aisles import Rayon, rayon
from .normalize import sans_accents
from .pantry import est_au_placard
from .parser import Ingredient, analyser
from .units import UNITES, Famille

# Keys whose displayed name comes from an alias ("Œufs") and must not be replaced.
_NOMS_IMPOSES = {cible for cible, _, _ in ALIAS.values()}

_PLURIELS = {"morceau": "morceaux", "noix": "noix", "tête": "têtes", "pincée": "pincées", "boîte": "boîtes"}


@dataclass(frozen=True, slots=True)
class Contribution:
    """A recipe from the menu, with its scaling factor."""

    recette: str
    couverts: int
    facteur: float
    lignes: tuple[str, ...]


@dataclass(slots=True)
class LigneCourses:
    """A product to buy, aggregated over every recipe in the menu."""

    cle: str
    nom: str
    rayon: Rayon
    # Quantities per "measure": "g", "ml", "c. à c." (spoons brought back to c. à c.), a container
    # unit ("gousse"...), or "pièce" for quantities with no unit.
    quantites: dict[str, float] = field(default_factory=dict)
    sans_quantite: bool = False
    sources: dict[str, int] = field(default_factory=dict)

    @property
    def libelle(self) -> str:
        quantites = formater_quantites(self.quantites, self.cle)
        return f"{self.nom} ({quantites})" if quantites else self.nom

    def mesure(self) -> dict[str, float]:
        """Quantities rounded to what is actually bought, to compare two computations."""
        return {m: arrondir(m, q, self.cle) for m, q in self.quantites.items()}


def _mesure_et_valeur(ingredient: Ingredient, facteur: float) -> tuple[str, float] | None:
    quantite = ingredient.quantite_max or ingredient.quantite
    if quantite is None or quantite <= 0:
        return None
    quantite *= facteur
    unite = ingredient.unite
    if unite is None:
        return "pièce", quantite
    definition = UNITES[unite]
    if definition.famille is Famille.MASSE:
        return "g", quantite * definition.facteur
    if definition.famille is Famille.VOLUME:
        return "ml", quantite * definition.facteur
    if definition.famille is Famille.CUILLERE:
        return "c. à c.", quantite * definition.facteur / 5
    return unite, quantite


def arrondir(mesure: str, valeur: float, cle: str | None = None) -> float:
    """Quantity actually bought: rounded to the package when known, otherwise to the usual step."""
    if cle is not None and (paquet := conditionnement(cle, mesure)):
        return math.ceil(round(valeur / paquet, 6)) * paquet
    if mesure == "g":
        pas = 10 if valeur < 100 else 50
        return math.ceil(round(valeur, 6) / pas) * pas
    if mesure == "ml":
        pas = 10 if valeur < 100 else 50
        return math.ceil(round(valeur, 6) / pas) * pas
    if mesure == "c. à c.":
        return math.ceil(round(valeur, 6) * 2) / 2
    # Pieces and containers: round up to the next integer.
    return float(max(1, math.ceil(round(valeur, 6))))


def _nombre(valeur: float) -> str:
    """Rounded up to the nearest tenth, decimal comma: 1.25 gives "1,3"."""
    valeur = math.ceil(round(valeur * 10, 6)) / 10
    texte = f"{valeur:.1f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",")


def formater_quantites(quantites: dict[str, float], cle: str | None = None) -> str:
    """ "1 kg + 2 gousses" (1 kg + 2 cloves), with rounding to the purchase and readable units."""
    morceaux = []
    for mesure, valeur in quantites.items():
        arrondi = arrondir(mesure, valeur, cle)
        if mesure == "g":
            morceaux.append(f"{_nombre(arrondi / 1000)} kg" if arrondi >= 1000 else f"{int(arrondi)} g")
        elif mesure == "ml":
            if arrondi >= 1000:
                morceaux.append(f"{_nombre(arrondi / 1000)} l")
            elif arrondi >= 100:
                morceaux.append(f"{_nombre(arrondi / 10)} cl")
            else:
                morceaux.append(f"{int(arrondi)} ml")
        elif mesure == "c. à c.":
            if arrondi >= 3:
                morceaux.append(f"{_nombre(math.ceil(arrondi / 3 * 2) / 2)} c. à s.")
            else:
                morceaux.append(f"{_nombre(arrondi)} c. à c.")
        elif mesure == "pièce":
            morceaux.append(f"{int(arrondi)}")
        elif mesure == "gousse" and arrondi >= 10:
            tetes = math.ceil(arrondi / 10)
            morceaux.append(f"{tetes} tête{'s' if tetes > 1 else ''}")
        else:
            forme = mesure
            if arrondi > 1:
                forme = _PLURIELS.get(mesure, mesure if mesure.endswith(("s", "x")) else f"{mesure}s")
            morceaux.append(f"{int(arrondi)} {forme}")
    return " + ".join(morceaux)


def calculer(
    contributions: Iterable[Contribution],
    placard: Iterable[str] = (),
    epuises: Iterable[str] = (),
) -> tuple[list[LigneCourses], list[str]]:
    """Shopping lines sorted by aisle, and names of the pantry products left out.

    `epuises`: keys of pantry products flagged as out of stock, which become normal
    shopping items again.
    """
    placard = set(placard)
    epuises = set(epuises)
    lignes: dict[str, LigneCourses] = {}
    ecartes: dict[str, str] = {}
    for contribution in contributions:
        comptees: set[str] = set()
        for texte in contribution.lignes:
            for ingredient in analyser(texte):
                if ingredient.section or not ingredient.cle:
                    continue
                cle = ingredient.cle
                mesure = _mesure_et_valeur(ingredient, contribution.facteur)
                nom_impose = None
                if mesure is not None:
                    cle, unite, valeur, nom_impose = convertir(cle, *mesure)
                    mesure = (unite, valeur)
                elif cle in ALIAS:
                    cle, _, nom_impose = ALIAS[cle]
                if cle not in epuises and est_au_placard(cle, placard):
                    ecartes.setdefault(cle, ingredient.nom)
                    continue
                ligne = lignes.get(cle)
                if ligne is None:
                    ligne = lignes[cle] = LigneCourses(cle=cle, nom=nom_impose or ingredient.nom, rayon=rayon(cle))
                elif nom_impose:
                    ligne.nom = nom_impose
                elif len(ingredient.nom) < len(ligne.nom) and ligne.cle not in _NOMS_IMPOSES:
                    ligne.nom = ingredient.nom
                if cle not in comptees:
                    # A recipe that mentions a product twice ("salt" in the salad and the sauce)
                    # only counts its servings once.
                    comptees.add(cle)
                    ligne.sources[contribution.recette] = (
                        ligne.sources.get(contribution.recette, 0) + contribution.couverts
                    )
                if mesure is None:
                    ligne.sans_quantite = True
                else:
                    ligne.quantites[mesure[0]] = ligne.quantites.get(mesure[0], 0) + mesure[1]
    for ligne in lignes.values():
        if ligne.cle not in PROFILS:
            ligne.quantites = fusionner_mesures(ligne.quantites)
    return trier(lignes.values()), sorted(ecartes.values(), key=sans_accents)


def trier(lignes: Iterable[LigneCourses]) -> list[LigneCourses]:
    """Walk-through order in store: by aisle, then by name without accents."""
    return sorted(lignes, key=lambda produit: (produit.rayon, sans_accents(produit.nom)))


def augmentation(avant: dict[str, float], apres: dict[str, float]) -> dict[str, float]:
    """Measures whose rounded quantity increased (the delta), empty if nothing increased."""
    return {m: apres[m] - avant.get(m, 0) for m in apres if apres[m] > avant.get(m, 0) + 1e-9}
