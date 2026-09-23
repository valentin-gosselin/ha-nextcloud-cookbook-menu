"""Measurement units found in recipes (French first, common English next).

Each canonical unit belongs to a family. Only units from the same convertible family
(mass, volume) can be added together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Famille(StrEnum):
    """Unit family."""

    MASSE = "masse"
    VOLUME = "volume"
    CUILLERE = "cuillere"
    CONTENANT = "contenant"


@dataclass(frozen=True, slots=True)
class Unite:
    """Canonical unit."""

    code: str
    famille: Famille
    # Factor to the family's base unit (g for mass, ml for volume).
    facteur: float = 1.0


UNITES: dict[str, Unite] = {
    u.code: u
    for u in (
        Unite("mg", Famille.MASSE, 0.001),
        Unite("g", Famille.MASSE, 1),
        Unite("kg", Famille.MASSE, 1000),
        Unite("ml", Famille.VOLUME, 1),
        Unite("cl", Famille.VOLUME, 10),
        Unite("dl", Famille.VOLUME, 100),
        Unite("l", Famille.VOLUME, 1000),
        Unite("c. à s.", Famille.CUILLERE, 15),
        Unite("c. à c.", Famille.CUILLERE, 5),
        Unite("cuillère", Famille.CUILLERE, 10),
        *(
            Unite(code, Famille.CONTENANT)
            for code in (
                "pincée",
                "gousse",
                "branche",
                "brin",
                "botte",
                "bouquet",
                "feuille",
                "tranche",
                "rondelle",
                "sachet",
                "boîte",
                "pot",
                "paquet",
                "barquette",
                "brique",
                "noix",
                "noisette",
                "poignée",
                "morceau",
                "filet",
                "verre",
                "tasse",
                "bol",
                "cube",
                "dose",
                "trait",
                "goutte",
                "bâton",
                "tête",
                "grain",
                "zeste",
            )
        ),
    )
}

# Written variants -> canonical code. The regular expressions are applied to lowercased
# text; order matters (the longest ones first).
_VARIANTES: list[tuple[str, str]] = [
    # Tablespoons
    (r"cuill?(?:e|è)res?\s+(?:à|a)\s+soupe", "c. à s."),
    (r"cuil\.?\s*(?:à|a)\s*soupe", "c. à s."),
    (r"c\.?\s*(?:à|a)\.?\s*s(?:oupe)?\.?", "c. à s."),
    (r"càs|cas\b|cs|c\.s\.|tbsp|tablespoons?", "c. à s."),
    # Teaspoons
    (r"cuill?(?:e|è)res?\s+(?:à|a)\s+(?:café|cafe|thé|the)", "c. à c."),
    (r"cuil\.?\s*(?:à|a)\s*(?:café|cafe)", "c. à c."),
    (r"c\.?\s*(?:à|a)\.?\s*c(?:afé)?\.?", "c. à c."),
    (r"càc|cc|c\.c\.|tsp|teaspoons?", "c. à c."),
    (r"cuill?(?:e|è)res?|cuil\.", "cuillère"),
    # Mass
    (r"milligrammes?|mg", "mg"),
    (r"kilogrammes?|kilos?|kg", "kg"),
    (r"grammes?|gr\.?|g", "g"),
    # Volume
    (r"millilitres?|ml", "ml"),
    (r"centilitres?|cl", "cl"),
    (r"décilitres?|decilitres?|dl", "dl"),
    (r"litres?|l", "l"),
    # Containers and pieces
    (r"pinc(?:é|e)es?", "pincée"),
    (r"gousses?|gou\.", "gousse"),
    (r"branches?", "branche"),
    (r"brins?", "brin"),
    (r"bottes?", "botte"),
    (r"bouquets?", "bouquet"),
    (r"feuilles?", "feuille"),
    (r"tranches?", "tranche"),
    (r"rondelles?", "rondelle"),
    (r"sachets?|sac\.", "sachet"),
    (r"bo(?:î|i)tes?", "boîte"),
    (r"pots?", "pot"),
    (r"paquets?", "paquet"),
    (r"barquettes?", "barquette"),
    (r"briques?", "brique"),
    (r"noix", "noix"),
    (r"noisettes?", "noisette"),
    (r"poign(?:é|e)es?", "poignée"),
    (r"morceaux?", "morceau"),
    (r"filets?", "filet"),
    (r"verres?", "verre"),
    (r"tasses?", "tasse"),
    (r"bols?", "bol"),
    (r"cubes?", "cube"),
    (r"doses?", "dose"),
    (r"traits?", "trait"),
    (r"gouttes?", "goutte"),
    (r"b(?:â|a)tons?", "bâton"),
    (r"t(?:ê|e)tes?", "tête"),
    (r"grains?", "grain"),
]

_MOTIF = re.compile(
    r"^(?:" + "|".join(f"(?P<u{i}>{motif})" for i, (motif, _) in enumerate(_VARIANTES)) + r")(?=$|[\s.,(')’]|\d)",
    re.IGNORECASE,
)


def lire_unite(texte: str) -> tuple[str | None, str]:
    """Reads a unit at the start of `texte`. Returns (canonical code or None, rest of the text)."""
    correspondance = _MOTIF.match(texte)
    if correspondance is None:
        return None, texte
    groupe = next(nom for nom, valeur in correspondance.groupdict().items() if valeur is not None)
    code = _VARIANTES[int(groupe[1:])][1]
    # The end of the pattern requires a separator: the "g" in "gros" or the "l" in "lait"
    # are not units.
    return code, texte[correspondance.end() :].lstrip(" .")


def famille(code: str | None) -> Famille | None:
    """Family of a canonical unit."""
    return UNITES[code].famille if code in UNITES else None
