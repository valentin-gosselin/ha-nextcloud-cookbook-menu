"""Dropdown lists: recipe to add and planned day."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CookbookMenuConfigEntry
from .entity import CookbookMenuControle
from .planner import JOURS_SELECTION

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: CookbookMenuConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([RecetteSelect(entry), JourSelect(entry)])


class RecetteSelect(CookbookMenuControle, SelectEntity):
    """All recipes, by name."""

    def __init__(self, entry: CookbookMenuConfigEntry) -> None:
        super().__init__(entry, "recipe")

    @property
    def options(self) -> list[str]:
        return list(self.planificateur.choix_recettes())

    @property
    def current_option(self) -> str | None:
        return self.planificateur.selection.recette

    async def async_select_option(self, option: str) -> None:
        self.planificateur.async_modifier_selection(recette=option)


class JourSelect(CookbookMenuControle, SelectEntity):
    """Planned day for the dish to add (translated labels)."""

    def __init__(self, entry: CookbookMenuConfigEntry) -> None:
        super().__init__(entry, "day")
        self._attr_options = list(JOURS_SELECTION)

    @property
    def current_option(self) -> str:
        return self.planificateur.selection.jour

    async def async_select_option(self, option: str) -> None:
        self.planificateur.async_modifier_selection(jour=option)
