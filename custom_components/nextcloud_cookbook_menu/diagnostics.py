"""Diagnostics téléchargeables, sans secret."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import CookbookMenuConfigEntry

A_MASQUER = {CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: CookbookMenuConfigEntry) -> dict[str, Any]:
    """Diagnostics d'une entrée."""
    coordinateur = entry.runtime_data.coordinator
    index = coordinateur.data
    categories: dict[str, int] = {}
    for recette in [*index.recipes.values(), *index.excluded.values()]:
        cle = recette.category or "(sans catégorie)"
        categories[cle] = categories.get(cle, 0) + 1
    return {
        "entry": {"data": async_redact_data(dict(entry.data), A_MASQUER), "options": dict(entry.options)},
        "coordinator": {
            "last_update_success": coordinateur.last_update_success,
            "update_interval": str(coordinateur.update_interval),
        },
        "recipes": {
            "available": len(index.recipes),
            "excluded": len(index.excluded),
            "by_category": categories,
            "without_ingredients": sum(1 for r in index.recipes.values() if not r.ingredients),
        },
    }
