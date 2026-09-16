"""Flux de configuration de Cookbook Menu."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class CookbookMenuConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flux de configuration (squelette, complété par la story 1.2)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Étape initiale lancée depuis l'UI."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title="Cookbook Menu", data={})
