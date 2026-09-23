"""Recipe sheet: enriched data, websocket command and photo (story 2.8)."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator, WebSocketGenerator
from yarl import URL

from custom_components.nextcloud_cookbook_menu.api import CookbookConnectionError, parse_recipe
from custom_components.nextcloud_cookbook_menu.fiche import (
    VueImageRecette,
    etapes_structurees,
    ingredients_structures,
)


def test_parse_recipe_enrichie() -> None:
    recette = parse_recipe(
        {
            "id": 1,
            "name": "Couscous",
            "description": "  Le vrai  ",
            "recipeInstructions": ["Couper.", {"@type": "HowToStep", "text": "Cuire 25 mn."}, "", 3],
            "tool": "autocuiseur",
            "prepTime": "PT0H30M0S",
            "cookTime": "PT1H30M",
            "totalTime": "PT0H0M0S",
        }
    )
    assert recette.description == "Le vrai"
    assert recette.instructions == ("Couper.", "Cuire 25 mn.")
    assert recette.tools == ("autocuiseur",)
    assert (recette.prep_minutes, recette.cook_minutes, recette.total_minutes) == (30, 90, None)
    assert parse_recipe({"id": 1, "name": "x", "prepTime": "n'importe quoi", "tool": 3}).prep_minutes is None


def test_ingredients_et_etapes_structures() -> None:
    recette = parse_recipe(
        {
            "id": 1,
            "name": "César",
            "recipeIngredient": ["Pour la sauce", "0,5 Citron(s)", "sel, poivre", "un peu de lait", ""],
            "recipeInstructions": ["Mariner 4 heures au frigo."],
        }
    )
    lignes = ingredients_structures(recette)
    assert lignes[0] == {"section": "Pour la sauce"}
    assert lignes[1]["name"] == "Citron" and lignes[1]["quantity"] == 0.5
    assert [ligne["name"] for ligne in lignes[2:4]] == ["Sel", "Poivre"]
    assert lignes[4]["vague"] == "un peu"
    [etape] = etapes_structurees(recette)
    assert etape["timers"] == [{"text": "4 heures", "start": 8, "end": 16, "seconds": 14400}]


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry, recettes):
    carry = recettes["2176038"]
    recettes["2176038"] = carry.__class__(
        **{
            **{f: getattr(carry, f) for f in carry.__slots__},
            "instructions": ("Faire revenir.", "Cuire 1 h à feu doux."),
            "prep_minutes": 30,
            "url": "https://exemple.fr/carry",
        }
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def test_fiche_par_plat_du_menu(hass: HomeAssistant, entree, hass_ws_client: WebSocketGenerator) -> None:
    plat = entree.runtime_data.planner.async_ajouter_plat("carry", couverts=4).plat
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/recipe", "uid": plat.uid})
    reponse = await client.receive_json()
    assert reponse["success"], reponse
    fiche = reponse["result"]
    assert fiche["name"] == "Carry de poulet"
    assert (fiche["yield"], fiche["servings"], fiche["prep_minutes"]) == (6, 4, 30)
    assert fiche["steps"][1]["timers"][0]["seconds"] == 3600
    assert fiche["cookbook_url"] == "https://cloud.exemple.fr/apps/cookbook/#/recipe/2176038"
    assert fiche["url"] == "https://exemple.fr/carry"
    assert fiche["image"].startswith(f"/api/nextcloud_cookbook_menu/image/{entree.entry_id}/2176038?authSig=")

    await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/recipe", "recipe_id": "2176038"})
    assert (await client.receive_json())["result"]["servings"] == 2

    libre = entree.runtime_data.planner.async_ajouter_plat("restes").plat
    for message in (
        {"uid": libre.uid},
        {"uid": "inconnu"},
        {"recipe_id": "000"},
        {"config_entry_id": "x", "uid": "y"},
    ):
        await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/recipe", **message})
        erreur = await client.receive_json()
        assert not erreur["success"]
        assert erreur["error"]["code"] == "not_found"


async def test_vue_image(hass: HomeAssistant, entree, mock_client, hass_client: ClientSessionGenerator) -> None:
    assert await async_setup_component(hass, "http", {})
    hass.http.register_view(VueImageRecette())
    client = await hass_client()
    url = f"/api/nextcloud_cookbook_menu/image/{entree.entry_id}/2176038"

    mock_client.async_get_image = AsyncMock(return_value=(b"JPEG", "image/jpeg"))
    reponse = await client.get(url)
    assert reponse.status == HTTPStatus.OK
    assert await reponse.read() == b"JPEG"

    # Thumbnail: the size is passed to Nextcloud, unknown sizes are rejected.
    reponse = await client.get(f"{url}/thumb")
    assert reponse.status == HTTPStatus.OK
    assert mock_client.async_get_image.call_args[0][1] == "thumb"
    assert (await client.get(f"{url}/enorme")).status == HTTPStatus.BAD_REQUEST

    mock_client.async_get_image.return_value = None
    assert (await client.get(url)).status == HTTPStatus.NOT_FOUND
    mock_client.async_get_image.side_effect = CookbookConnectionError("coupure")
    assert (await client.get(url)).status == HTTPStatus.BAD_GATEWAY
    assert (await client.get("/api/nextcloud_cookbook_menu/image/inconnue/1")).status == HTTPStatus.NOT_FOUND
    assert URL(url).path.startswith("/api/")
