"""Clé de fusion d'un nom d'ingrédient : deux lignes de même clé désignent le même produit à acheter."""

from __future__ import annotations

import re
import unicodedata

# Mots vides retirés de la clé.
_MOTS_VIDES = {"de", "d", "du", "des", "la", "le", "les", "l", "a", "au", "aux", "en", "et", "un", "une"}

# Qualificatifs qui ne changent pas le produit acheté (préparation, taille, maturité).
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

# « haché » ne change pas le produit, sauf pour la viande (steak haché, boeuf haché).
_VIANDES = {"boeuf", "porc", "veau", "viande", "poulet", "agneau", "dinde", "volaille"}

# Mots invariables qui se terminent par s ou x au singulier.
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

# Équivalences de clés (après normalisation), pour les produits écrits de plusieurs façons.
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
}


def sans_accents(texte: str) -> str:
    """Minuscules, sans accents, ligatures dépliées."""
    texte = texte.casefold().replace("œ", "oe").replace("æ", "ae")
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def singulier(mot: str) -> str:
    """Singulier approximatif d'un mot français (sans accents)."""
    if len(mot) <= 3 or mot in _INVARIABLES:
        return mot
    if mot.endswith(("eaux", "eux", "oux")):
        return mot[:-1]
    if mot.endswith("aux"):
        return mot[:-3] + "al"
    # Les mots en -is, -us, -os, -as sont presque toujours invariables (radis, couscous, anchois).
    if mot.endswith("s") and not mot.endswith(("ss", "is", "us", "os", "as")):
        return mot[:-1]
    return mot


def cle(nom: str) -> str:
    """Clé de fusion d'un nom d'ingrédient."""
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
    # « crème fraîche » est un produit : on remet « fraiche » si le nom commence par crème.
    if resultat == "creme" and "fraiche" in mots:
        resultat = "creme fraiche"
    return EQUIVALENCES.get(resultat, resultat)
