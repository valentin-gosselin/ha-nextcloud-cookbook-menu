"""Parsing of a free-text ingredient line, French first.

Real-world examples: "0.5 Citron(s)", "2 tbsp olive oil", "1 1/2 glass dry white wine",
"7-8 mushrooms", "Salt, pepper", "Meringue:". A line that is not understood keeps its raw
text as the name, with no quantity or unit: an intact label beats a wrong interpretation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import cle
from .units import lire_unite

_FRACTIONS_UNICODE = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125}

_NOMBRES_EN_LETTRES = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "demi": 0.5,
    "demie": 0.5,
}

# Vague quantities: no number, but we keep the mention.
_QUANTITES_VAGUES = ("un peu", "quelques", "un filet", "une pointe", "un trait")

_NOMBRE = r"(?:\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|[½¼¾⅓⅔⅛])"
_QUANTITE = re.compile(
    rf"^(?P<a>{_NOMBRE}(?:\s+\d+\s*/\s*\d+|\s*[½¼¾⅓⅔⅛])?)"
    rf"(?:\s*(?:-|à|a|ou)\s*(?P<b>{_NOMBRE}))?"
    r"(?=\s|[a-zA-Zàâäéèêëîïôöùûüç(]|$)",
)

# Adjectives that can slip in between the quantity and the unit, or right after the unit.
_ADJECTIFS = (
    r"(?:grosses?|gros|petites?|petits?|belles?|beaux?|bonnes?|bons?|grandes?|grands?"
    r"|épaisses?|épais|rases?|bombées?|baby|bien\s+pleines?)"
)


_CONDIMENTS_ASSOCIES = {"sel", "poivre", "muscade", "huile", "huile d'olive"}


@dataclass(frozen=True, slots=True)
class Ingredient:
    """A parsed ingredient line."""

    brut: str
    nom: str
    quantite: float | None = None
    quantite_max: float | None = None
    unite: str | None = None
    note: str | None = None
    facultatif: bool = False
    section: bool = False
    vague: str | None = None

    @property
    def cle(self) -> str:
        """Merge key of the product."""
        return cle(self.nom)


def _nombre(texte: str) -> float:
    texte = texte.strip()
    total = 0.0
    for morceau in re.findall(r"\d+\s*/\s*\d+|\d+(?:[.,]\d+)?|[½¼¾⅓⅔⅛]", texte):
        if morceau in _FRACTIONS_UNICODE:
            total += _FRACTIONS_UNICODE[morceau]
        elif "/" in morceau:
            numerateur, denominateur = (int(x) for x in morceau.split("/"))
            total += numerateur / denominateur if denominateur else 0
        else:
            total += float(morceau.replace(",", "."))
    return round(total, 4)


def _nettoyer(ligne: str) -> str:
    ligne = ligne.replace("’", "'").replace("`", "'").replace(" ", " ")
    ligne = re.sub(r"\((?:s|x|es)\)", "", ligne, flags=re.IGNORECASE)
    ligne = re.sub(r"^[\s\-•*·]+", "", ligne)
    ligne = re.sub(r"\s+", " ", ligne).strip()
    ligne = re.sub(r"\b(d|l)'\s+", r"\1'", ligne, flags=re.IGNORECASE)
    ligne = re.sub(r"\(\s+", "(", ligne)
    return re.sub(r"\s+\)", ")", ligne)


def _est_section(ligne: str) -> bool:
    if re.search(r"\d", ligne):
        return False
    if ligne.endswith(":"):
        return True
    return bool(re.match(r"^pour\s+(?:la|le|les|l')\s*\S+(?:\s+\S+){0,3}$", ligne, re.IGNORECASE))


def _decouper(ligne: str) -> list[str]:
    """Splits lines that contain several ingredients.

    Examples: "Salt, pepper", "1/2 glass water, 1/2 glass sugar". Commas inside parentheses
    do not split anything ("Spices (cumin, paprika)").
    """
    if "(" in ligne:
        return [ligne]
    minuscule = ligne.lower()
    if re.fullmatch(r"(?:sel|poivre)\s+(?:et\s+)?(?:sel|poivre)", minuscule):
        return re.split(r"\s+(?:et\s+)?", ligne, maxsplit=1)
    morceaux = [m.strip() for m in re.split(r"(?<!\d),\s*|,\s+|\s+et\s+", ligne) if m.strip()]
    if len(morceaux) > 1:
        sans_quantite = not _QUANTITE.match(ligne)
        tous_courts = all(len(m.split()) <= 3 for m in morceaux)
        if sans_quantite and tous_courts:
            return morceaux
    # "1/2 glass water, 1/2 glass sugar": each piece starts with a quantity.
    par_virgule = [m.strip() for m in re.split(r"(?<!\d),\s*|,\s+", ligne)]
    if len(par_virgule) > 1 and all(_QUANTITE.match(m) for m in par_virgule):
        return par_virgule
    return [ligne]


def _extraire_notes(nom: str) -> tuple[str, list[str], bool]:
    """Pulls the parentheses, the details after a comma and the extras out of the name."""
    notes: list[str] = []
    facultatif = False

    def garder(texte: str) -> None:
        nonlocal facultatif
        texte = texte.strip(" ,;")
        if re.search(r"facultatif|optionnel|si désiré|si besoin", texte, re.IGNORECASE):
            facultatif = True
        notes.append(texte)

    taille = re.search(r"\s+de\s+\d+(?:[.,]\d+)?\s*(?:g|gr|kg|ml|cl|l)\b", nom, re.IGNORECASE)
    if taille:
        garder(taille.group(0).strip()[3:])
        nom = nom[: taille.start()] + nom[taille.end() :]

    for motif in (
        r"\s+\+\s+.*$",
        r",?\s+soit\s+.*$",
        r"\s+pour\s+(?:la|le|les|l'|beurrer|la cuisson).*$",
        r"\s+si\s+désiré.*$",
        r"\s+ou\s+(?:\d|[½¼¾]).*$",
        r"\s+ou\s+(?:une?|de\s+la|du|des|d')\s.*$",
        r",\s+.*$",
    ):
        correspondance = re.search(motif, nom, re.IGNORECASE)
        if correspondance:
            garder(correspondance.group(0))
            nom = nom[: correspondance.start()]

    # Simple "X or Y" alternative: we keep X as the product, Y as a note.
    correspondance = re.search(r"\s+ou\s+(?P<alt>.+)$", nom, re.IGNORECASE)
    if correspondance:
        garder(f"ou {correspondance.group('alt')}")
        nom = nom[: correspondance.start()]

    nom = re.sub(r"\s+(?:rases?|bombées?)$", "", nom.strip(), flags=re.IGNORECASE)
    return nom.strip(" ,;.-"), notes, facultatif


def _analyser_un(ligne: str, brut: str) -> Ingredient:
    notes_parentheses: list[str] = []
    while (parenthese := re.search(r"\(([^()]*)\)?", ligne)) is not None:
        if parenthese.group(1).strip():
            notes_parentheses.append(parenthese.group(1).strip())
        ligne = re.sub(r"\s+", " ", ligne[: parenthese.start()] + " " + ligne[parenthese.end() :]).strip()
    reste = ligne
    quantite: float | None = None
    quantite_max: float | None = None
    vague: str | None = None

    minuscule = reste.lower()
    for expression in _QUANTITES_VAGUES:
        if minuscule.startswith(expression + " "):
            vague = expression
            reste = reste[len(expression) :].strip()
            reste = re.sub(r"^(?:de\s+|d')", "", reste, flags=re.IGNORECASE)
            break

    if vague is None:
        correspondance = _QUANTITE.match(reste)
        if correspondance:
            quantite = _nombre(correspondance.group("a"))
            if correspondance.group("b"):
                quantite_max = _nombre(correspondance.group("b"))
            reste = reste[correspondance.end() :].strip()
        else:
            mot = re.match(r"^(\w+)\s+", reste)
            if mot and mot.group(1).lower() in _NOMBRES_EN_LETTRES:
                quantite = float(_NOMBRES_EN_LETTRES[mot.group(1).lower()])
                reste = reste[mot.end() :]

    # Adjective before the unit: "1 grosses poignées de coriandre" (1 big handfuls of coriander).
    avant_unite = re.match(rf"^{_ADJECTIFS}\s+", reste, re.IGNORECASE)
    candidat = reste[avant_unite.end() :] if avant_unite else reste
    unite, apres = lire_unite(candidat)
    if unite is not None and quantite is None and vague is None and not re.match(r"^\s*(?:de|d')", apres):
        # A unit with no quantity is only accepted when followed by "de" ("paquet de crêpes",
        # a pack of pancakes).
        unite, apres = None, candidat
    if unite is not None:
        reste = apres
        # "1 verre 1/2 de vin" (1 1/2 glass of wine): fraction after the unit.
        fraction = re.match(r"^\s*(\d+\s*/\s*\d+|[½¼¾])\s+", reste)
        if fraction and quantite is not None:
            quantite = round(quantite + _nombre(fraction.group(1)), 4)
            reste = reste[fraction.end() :]
        # "1 feuille ou pincée de quatre-épices" (1 leaf or pinch of allspice): alternative unit ignored.
        alternative = re.match(r"^\s*ou\s+(\w+)\s+", reste, re.IGNORECASE)
        if alternative and lire_unite(alternative.group(1) + " ")[0]:
            reste = reste[alternative.end() :]
        reste = re.sub(rf"^\s*(?:{_ADJECTIFS}\s+)+", "", reste, flags=re.IGNORECASE)
        reste = re.sub(r"^\s*,\s*", "", reste)
    elif avant_unite is None and quantite is not None:
        # "1/4 de litre de lait" (1/4 of a litre of milk): "de" between the quantity and the unit.
        de_unite = re.match(r"^(?:de|d')\s*", reste, re.IGNORECASE)
        if de_unite:
            unite_de, apres_de = lire_unite(reste[de_unite.end() :])
            if unite_de is not None:
                unite, reste = unite_de, apres_de

    reste = re.sub(r"^(?:hach[ée]e?s?|émincée?s?)\s+", "", reste.strip(), flags=re.IGNORECASE)
    reste = re.sub(r"^(?:de\s+la\s+|de\s+l'|du\s+|des\s+|de\s+|d')", "", reste.strip(), flags=re.IGNORECASE)

    # Packaging: "1 barquette de 250gr de tomates" (1 tray of 250g tomatoes) -> size goes into the note.
    notes: list[str] = list(notes_parentheses)
    conditionnement = re.match(
        r"^(?P<taille>\d+(?:[.,]\d+)?\s*(?:g|gr|kg|ml|cl|l)\b(?:\s+net)?(?:\s+égoutté)?)\s+(?:de|d')\s*",
        reste,
        re.IGNORECASE,
    )
    if conditionnement and unite is not None:
        notes.append(conditionnement.group("taille"))
        reste = reste[conditionnement.end() :]

    nom, autres_notes, facultatif = _extraire_notes(reste)
    notes.extend(autres_notes)
    facultatif = facultatif or any(re.search(r"facultatif|optionnel", n, re.IGNORECASE) for n in notes_parentheses)
    # R. "bouquet garni": the unit is actually part of the name.
    if unite == "bouquet" and nom.lower() == "garni":
        nom, unite = "bouquet garni", None
    if not nom:
        return Ingredient(brut=brut, nom=brut.strip())

    return Ingredient(
        brut=brut,
        nom=nom[0].upper() + nom[1:],
        quantite=quantite,
        quantite_max=quantite_max,
        unite=unite,
        note="; ".join(notes) or None,
        facultatif=facultatif,
        vague=vague,
    )


def analyser(ligne: str) -> list[Ingredient]:
    """Parses a line.

    Returns a list: a line can contain several ingredients, or be just a section title.
    """
    brut = ligne if isinstance(ligne, str) else ""
    propre = _nettoyer(brut)
    if not propre:
        return []
    if _est_section(propre):
        return [Ingredient(brut=brut, nom=propre.rstrip(" :"), section=True)]
    resultat: list[Ingredient] = []
    morceaux = _decouper(propre)
    for morceau in morceaux:
        try:
            ingredient = _analyser_un(morceau, brut)
        except ValueError, ZeroDivisionError, IndexError:  # pragma: no cover - safety net
            ingredient = Ingredient(brut=brut, nom=morceau)
        resultat.append(ingredient)
    # "1 pincée de muscade et poivre" (1 pinch of nutmeg and pepper): same quantity for paired condiments.
    if len(resultat) == 1 and " et " in resultat[0].nom:
        gauche, droite = resultat[0].nom.split(" et ", 1)
        if gauche.lower() in _CONDIMENTS_ASSOCIES and droite.lower() in _CONDIMENTS_ASSOCIES:
            base = resultat[0]
            resultat = [
                Ingredient(brut=brut, nom=gauche, quantite=base.quantite, unite=base.unite),
                Ingredient(brut=brut, nom=droite.capitalize(), quantite=base.quantite, unite=base.unite),
            ]
    return resultat
