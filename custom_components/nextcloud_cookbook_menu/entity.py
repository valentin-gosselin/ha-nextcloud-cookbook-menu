"""Common base for control entities (recipe selection, day, servings, button)."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from . import CookbookMenuConfigEntry
from .const import DOMAIN
from .planner import Planificateur


def info_appareil(entry: CookbookMenuConfigEntry) -> DeviceInfo:
    """Service device shared by all entities of a config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        entry_type=DeviceEntryType.SERVICE,
        manufacturer="Nextcloud",
        model="Cookbook",
    )


class CookbookMenuControle(Entity):
    """Entity tied to the planner: translated name, shared device, updates on change."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: CookbookMenuConfigEntry, cle: str) -> None:
        self.planificateur: Planificateur = entry.runtime_data.planner
        self._attr_translation_key = cle
        self._attr_unique_id = f"{entry.entry_id}_{cle}"
        self._attr_device_info = info_appareil(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.planificateur.async_ecouter(self._async_rafraichir))
        self.async_on_remove(self.planificateur.coordinateur.async_add_listener(self._async_rafraichir))

    @property
    def available(self) -> bool:
        return self.planificateur.coordinateur.last_update_success

    @callback
    def _async_rafraichir(self) -> None:
        self.async_write_ha_state()
