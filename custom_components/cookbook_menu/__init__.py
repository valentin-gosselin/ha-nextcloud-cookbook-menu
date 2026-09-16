"""Intégration Cookbook Menu : menu de la semaine et liste de courses depuis Nextcloud Cookbook."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import CookbookClient
from .assist import async_enregistrer_phrases
from .const import DOMAIN
from .coordinator import CookbookCoordinator
from .frontend import async_enregistrer_carte
from .planner import Planificateur
from .services import async_setup_services
from .store import StockagePlanificateur
from .sync import Synchroniseur
from .websocket import async_enregistrer_commandes

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.NUMBER, Platform.SELECT, Platform.TODO]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class CookbookMenuData:
    """Objets partagés par les plateformes d'une entrée."""

    client: CookbookClient
    coordinator: CookbookCoordinator
    planner: Planificateur
    sync: Synchroniseur


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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Enregistre les actions et les phrases vocales du domaine."""
    async_setup_services(hass)
    async_enregistrer_phrases(hass)
    async_enregistrer_commandes(hass)
    await async_enregistrer_carte(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Met en place une entrée : premier chargement des recettes (test-before-setup)."""
    client = create_client(hass, dict(entry.data))
    coordinator = CookbookCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.async_close()
        raise
    stockage = StockagePlanificateur(hass, entry.entry_id)
    await stockage.async_charger()
    planificateur = Planificateur(hass, coordinator, stockage)
    entry.runtime_data = CookbookMenuData(
        client=client, coordinator=coordinator, planner=planificateur, sync=Synchroniseur(hass, planificateur)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.runtime_data.sync.async_demarrer()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Décharge une entrée et ferme sa session HTTP."""
    entry.runtime_data.sync.async_arreter()
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):  # pragma: no cover
        return False
    await entry.runtime_data.client.async_close()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> None:
    """Suppression de l'intégration : on efface aussi le menu stocké."""
    await StockagePlanificateur(hass, entry.entry_id).async_supprimer()
