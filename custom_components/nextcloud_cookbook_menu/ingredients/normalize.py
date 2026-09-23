"""Merge key for an ingredient name: two lines with the same key designate the same product to buy."""

from __future__ import annotations

import re
import unicodedata

# Stop words removed from the key.
_MOTS_VIDES = {"de", "d", "du", "des", "la", "le", "les", "l", "a", "au", "aux", "en", "et", "un", "une"}

# Qualifiers that do not change the product bought (preparation, size, ripeness).
_QUALIFICATIFS = {
    "emince",
    "rape",
    "cisele",
    "battu",
    "presse",
    "tamise",
    "ramolli",
    "fondu",
    "mou",
    "tres",
    "bien",
    "fait",
    "entier",
    "gros",
    "grosse",
    "petit",
    "petite",
    "moyen",
    "moyenne",
    "beau",
    "bel",
    "belle",
    "mur",
    "mure",
    "frais",
    "fraiche",
    "concasse",
    "emiette",
    "decoupe",
    "coupe",
    "epais",
    "epaisse",
    "allege",
    "legere",
    "leger",
    "doux",
    "dur",
    "tiede",
    "froid",
    "baby",
    "rase",
    "bombee",
    "bombe",
    "supplementaire",
    "copeau",
    "rondelle",
    "cru",
    "maigre",
    "rapee",
    "emincee",
    "ciselee",
    "battue",
    "pressee",
    "tamisee",
    "ramollie",
    "fondue",
    "concassee",
    "emiettee",
    "decoupee",
    "coupee",
    "allegee",
    "douce",
    "entiere",
    "froide",
    "moyens",
    "gro",
}

# "chopped/minced" does not change the product, except for meat (minced steak, minced beef).
_VIANDES = {"boeuf", "porc", "veau", "viande", "poulet", "agneau", "dinde", "volaille"}

# Invariable words that already end in s or x in the singular.
_INVARIABLES = {
    "pois",
    "radis",
    "ananas",
    "jus",
    "anis",
    "gras",
    "mais",
    "cassis",
    "bras",
    "noix",
    "riz",
    "brebis",
    "pastis",
    "ris",
    "fils",
    "os",
    "kirsch",
    "roux",
    "doux",
    "gris",
    "mars",
    "sans",
    "frais",
    "epais",
    "gros",
    "ras",
}

# Key equivalences (after normalization), for products written in several different ways.
EQUIVALENCES: dict[str, str] = {
    "poudre amande": "amande poudre",
    "sucre poudre": "sucre",
    "sucre semoule": "sucre",
    "sucre blanc": "sucre",
    "creme fraiche epaisse": "creme fraiche",
    "gousse ail": "ail",
    "oignon jaune": "oignon",
    "pomme terre chair ferme": "pomme terre",
    "pomme terre chair farineuse": "pomme terre",
    "tomate pelee": "tomate",
    "sauce soya": "sauce soja",
    "huile neutre": "huile",
    "boeuf hache": "viande hachee",
    "viande hache": "viande hachee",
    "cacahuete grillee": "cacahuete",
    "salade verte": "salade",
    "laitue": "salade",
    "coriandre fraiche": "coriandre",
    "miel liquide": "miel",
    "farine ble": "farine",
    "farine ble mi blanche": "farine",
    "oeuf dur": "oeuf",
}


def sans_accents(texte: str) -> str:
    """Lowercase, no accents, ligatures expanded."""
    texte = texte.casefold().replace("œ", "oe").replace("æ", "ae")
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def singulier(mot: str) -> str:
    """Approximate singular of a French word (without accents)."""
    if len(mot) <= 3 or mot in _INVARIABLES:
        return mot
    if mot.endswith(("eaux", "eux", "oux")):
        return mot[:-1]
    if mot.endswith("aux"):
        return mot[:-3] + "al"
    # Words ending in -is, -us, -os, -as are almost always invariable in French (e.g. "radis",
    # "couscous", "anchois").
    if mot.endswith("s") and not mot.endswith(("ss", "is", "us", "os", "as")):
        return mot[:-1]
    return mot


def cle(nom: str) -> str:
    """Merge key for an ingredient name."""
    texte = sans_accents(nom)
    texte = texte.replace("(s)", "s")
    texte = re.sub(r"\([^)]*\)", " ", texte)
    texte = re.sub(r"[’'`]", " ", texte)
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    bruts = [m for m in texte.split() if m not in _MOTS_VIDES and not m.isdigit()]
    mots = [singulier(m) for m in bruts]
    garde: list[str] = []
    for brut, mot in zip(bruts, mots, strict=True):
        if brut in _QUALIFICATIFS or mot in _QUALIFICATIFS:
            continue
        if mot in ("hache", "hachee"):
            if any(v in garde for v in _VIANDES):
                garde.append("hache")
            continue
        garde.append(mot)
    resultat = " ".join(garde) or " ".join(mots)
    # "crème fraîche" is a product on its own: we put "fraiche" back if the name starts with crème.
    if resultat == "creme" and "fraiche" in mots:
        resultat = "creme fraiche"
    return EQUIVALENCES.get(resultat, resultat)
