"""Tests du client HTTP Cookbook (réponses simulées)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.cookbook_menu.api import (
    API_PREFIX,
    CookbookAuthError,
    CookbookClient,
    CookbookConnectionError,
    CookbookNotFoundError,
    Recipe,
    RecipeStub,
    parse_recipe,
)

BASE = "https://cloud.exemple.fr"


@pytest.fixture
async def client(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> CookbookClient:
    # aioclient_mock doit être actif avant la création de la session.
    return CookbookClient(async_get_clientsession(hass), f"{BASE}/", "valentin", "secret")


async def test_fermeture() -> None:
    session = AsyncMock()
    await CookbookClient(session, BASE, "u", "p").async_close()
    session.close.assert_awaited_once()


async def test_categories(client: CookbookClient, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(
        f"{BASE}{API_PREFIX}/categories",
        json=[{"name": "Dessert", "recipe_count": 3}, {"name": "*", "recipe_count": 1}, {"name": "apéritif"}],
    )
    assert await client.async_get_categories() == ["apéritif", "Dessert"]
    en_tetes = aioclient_mock.mock_calls[0][3]
    assert en_tetes["Accept"] == "application/json"
    assert en_tetes["Authorization"] == "Basic dmFsZW50aW46c2VjcmV0"


@pytest.mark.parametrize(
    ("statut", "exception"),
    [
        (401, CookbookAuthError),
        (403, CookbookAuthError),
        (404, CookbookNotFoundError),
        (500, CookbookConnectionError),
    ],
)
async def test_erreurs_http(client, aioclient_mock, statut, exception) -> None:
    aioclient_mock.get(f"{BASE}{API_PREFIX}/categories", status=statut)
    with pytest.raises(exception):
        await client.async_get_categories()


async def test_erreur_reseau(client, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}{API_PREFIX}/recipes", exc=aiohttp.ClientError())
    with pytest.raises(CookbookConnectionError):
        await client.async_get_recipe_stubs()


async def test_reponse_non_json(client, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE}{API_PREFIX}/recipes", text="<html>maintenance</html>")
    with pytest.raises(CookbookConnectionError):
        await client.async_get_recipe_stubs()


@pytest.mark.parametrize("chemin", ["/recipes", "/categories"])
async def test_format_inattendu(client, aioclient_mock, chemin) -> None:
    aioclient_mock.get(f"{BASE}{API_PREFIX}{chemin}", json={"inattendu": True})
    with pytest.raises(CookbookConnectionError):
        if chemin == "/recipes":
            await client.async_get_recipe_stubs()
        else:
            await client.async_get_categories()


async def test_stubs(client, aioclient_mock) -> None:
    aioclient_mock.get(
        f"{BASE}{API_PREFIX}/recipes",
        json=[
            {"recipe_id": 12, "name": " Couscous ", "dateModified": "2023-07-27T17:55:59+0000"},
            {"id": "13", "name": "Taboulé", "dateModified": None},
            {"name": "sans identifiant"},
        ],
    )
    stubs = await client.async_get_recipe_stubs()
    assert [s.id for s in stubs] == ["12", "13"]
    assert stubs[0].name == "Couscous"
    assert stubs[0].date_modified == datetime.fromisoformat("2023-07-27T17:55:59+00:00")
    assert stubs[1].date_modified is None


async def test_recette_et_cache(client, aioclient_mock) -> None:
    aioclient_mock.get(
        f"{BASE}{API_PREFIX}/recipes/1",
        json={"id": "1", "name": "Carry", "recipeYield": 6, "recipeIngredient": ["1 kg de poulet"]},
    )
    aioclient_mock.get(f"{BASE}{API_PREFIX}/recipes/3", status=404)
    aioclient_mock.get(f"{BASE}{API_PREFIX}/recipes/4", json=["pas", "un", "objet"])
    date = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    en_cache = Recipe(id="2", name="Taboulé", category=None, servings=4, ingredients=(), date_modified=date)
    stubs = [
        RecipeStub("1", "Carry", None),
        RecipeStub("2", "Taboulé", date),
        RecipeStub("3", "Supprimée entre-temps", None),
    ]
    resultat = await client.async_get_recipes(stubs, 2, {"2": en_cache})
    assert set(resultat) == {"1", "2"}
    assert resultat["2"] is en_cache
    assert resultat["1"].servings == 6
    assert aioclient_mock.call_count == 2

    with pytest.raises(CookbookConnectionError):
        await client.async_get_recipe("4")


@pytest.mark.parametrize(
    ("rendement", "attendu"),
    [(4, 4), (0, 1), ("6 personnes", 6), ("", 1), (None, 1), (True, 1), (2.0, 2)],
)
def test_parse_recipe_rendement(rendement, attendu) -> None:
    assert parse_recipe({"id": 1, "name": "x", "recipeYield": rendement}).servings == attendu


def test_parse_recipe_champs() -> None:
    recette = parse_recipe(
        {
            "id": 7,
            "name": "  Couscous ",
            "recipeCategory": " Plats principaux ",
            "recipeIngredient": ["12 merguez", 3, None],
            "keywords": "merguez, harissa,merguez,,",
            "dateModified": "pas une date",
            "url": "",
        }
    )
    assert recette.id == "7"
    assert recette.name == "Couscous"
    assert recette.category == "Plats principaux"
    assert recette.ingredients == ("12 merguez",)
    assert recette.keywords == ("merguez", "harissa")
    assert recette.date_modified is None
    assert recette.url is None
    assert parse_recipe({"id": 1, "name": "x", "recipeCategory": "  "}).category is None
