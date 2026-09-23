"""Dashboard card served and registered automatically by the integration.

The JavaScript file is exposed through a static path, then added as a Lovelace resource
(storage mode), like the trakt-card: nothing to install by hand. Everything is guarded so
that a failure here never blocks the integration's setup.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CHEMIN_BASE = "/nextcloud_cookbook_menu_static"
FICHIER = "cookbook-menu-card.js"
URL_CARTE = f"{CHEMIN_BASE}/{FICHIER}"
# The domain was called "cookbook_menu" before 1.0.0: its resource is no longer of any use.
ANCIENNE_URL_CARTE = "/cookbook_menu_static/"


def version_carte() -> str:
    """Version used to force the browser to reload when the file changes."""
    return str(int((Path(__file__).parent / FICHIER).stat().st_mtime))


async def async_enregistrer_carte(hass: HomeAssistant) -> None:
    """Serves the card's file and registers it as a Lovelace resource (only once)."""
    if getattr(hass, "http", None) is None or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    try:
        await hass.http.async_register_static_paths([StaticPathConfig(CHEMIN_BASE, str(Path(__file__).parent), False)])
    except (RuntimeError, ValueError) as err:
        _LOGGER.debug("Chemin statique de la carte déjà enregistré ou impossible : %s", err)
    url = f"{URL_CARTE}?v={await hass.async_add_executor_job(version_carte)}"
    try:
        ressources = getattr(hass.data.get("lovelace"), "resources", None)
        if ressources is None:
            add_extra_js_url(hass, url)
            return
        if not ressources.loaded:
            await ressources.async_load()
            ressources.loaded = True
        enregistree = False
        for element in list(ressources.async_items()):
            adresse = element.get("url", "")
            if adresse.startswith(ANCIENNE_URL_CARTE):
                await ressources.async_delete_item(element["id"])
            elif adresse.startswith(URL_CARTE):
                if adresse != url:
                    await ressources.async_update_item(element["id"], {"res_type": "module", "url": url})
                enregistree = True
        if not enregistree:
            await ressources.async_create_item({"res_type": "module", "url": url})
    except Exception as err:
        _LOGGER.warning("Impossible d'enregistrer la carte Nextcloud Cookbook Menu comme ressource : %s", err)
