"""Tests du flux de configuration et des options."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cookbook_menu.api import (
    CookbookAuthError,
    CookbookConnectionError,
    CookbookNotFoundError,
)
from custom_components.cookbook_menu.const import DOMAIN

from .conftest import DONNEES_ENTREE


async def test_ajout_reussi(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_URL: "cloud.exemple.fr/",
            CONF_USERNAME: "valentin",
            CONF_PASSWORD: "secret",
            CONF_VERIFY_SSL: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "valentin @ cloud.exemple.fr"
    assert result["data"][CONF_URL] == "https://cloud.exemple.fr"
    assert result["result"].unique_id == "https://cloud.exemple.fr|valentin"


@pytest.mark.parametrize(
    ("exception", "erreur"),
    [
        (CookbookAuthError, "invalid_auth"),
        (CookbookNotFoundError, "cookbook_not_found"),
        (CookbookConnectionError, "cannot_connect"),
        (RuntimeError, "unknown"),
    ],
)
async def test_ajout_erreurs_puis_reussite(hass, mock_client, exception, erreur) -> None:
    mock_client.async_get_categories.side_effect = exception
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(DONNEES_ENTREE))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": erreur}

    mock_client.async_get_categories.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(DONNEES_ENTREE))
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_ajout_deja_configure(hass, mock_client, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(DONNEES_ENTREE))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_client.async_get_categories.side_effect = CookbookAuthError
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "encore faux"})
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.async_get_categories.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "nouveau"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "nouveau"
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_reconfigure(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**DONNEES_ENTREE, CONF_URL: "https://nouveau.exemple.fr", CONF_PASSWORD: "p"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_URL] == "https://nouveau.exemple.fr"
    assert config_entry.unique_id == "https://nouveau.exemple.fr|valentin"
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_reconfigure_vers_compte_existant(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    autre = MockConfigEntry(domain=DOMAIN, unique_id="https://autre.fr|alice", data={**DONNEES_ENTREE})
    autre.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**DONNEES_ENTREE, CONF_URL: "https://autre.fr", CONF_USERNAME: "alice"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_erreur(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    mock_client.async_get_categories.side_effect = CookbookConnectionError
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(DONNEES_ENTREE))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    selecteur = next(v for k, v in schema.items() if k == "excluded_categories")
    assert "Dessert" in selecteur.config["options"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"servings": 4.0, "excluded_categories": ["Dessert"], "scan_interval_minutes": 60.0},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options == {
        "servings": 4,
        "excluded_categories": ["Dessert"],
        "scan_interval_minutes": 60,
    }
    index = config_entry.runtime_data.coordinator.data
    assert all(r.category != "Dessert" for r in index.recipes.values())
    assert config_entry.runtime_data.coordinator.update_interval.total_seconds() == 3600


async def test_options_categories_indisponibles(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    mock_client.async_get_categories.side_effect = CookbookConnectionError
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    selecteur = next(v for k, v in result["data_schema"].schema.items() if k == "excluded_categories")
    assert selecteur.config["options"] == ["Produits Ménagers"]
