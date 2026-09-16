"""Tests du flux de configuration et des options."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

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
    DemandeConnexion,
    IdentifiantsNextcloud,
)
from custom_components.cookbook_menu.const import DOMAIN

from .conftest import DONNEES_ENTREE


async def demarrer(hass: HomeAssistant, url: str = "cloud.exemple.fr/") -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: url, CONF_VERIFY_SSL: True}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["login", "manual"]
    return result


async def test_ajout_manuel_reussi(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    result = await demarrer(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "manual"})
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "valentin", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "valentin @ cloud.exemple.fr"
    assert result["data"] == {
        CONF_URL: "https://cloud.exemple.fr",
        CONF_USERNAME: "valentin",
        CONF_PASSWORD: "secret",
        CONF_VERIFY_SSL: True,
    }
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
async def test_ajout_manuel_erreurs_puis_reussite(hass, mock_client, exception, erreur) -> None:
    mock_client.async_get_categories.side_effect = exception
    result = await demarrer(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "manual"})
    identifiants = {CONF_USERNAME: "valentin", CONF_PASSWORD: "faux"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], identifiants)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": erreur}

    mock_client.async_get_categories.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], identifiants)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_ajout_deja_configure(hass, mock_client, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await demarrer(hass, "https://cloud.exemple.fr")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "manual"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "valentin", CONF_PASSWORD: "x"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


IDENTIFIANTS = IdentifiantsNextcloud(
    url="https://cloud.exemple.fr/", utilisateur="valentin", mot_de_passe="genere"
)
DEMANDE = DemandeConnexion(
    url_connexion="https://cloud.exemple.fr/login/v2/flow/abc",
    url_poll="https://cloud.exemple.fr/login/v2/poll",
    jeton="jeton",
)


async def suivre_connexion(hass: HomeAssistant, result: dict, identifiants, erreur_demarrage=None) -> dict:
    """Choisit « Se connecter avec Nextcloud » et simule l'accès accordé dans le navigateur."""
    with (
        patch(
            "custom_components.cookbook_menu.config_flow.async_demarrer_connexion",
            side_effect=erreur_demarrage,
            return_value=DEMANDE,
        ),
        patch(
            "custom_components.cookbook_menu.config_flow.async_attendre_connexion", return_value=identifiants
        ),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "login"})
        if result["type"] is not FlowResultType.EXTERNAL_STEP:
            return result
        assert result["url"] == DEMANDE.url_connexion
        await hass.async_block_till_done()
        # Le frontend reprend le flux quand l'étape externe est terminée.
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        await hass.async_block_till_done()
    return result


async def test_connexion_nextcloud_reussie(hass: HomeAssistant, mock_client) -> None:
    result = await demarrer(hass)
    result = await suivre_connexion(hass, result, IDENTIFIANTS)
    [entree] = hass.config_entries.async_entries(DOMAIN)
    assert entree.data == {
        CONF_URL: "https://cloud.exemple.fr",
        CONF_USERNAME: "valentin",
        CONF_PASSWORD: "genere",
        CONF_VERIFY_SSL: True,
    }
    assert entree.unique_id == "https://cloud.exemple.fr|valentin"


async def test_connexion_nextcloud_expiree(hass: HomeAssistant, mock_client) -> None:
    result = await demarrer(hass)
    result = await suivre_connexion(hass, result, None)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "login_timeout"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_connexion_nextcloud_identifiants_refuses(hass: HomeAssistant, mock_client) -> None:
    mock_client.async_get_categories.side_effect = CookbookNotFoundError
    result = await demarrer(hass)
    result = await suivre_connexion(hass, result, IDENTIFIANTS)
    assert result["reason"] == "cookbook_not_found"
    assert hass.config_entries.async_entries(DOMAIN) == []


@pytest.mark.parametrize(
    ("exception", "raison"),
    [(CookbookNotFoundError, "login_flow_unavailable"), (CookbookConnectionError, "cannot_connect")],
)
async def test_connexion_nextcloud_indisponible(hass: HomeAssistant, mock_client, exception, raison) -> None:
    result = await demarrer(hass)
    result = await suivre_connexion(hass, result, IDENTIFIANTS, erreur_demarrage=exception)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == raison


async def test_abandon_arrete_l_attente(hass: HomeAssistant, mock_client) -> None:
    result = await demarrer(hass)
    attente = asyncio.Event()

    async def attendre_indefiniment(*_args, **_kwargs):
        await attente.wait()

    with (
        patch("custom_components.cookbook_menu.config_flow.async_demarrer_connexion", return_value=DEMANDE),
        patch(
            "custom_components.cookbook_menu.config_flow.async_attendre_connexion",
            side_effect=attendre_indefiniment,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "login"})
        assert result["type"] is FlowResultType.EXTERNAL_STEP
        hass.config_entries.flow.async_abort(result["flow_id"])
        await hass.async_block_till_done()
    assert hass.config_entries.flow.async_progress() == []


async def test_reauth_par_connexion_nextcloud(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "reauth_confirm"
    await suivre_connexion(hass, result, IDENTIFIANTS)
    assert config_entry.data[CONF_PASSWORD] == "genere"
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(config_entry.entry_id)


async def test_reauth_avec_un_autre_compte(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    autre = IdentifiantsNextcloud(url="https://cloud.exemple.fr", utilisateur="alice", mot_de_passe="x")
    result = await suivre_connexion(hass, result, autre)
    assert result["reason"] == "wrong_account"
    assert config_entry.data[CONF_PASSWORD] == "mot-de-passe-application"


async def test_reauth_manuelle(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reauth_manual"}
    )
    assert result["step_id"] == "reauth_manual"

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
        {
            "servings": 4.0,
            "excluded_categories": ["Dessert"],
            "pantry": ["Sel", "Harissa"],
            "pantry_reminder": False,
            "history_months": 12.0,
            "scan_interval_minutes": 60.0,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert dict(config_entry.options) == {
        "servings": 4,
        "excluded_categories": ["Dessert"],
        "pantry": ["Sel", "Harissa"],
        "pantry_reminder": False,
        "history_months": 12,
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
