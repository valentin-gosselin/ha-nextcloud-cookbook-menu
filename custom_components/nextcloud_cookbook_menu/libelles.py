"""Labels written into lists (outside HA translations, which don't cover list item content)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

_LIBELLES = {
    "fr": {
        "couverts": "{n} couverts",
        "un_couvert": "1 couvert",
        "sans_recette": "sans recette",
        "introuvable": "recette introuvable",
        "pour": "{recette} pour {n}",
        "placard_epuise": "manque au placard",
        "au_frigo": "déjà au frigo : {quantite}",
        "recurrent": "à racheter toutes les {n} semaines",
        "recurrent_semaine": "à racheter chaque semaine",
    },
    "en": {
        "couverts": "{n} servings",
        "un_couvert": "1 serving",
        "sans_recette": "no recipe",
        "introuvable": "recipe not found",
        "pour": "{recette} for {n}",
        "placard_epuise": "missing from the pantry",
        "au_frigo": "already in the fridge: {quantite}",
        "recurrent": "to buy again every {n} weeks",
        "recurrent_semaine": "to buy again every week",
    },
}


def libelles(hass: HomeAssistant) -> dict[str, str]:
    """Labels in the instance's language (French, otherwise English)."""
    return _LIBELLES["fr" if hass.config.language.startswith("fr") else "en"]
