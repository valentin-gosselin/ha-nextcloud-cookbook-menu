"""Recipe card data: parsed ingredients, steps with timers, photo served by HA."""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus
from typing import Any, ClassVar

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from .api import CookbookError, Recipe
from .const import DOMAIN
from .ingredients.minuteurs import trouver_minuteurs
from .ingredients.parser import analyser

URL_IMAGE = "/api/nextcloud_cookbook_menu/image/{entry_id}/{recipe_id}"
URL_IMAGE_TAILLE = f"{URL_IMAGE}/{{taille}}"
VALIDITE_IMAGE = timedelta(hours=24)
# Sizes served by Nextcloud's Cookbook app.
TAILLES = ("full", "thumb", "thumb16")


def image_signee(hass: HomeAssistant, entry_id: str, recipe_id: str, taille: str = "full") -> str:
    """Photo URL, signed by Home Assistant for 24 hours (Nextcloud requires credentials)."""
    chemin = (
        URL_IMAGE.format(entry_id=entry_id, recipe_id=recipe_id)
        if taille == "full"
        else URL_IMAGE_TAILLE.format(entry_id=entry_id, recipe_id=recipe_id, taille=taille)
    )
    return async_sign_path(hass, chemin, VALIDITE_IMAGE)


def ingredients_structures(recette: Recipe) -> list[dict[str, Any]]:
    """Parsed ingredient lines, which the card rescales to the chosen headcount."""
    lignes: list[dict[str, Any]] = []
    for brut in recette.ingredients:
        analyses = analyser(brut)
        if not analyses:
            continue
        if len(analyses) == 1 and analyses[0].section:
            lignes.append({"section": analyses[0].nom})
            continue
        for ingredient in analyses:
            lignes.append(
                {
                    "raw": brut,
                    "name": ingredient.nom,
                    "quantity": ingredient.quantite,
                    "quantity_max": ingredient.quantite_max,
                    "unit": ingredient.unite,
                    "note": ingredient.note,
                    "vague": ingredient.vague,
                    "optional": ingredient.facultatif,
                }
            )
    return lignes


def etapes_structurees(recette: Recipe) -> list[dict[str, Any]]:
    """Steps with the position of detected durations (to turn them into timer buttons)."""
    return [
        {
            "text": etape,
            "timers": [
                {"text": m.texte, "start": m.debut, "end": m.fin, "seconds": m.secondes}
                for m in trouver_minuteurs(etape)
            ],
        }
        for etape in recette.instructions
    ]


def fiche(hass: HomeAssistant, entry_id: str, recette: Recipe, couverts: int) -> dict[str, Any]:
    """Everything the recipe window displays."""
    entree = hass.config_entries.async_get_entry(entry_id)
    nextcloud = entree.data[CONF_URL].rstrip("/") if entree else ""
    return {
        "id": recette.id,
        "name": recette.name,
        "description": recette.description,
        "category": recette.category,
        "url": recette.url,
        "cookbook_url": f"{nextcloud}/apps/cookbook/#/recipe/{recette.id}" if nextcloud else None,
        "yield": recette.servings,
        "servings": couverts,
        "prep_minutes": recette.prep_minutes,
        "cook_minutes": recette.cook_minutes,
        "total_minutes": recette.total_minutes,
        "tools": list(recette.tools),
        "ingredients": ingredients_structures(recette),
        "steps": etapes_structurees(recette),
        "image": image_signee(hass, entry_id, recette.id),
    }


class VueImageRecette(HomeAssistantView):
    """Recipe photo relayed from Nextcloud (accessing Nextcloud requires credentials)."""

    url = URL_IMAGE
    extra_urls: ClassVar[list[str]] = [URL_IMAGE_TAILLE]
    name = "api:nextcloud_cookbook_menu:image"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, recipe_id: str, taille: str = "full") -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entree = hass.config_entries.async_get_entry(entry_id)
        if entree is None or entree.domain != DOMAIN or not hasattr(entree, "runtime_data"):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        if taille not in TAILLES:
            return web.Response(status=HTTPStatus.BAD_REQUEST)
        try:
            image = await entree.runtime_data.client.async_get_image(recipe_id, taille)
        except CookbookError:
            return web.Response(status=HTTPStatus.BAD_GATEWAY)
        if image is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        contenu, type_mime = image
        return web.Response(body=contenu, content_type=type_mime, headers={"Cache-Control": "private, max-age=3600"})
