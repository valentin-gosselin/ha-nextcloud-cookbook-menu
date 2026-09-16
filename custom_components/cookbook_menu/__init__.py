"""Intégration Cookbook Menu : menu de la semaine et liste de courses depuis Nextcloud Cookbook."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

type CookbookMenuConfigEntry = ConfigEntry[None]


async def async_setup_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Met en place une entrée de configuration."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> bool:
    """Décharge une entrée de configuration."""
    return True
