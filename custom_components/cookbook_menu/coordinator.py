"""Coordinateur : index des recettes Nextcloud Cookbook, rafraîchi périodiquement."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CookbookAuthError, CookbookClient, CookbookError, Recipe
from .const import (
    CONF_EXCLUDED_CATEGORIES,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_PARALLEL_REQUESTS,
)

if TYPE_CHECKING:
    from . import CookbookMenuConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RecipeIndex:
    """Recettes disponibles, après exclusion des catégories choisies dans les options."""

    recipes: dict[str, Recipe] = field(default_factory=dict)
    excluded: dict[str, Recipe] = field(default_factory=dict)


class CookbookCoordinator(DataUpdateCoordinator[RecipeIndex]):
    """Charge la liste des recettes et ne recharge le détail que des recettes modifiées."""

    config_entry: CookbookMenuConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CookbookMenuConfigEntry, client: CookbookClient) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self._cache: dict[str, Recipe] = {}

    async def _async_update_data(self) -> RecipeIndex:
        try:
            stubs = await self.client.async_get_recipe_stubs()
            recettes = await self.client.async_get_recipes(stubs, MAX_PARALLEL_REQUESTS, self._cache)
        except CookbookAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth") from err
        except CookbookError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self._cache = recettes

        exclues = {c.casefold() for c in self.config_entry.options.get(CONF_EXCLUDED_CATEGORIES, [])}
        index = RecipeIndex()
        for recette in recettes.values():
            if recette.category and recette.category.casefold() in exclues:
                index.excluded[recette.id] = recette
            else:
                index.recipes[recette.id] = recette
        return index
