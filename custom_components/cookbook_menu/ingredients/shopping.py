"""Calcul de la liste de courses : menu + recettes -> produits à acheter.

Code pur et déterministe (mêmes entrées, même sortie), pour que le recalcul à chaque
changement soit sans surprise et entièrement testable.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from .aisles import Rayon, rayon
from .normalize import sans_accents
from .pantry import est_au_placard
from .parser import Ingredient, analyser
from .units import UNITES, Famille


@dataclass(frozen=True, slots=True)
class Contribution:
    """Une recette du menu, avec son facteur d'échelle."""

    recette: str
    couverts: int
    facteur: float
    lignes: tuple[str, ...]


@dataclass(slots=True)
class LigneCourses:
    """Un produit à acheter, agrégé sur toutes les recettes du menu."""

    cle: str
    nom: str
    rayon: Rayon
    # Quantités par « mesure » : "g", "ml", "c. à c." (cuillères ramenées en c. à c.), une unité de
    # contenant ("gousse"...), ou "pièce" pour les quantités sans unité.
    quantites: dict[str, float] = field(default_factory=dict)
    sans_quantite: bool = False
    sources: dict[str, int] = field(default_factory=dict)

    @property
    def libelle(self) -> str:
        quantites = formater_quantites(self.quantites)
        return f"{self.nom} ({quantites})" if quantites else self.nom

    def mesure(self) -> dict[str, float]:
        """Quantités arrondies à l'achat, pour comparer deux calculs."""
        return {m: _arrondir(m, q) for m, q in self.quantites.items()}


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


def _arrondir(mesure: str, valeur: float) -> float:
    if mesure == "g":
        pas = 10 if valeur < 100 else 50
        return math.ceil(round(valeur, 6) / pas) * pas
    if mesure == "ml":
        pas = 10 if valeur < 100 else 50
        return math.ceil(round(valeur, 6) / pas) * pas
    if mesure == "c. à c.":
        return math.ceil(round(valeur, 6) * 2) / 2
    # Pièces et contenants : entier supérieur.
    return float(max(1, math.ceil(round(valeur, 6))))


def _nombre(valeur: float) -> str:
    """Au dixième supérieur, virgule décimale : 1,25 donne « 1,3 »."""
    valeur = math.ceil(round(valeur * 10, 6)) / 10
    texte = f"{valeur:.1f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",")


def formater_quantites(quantites: dict[str, float]) -> str:
    """« 1 kg + 2 gousses », avec arrondi à l'achat et unités lisibles."""
    morceaux = []
    for mesure, valeur in quantites.items():
        arrondi = _arrondir(mesure, valeur)
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
        else:
            pluriel = "s" if arrondi > 1 and not mesure.endswith(("s", "x")) else ""
            morceaux.append(f"{int(arrondi)} {mesure}{pluriel}")
    return " + ".join(morceaux)


def calculer(
    contributions: Iterable[Contribution],
    placard: Iterable[str] = (),
    epuises: Iterable[str] = (),
) -> tuple[list[LigneCourses], list[str]]:
    """Lignes de courses triées par rayon, et noms des produits du placard écartés.

    `epuises` : clés de produits du placard signalés épuisés, qui redeviennent des courses normales.
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
                if cle not in epuises and est_au_placard(cle, placard):
                    ecartes.setdefault(cle, ingredient.nom)
                    continue
                ligne = lignes.get(cle)
                if ligne is None:
                    ligne = lignes[cle] = LigneCourses(cle=cle, nom=ingredient.nom, rayon=rayon(cle))
                elif len(ingredient.nom) < len(ligne.nom):
                    ligne.nom = ingredient.nom
                if cle not in comptees:
                    # Une recette qui cite deux fois un produit (« sel » dans la salade et la sauce)
                    # ne compte ses couverts qu'une fois.
                    comptees.add(cle)
                    ligne.sources[contribution.recette] = (
                        ligne.sources.get(contribution.recette, 0) + contribution.couverts
                    )
                mesure = _mesure_et_valeur(ingredient, contribution.facteur)
                if mesure is None:
                    ligne.sans_quantite = True
                else:
                    ligne.quantites[mesure[0]] = ligne.quantites.get(mesure[0], 0) + mesure[1]
    return trier(lignes.values()), sorted(ecartes.values(), key=sans_accents)


def trier(lignes: Iterable[LigneCourses]) -> list[LigneCourses]:
    """Ordre de passage en magasin : par rayon, puis par nom sans accents."""
    return sorted(lignes, key=lambda produit: (produit.rayon, sans_accents(produit.nom)))


def augmentation(avant: dict[str, float], apres: dict[str, float]) -> dict[str, float]:
    """Mesures dont la quantité arrondie a augmenté (écart), vide si rien n'a augmenté."""
    return {m: apres[m] - avant.get(m, 0) for m in apres if apres[m] > avant.get(m, 0) + 1e-9}
