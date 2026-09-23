"""Fuzzy search for a recipe by name (accents, case, plurals, minor typos)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .api import Recipe
from .ingredients.normalize import sans_accents, singulier

# Words that carry no weight when distinguishing two recipes.
_MOTS_VIDES = {
    "de", "d", "du", "des", "la", "le", "les", "l", "a", "au", "aux", "en", "et", "un", "une",
    "facon", "maison", "recette", "the", "of", "with", "and",
}  # fmt: skip

# Minimum score to automatically link a line entered in the UI to a recipe.
SEUIL_LIEN = 0.75
# Two recipes whose scores are closer than this gap are considered ambiguous.
ECART_AMBIGUITE = 0.05


@dataclass(frozen=True, slots=True)
class Correspondance:
    """A candidate recipe and its score (0 to 1)."""

    recette: Recipe
    score: float


def _mots(texte: str) -> list[str]:
    texte = re.sub(r"[^a-z0-9]+", " ", sans_accents(texte))
    return [singulier(m) for m in texte.split() if m not in _MOTS_VIDES]


def _ressemblance(a: str, b: str) -> float:
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= 0.8 else 0.0


def score(requete: str, nom: str) -> float:
    """Match score between a query and a recipe name."""
    mots_requete, mots_nom = _mots(requete), _mots(nom)
    if not mots_requete or not mots_nom:
        return 0.0
    if mots_requete == mots_nom:
        return 1.0
    meilleurs = [max(_ressemblance(q, n) for n in mots_nom) for q in mots_requete]
    rappel = sum(meilleurs) / len(mots_requete)
    trouves = {n for n in mots_nom if any(_ressemblance(q, n) for q in mots_requete)}
    precision = len(trouves) / len(mots_nom)
    return round(0.7 * rappel + 0.3 * precision, 4)


def chercher(requete: str, recettes: list[Recipe], limite: int = 5) -> list[Correspondance]:
    """Recipes ranked by descending score (zero scores excluded)."""
    candidats = [Correspondance(r, score(requete, r.name)) for r in recettes]
    candidats = [c for c in candidats if c.score > 0]
    candidats.sort(key=lambda c: (-c.score, c.recette.name.casefold()))
    return candidats[:limite]


def est_ambigu(candidats: list[Correspondance]) -> bool:
    """True if the best recipe isn't clearly ahead of the second one."""
    if len(candidats) < 2 or candidats[0].score == 1.0:
        return False
    return candidats[0].score - candidats[1].score < ECART_AMBIGUITE


def lien_automatique(requete: str, recettes: list[Recipe]) -> tuple[Recipe | None, list[Correspondance]]:
    """Recipe to link without asking (score high enough and no ambiguity), and the candidates."""
    candidats = chercher(requete, recettes)
    if candidats and candidats[0].score >= SEUIL_LIEN and not est_ambigu(candidats):
        return candidats[0].recette, candidats
    return None, candidats
