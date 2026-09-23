"""Number of servings for the dish to add."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CookbookMenuConfigEntry
from .entity import CookbookMenuControle

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: CookbookMenuConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([CouvertsNumber(entry)])


class CouvertsNumber(CookbookMenuControle, NumberEntity):
    """Servings: defaults to the options' servings until changed."""

    _attr_native_min_value = 1
    _attr_native_max_value = 30
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: CookbookMenuConfigEntry) -> None:
        super().__init__(entry, "servings")

    @property
    def native_value(self) -> int:
        return self.planificateur.selection.couverts or self.planificateur.couverts_par_defaut

    async def async_set_native_value(self, value: float) -> None:
        self.planificateur.async_modifier_selection(couverts=int(value))
