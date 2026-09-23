"""Durations written in a recipe's steps, to turn them into timers.

Real-world examples: "25 mn", "40 to 45 minutes", "1-2 minutes", "2 or 3 min", "1/2 hour",
"1 h 30", "30 seconds". For a range, the timer takes the smallest value: we check on the
cooking as early as possible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NOMBRE = r"\d+(?:[.,]\d+)?|\d+\s*/\s*\d+|½|un|une|deux|trois|quatre|cinq|dix|quinze|vingt|trente"
_MOTS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "dix": 10, "quinze": 15, "vingt": 20, "trente": 30,
}  # fmt: skip
_UNITES = {
    "h": 3600, "heure": 3600, "heures": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
    "min": 60, "mins": 60, "minute": 60, "minutes": 60, "mn": 60,
    "s": 1, "sec": 1, "seconde": 1, "secondes": 1, "second": 1, "seconds": 1,
}  # fmt: skip

_DUREE = re.compile(
    rf"(?<![\w/])(?P<a>{_NOMBRE})(?:\s*(?:à|a|-|ou|to|or)\s*(?P<b>{_NOMBRE}))?\s*"
    r"(?P<unite>heures?|hours?|hr|h|minutes?|mins?|min|mn|secondes?|seconds?|sec|s)\b"
    rf"(?:\s*(?P<complement>\d{{1,2}})(?!\s*(?:min|mn|s)))?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Minuteur:
    """A duration found in a text."""

    texte: str
    debut: int
    fin: int
    secondes: int


def _valeur(texte: str) -> float:
    texte = texte.strip().lower()
    if texte in _MOTS:
        return float(_MOTS[texte])
    if texte == "½":
        return 0.5
    if "/" in texte:
        numerateur, denominateur = (int(x) for x in texte.split("/"))
        return numerateur / denominateur if denominateur else 0.0
    return float(texte.replace(",", "."))


def trouver_minuteurs(texte: str) -> list[Minuteur]:
    """Durations found in a step, in text order."""
    resultat: list[Minuteur] = []
    for correspondance in _DUREE.finditer(texte or ""):
        unite = _UNITES[correspondance.group("unite").lower()]
        secondes = _valeur(correspondance.group("a")) * unite
        # "1 h 30": minutes after the hours.
        if correspondance.group("complement") and unite == 3600:
            secondes += int(correspondance.group("complement")) * 60
        # "s" alone after a number is too ambiguous ("2 s" could be a typo) except for "sec".
        if correspondance.group("unite") == "s" and secondes < 5:
            continue
        if secondes <= 0:
            continue
        resultat.append(
            Minuteur(
                texte=correspondance.group(0).strip(),
                debut=correspondance.start(),
                fin=correspondance.end(),
                secondes=round(secondes),
            )
        )
    return resultat
