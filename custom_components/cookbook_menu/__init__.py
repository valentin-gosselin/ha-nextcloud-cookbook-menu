"""Intégration Cookbook Menu : menu de la semaine et liste de courses depuis Nextcloud Cookbook."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import CookbookClient
from .coordinator import CookbookCoordinator


@dataclass(slots=True)
class CookbookMenuData:
    """Objets partagés par les plateformes d'une entrée."""

    client: CookbookClient
    coordinator: CookbookCoordinator


type CookbookMenuConfigEntry = ConfigEntry[CookbookMenuData]


def create_client(hass: HomeAssistant, data: dict) -> CookbookClient:
    """Construit le client à partir des données d'une entrée ou d'un formulaire.

    Session dédiée et SANS cookies : Nextcloud pose un cookie de session qui, dans une
    session partagée, continuerait d'authentifier les requêtes même après révocation du
    mot de passe d'application (réauthentification jamais déclenchée).
    """
    return CookbookClient(
        async_create_clientsession(
            hass, verify_ssl=data.get(CONF_VERIFY_SSL, True), cookie_jar=aiohttp.DummyCookieJar()
        ),
        data[CONF_URL],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )


async def async_setup_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Met en place une entrée : premier chargement des recettes (test-before-setup)."""
    client = create_client(hass, dict(entry.data))
    coordinator = CookbookCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.async_close()
        raise
    entry.runtime_data = CookbookMenuData(client=client, coordinator=coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Décharge une entrée et ferme sa session HTTP."""
    await entry.runtime_data.client.async_close()
    return True
