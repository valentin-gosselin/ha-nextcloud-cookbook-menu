"""Tests du client HTTP Cookbook (réponses simulées)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nextcloud_cookbook_menu.api import (
    API_PREFIX,
    CookbookAuthError,
    CookbookClient,
    CookbookConnectionError,
    CookbookNotFoundError,
    DemandeConnexion,
    IdentifiantsNextcloud,
    Recipe,
    RecipeStub,
    async_attendre_connexion,
    async_demarrer_connexion,
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


async def test_login_flow_v2(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    session = async_get_clientsession(hass)
    aioclient_mock.post(
        f"{BASE}/index.php/login/v2",
        json={
            "poll": {"token": "jeton", "endpoint": f"{BASE}/login/v2/poll"},
            "login": f"{BASE}/login/v2/flow/x",
        },
    )
    demande = await async_demarrer_connexion(session, f"{BASE}/")
    assert demande == DemandeConnexion(f"{BASE}/login/v2/flow/x", f"{BASE}/login/v2/poll", "jeton")
    assert aioclient_mock.mock_calls[0][3]["User-Agent"] == "Nextcloud Cookbook Menu (Home Assistant)"

    aioclient_mock.post(
        f"{BASE}/login/v2/poll",
        json={"server": f"{BASE}/", "loginName": "valentin", "appPassword": "genere"},
    )
    with patch("custom_components.nextcloud_cookbook_menu.api.asyncio.sleep"):
        identifiants = await async_attendre_connexion(session, demande, intervalle=0)
    assert identifiants == IdentifiantsNextcloud(BASE, "valentin", "genere")


async def test_login_flow_v2_attente_puis_expiration(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    session = async_get_clientsession(hass)
    demande = DemandeConnexion("x", f"{BASE}/login/v2/poll", "jeton")
    aioclient_mock.post(f"{BASE}/login/v2/poll", status=404)
    assert await async_attendre_connexion(session, demande, intervalle=0.01, duree_max=0.05) is None
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/login/v2/poll", exc=aiohttp.ClientError())
    assert await async_attendre_connexion(session, demande, intervalle=0.01, duree_max=0.02) is None


@pytest.mark.parametrize(
    ("reponse", "exception"),
    [
        ({"status": 404}, CookbookNotFoundError),
        ({"status": 500}, CookbookConnectionError),
        ({"exc": aiohttp.ClientError()}, CookbookConnectionError),
        ({"json": {"inattendu": 1}}, CookbookConnectionError),
    ],
)
async def test_login_flow_v2_erreurs(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, reponse, exception
) -> None:
    aioclient_mock.post(f"{BASE}/index.php/login/v2", **reponse)
    with pytest.raises(exception):
        await async_demarrer_connexion(async_get_clientsession(hass), BASE)


async def test_image(client, aioclient_mock) -> None:
    url = f"{BASE}{API_PREFIX}/recipes/7/image"
    aioclient_mock.get(url, content=b"JPEG", headers={"Content-Type": "image/jpeg"})
    assert await client.async_get_image("7") == (b"JPEG", "image/jpeg")

    aioclient_mock.clear_requests()
    aioclient_mock.get(url, text="pas une image", headers={"Content-Type": "text/html"})
    assert await client.async_get_image("7") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(url, status=404)
    assert await client.async_get_image("7") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(url, status=401)
    with pytest.raises(CookbookAuthError):
        await client.async_get_image("7")

    aioclient_mock.clear_requests()
    aioclient_mock.get(url, exc=aiohttp.ClientError())
    with pytest.raises(CookbookConnectionError):
        await client.async_get_image("7")
