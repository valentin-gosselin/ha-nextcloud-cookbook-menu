"""Parsing of a free-form voice request: "a caesar salad thursday for four"."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NOMBRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
    "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six_en": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12,
}  # fmt: skip
_NOMBRE = r"(\d{1,2}|" + "|".join(k for k in _NOMBRES if not k.endswith("_en")) + r")"

_COUVERTS = {
    "fr": re.compile(rf"\bpour\s+{_NOMBRE}(?:\s+(?:personnes?|couverts?|pers))?\b", re.IGNORECASE),
    "en": re.compile(rf"\bfor\s+{_NOMBRE}(?:\s+(?:people|persons?|servings?|guests?))?\b", re.IGNORECASE),
}
_JOURS = {
    "fr": re.compile(
        r"\b(?:(?:pour|le|ce)\s+)*(?P<jour>(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)(?:\s+prochain)?"
        r"|aujourd'hui|aujourd hui|ce\s+soir|ce\s+midi|après[- ]demain|apres[- ]demain|demain)\b",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"\b(?:(?:on|for)\s+)*(?P<jour>(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"|today|tonight|tomorrow)\b",
        re.IGNORECASE,
    ),
}
_ARTICLES = {
    "fr": re.compile(r"^(?:(?:une|un|des|du|de\s+la|le|la|les)\s+|de\s+l'|l')", re.IGNORECASE),
    "en": re.compile(r"^(?:a|an|the|some)\s+", re.IGNORECASE),
}


@dataclass(frozen=True, slots=True)
class Demande:
    """Dish, day and headcount extracted from a sentence."""

    plat: str
    jour: str | None = None
    couverts: int | None = None


# Words that give away the sentence's language. Words common to both languages ("menu",
# "salad", numbers) are excluded: only function words count.
_MARQUEURS = {
    "fr": re.compile(
        r"\b(?:ajoute|ajouter|ajoutes|rajoute|rajouter|mets|met|mettre|prevois|planifie|retire|retirer"
        r"|enleve|supprime|annule|une|un|des|du|de|la|le|les|au|aux|pour|avec|mange|manger|mangé|mange"
        r"|cuisine|cuisiné|fait|quoi|quel|quelle|quand|qu|est|ce|on|nous|je|il|plus|prochain|prochaine"
        r"|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|demain|aujourd|hui|soir|midi|semaine)\b",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"\b(?:add|adds|put|plan|remove|delete|cancel|a|an|the|some|to|on|from|for|with|we|our|what|when"
        r"|did|eat|ate|eating|have|had|cook|cooked|out|no|more|dinner|lunch|weekly|next|last"
        r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|tonight)\b",
        re.IGNORECASE,
    ),
}


def langue(code: str | None) -> str:
    """ "fr" for any variant of French, "en" otherwise."""
    return "fr" if (code or "").lower().startswith("fr") else "en"


def detecter_langue(texte: str | None, code_langue: str | None) -> str:
    """Language of the spoken sentence, rather than the one configured in Home Assistant.

    Sentences are recognized regardless of the pipeline's language: a French sentence spoken to
    a Home Assistant instance set up in English must still be parsed and answered in French.
    """
    texte = (texte or "").replace("’", "'")
    scores = {cle: len(marqueurs.findall(texte)) for cle, marqueurs in _MARQUEURS.items()}
    if scores["fr"] != scores["en"]:
        return "fr" if scores["fr"] > scores["en"] else "en"
    return langue(code_langue)


def analyser_demande(texte: str, code_langue: str | None) -> Demande:
    """Split the dish from the day and headcount, in the order they're spoken."""
    cle = langue(code_langue)
    reste = re.sub(r"\s+", " ", texte.replace("’", "'")).strip(" .!?,")
    couverts = None
    if correspondance := _COUVERTS[cle].search(reste):
        valeur = correspondance.group(1).lower()
        couverts = int(valeur) if valeur.isdigit() else _NOMBRES.get(valeur, _NOMBRES.get(f"{valeur}_en"))
        reste = reste[: correspondance.start()] + reste[correspondance.end() :]
    jour = None
    if correspondance := _JOURS[cle].search(reste):
        jour = correspondance.group("jour")
        reste = reste[: correspondance.start()] + reste[correspondance.end() :]
    plat = _ARTICLES[cle].sub("", re.sub(r"\s+", " ", reste).strip(" ,"))
    return Demande(plat=plat.strip(), jour=jour, couverts=couverts or None)
