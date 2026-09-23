"""Nextcloud Cookbook Menu integration: weekly menu and shopping list from Nextcloud Cookbook."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .api import CookbookClient
from .assist import async_enregistrer_phrases
from .const import CONF_TIMERS_COUNT, DEFAULT_TIMERS_COUNT, DOMAIN
from .coordinator import CookbookCoordinator
from .frontend import async_enregistrer_carte
from .minuteurs import GestionnaireMinuteurs
from .planner import Planificateur
from .services import async_setup_services
from .store import StockagePlanificateur
from .sync import Synchroniseur
from .websocket import async_enregistrer_commandes

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.TODO,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class CookbookMenuData:
    """Objects shared by an entry's platforms."""

    client: CookbookClient
    coordinator: CookbookCoordinator
    planner: Planificateur
    sync: Synchroniseur
    timers: GestionnaireMinuteurs


type CookbookMenuConfigEntry = ConfigEntry[CookbookMenuData]


def create_client(hass: HomeAssistant, data: dict) -> CookbookClient:
    """Build the client from a config entry's or a form's data.

    Dedicated session with NO cookies: Nextcloud sets a session cookie that, in a shared
    session, would keep authenticating requests even after the application password is
    revoked (reauthentication would never be triggered).
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
    """Register the domain's services and voice phrases."""
    async_setup_services(hass)
    async_enregistrer_phrases(hass)
    async_enregistrer_commandes(hass)
    if getattr(hass, "http", None) is not None:
        from .fiche import VueImageRecette

        hass.http.register_view(VueImageRecette())
    await async_enregistrer_carte(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Set up a config entry: first load of the recipes (test-before-setup)."""
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
        client=client,
        coordinator=coordinator,
        planner=planificateur,
        sync=Synchroniseur(hass, planificateur),
        timers=GestionnaireMinuteurs(hass, int(entry.options.get(CONF_TIMERS_COUNT, DEFAULT_TIMERS_COUNT))),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.runtime_data.sync.async_demarrer()

    # Every night: yesterday's dish portions are removed from the fridge, forgotten expired
    # products are dropped, and recurring products are put back on the shopping list. Without
    # @callback, Home Assistant would run this in a separate thread, while the planner touches
    # HA state.
    @callback
    def _chaque_nuit(_maintenant: datetime) -> None:
        planificateur.async_consommer()

    planificateur.async_consommer()
    entry.async_on_unload(async_track_time_change(hass, _chaque_nuit, hour=0, minute=1, second=0))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Unload a config entry, stop its timers, and close its HTTP session."""
    entry.runtime_data.timers.async_tout_arreter()
    entry.runtime_data.sync.async_arreter()
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):  # pragma: no cover
        return False
    await entry.runtime_data.client.async_close()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> None:
    """Remove the integration: also erase the stored menu."""
    await StockagePlanificateur(hass, entry.entry_id).async_supprimer()
