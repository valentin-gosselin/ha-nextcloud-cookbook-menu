"""Common test fixtures."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nextcloud_cookbook_menu.api import Recipe, RecipeStub, parse_recipe
from custom_components.nextcloud_cookbook_menu.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"

DONNEES_ENTREE = {
    CONF_URL: "https://cloud.exemple.fr",
    CONF_USERNAME: "valentin",
    CONF_PASSWORD: "mot-de-passe-application",
    CONF_VERIFY_SSL: True,
}


@pytest.fixture(autouse=True)
async def auto_enable_custom_integrations(hass, enable_custom_integrations):
    """Enable custom integrations, and the homeassistant component that conversation depends on."""
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture
def date_figee(freezer) -> None:
    """16/09/2026 at noon: dishes dated the 17th to the 20th remain upcoming, regardless of the actual day."""
    freezer.move_to("2026-09-16 12:00:00+02:00")


@pytest.fixture
def corpus() -> list[dict]:
    """Real recipe corpus (export from 16/09/2026)."""
    return json.loads((FIXTURES / "corpus_recettes.json").read_text(encoding="utf-8"))


@pytest.fixture
def recettes(corpus) -> dict[str, Recipe]:
    """Corpus recipes as `Recipe` objects."""
    return {
        str(r["id"]): parse_recipe(
            {
                "id": r["id"],
                "name": r["name"],
                "recipeCategory": r["category"],
                "recipeYield": r["yield"],
                "recipeIngredient": r["ingredients"],
                "keywords": r["keywords"],
                "dateModified": "2026-09-01T10:00:00+00:00",
            }
        )
        for r in corpus
    }


@pytest.fixture
def mock_client(recettes) -> Generator[AsyncMock]:
    """Mock Cookbook client, wired to the real corpus."""
    with (
        patch("custom_components.nextcloud_cookbook_menu.CookbookClient", autospec=True) as classe,
        patch("custom_components.nextcloud_cookbook_menu.config_flow.create_client") as creer_flux,
    ):
        client = classe.return_value
        client.async_get_categories.return_value = sorted({r.category for r in recettes.values() if r.category})
        client.async_get_recipe_stubs.return_value = [
            RecipeStub(id=r.id, name=r.name, date_modified=r.date_modified) for r in recettes.values()
        ]
        client.async_get_recipes.return_value = recettes
        creer_flux.return_value = client
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Sample config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="valentin @ cloud.exemple.fr",
        unique_id="https://cloud.exemple.fr|valentin",
        data=dict(DONNEES_ENTREE),
        options={"servings": 2, "excluded_categories": ["Produits Ménagers"], "scan_interval_minutes": 30},
    )
