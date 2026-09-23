"""'Add to menu' button."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import CookbookMenuConfigEntry
from .entity import CookbookMenuControle

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: CookbookMenuConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([AjouterButton(entry)])


class AjouterButton(CookbookMenuControle, ButtonEntity):
    """Adds the selected recipe, day, and servings to the menu."""

    def __init__(self, entry: CookbookMenuConfigEntry) -> None:
        super().__init__(entry, "add_to_menu")

    async def async_press(self) -> None:
        self.planificateur.async_ajouter_selection(dt_util.now().date())
