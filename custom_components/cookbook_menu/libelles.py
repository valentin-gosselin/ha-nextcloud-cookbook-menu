"""Libellés écrits dans les listes (hors traductions HA, qui ne couvrent pas le contenu des éléments)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

_LIBELLES = {
    "fr": {
        "couverts": "{n} couverts",
        "un_couvert": "1 couvert",
        "sans_recette": "sans recette",
        "introuvable": "recette introuvable",
        "pour": "{recette} pour {n}",
        "rappel_placard": "À vérifier au placard : {produits}",
        "rappel_autres": " et {n} autres",
        "placard_epuise": "au placard, signalé épuisé",
    },
    "en": {
        "couverts": "{n} servings",
        "un_couvert": "1 serving",
        "sans_recette": "no recipe",
        "introuvable": "recipe not found",
        "pour": "{recette} for {n}",
        "rappel_placard": "Check the pantry: {produits}",
        "rappel_autres": " and {n} more",
        "placard_epuise": "pantry item marked as out of stock",
    },
}


def libelles(hass: HomeAssistant) -> dict[str, str]:
    """Libellés dans la langue de l'instance (français, sinon anglais)."""
    return _LIBELLES["fr" if hass.config.language.startswith("fr") else "en"]
