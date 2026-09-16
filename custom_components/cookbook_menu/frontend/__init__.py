"""Carte de tableau de bord servie et enregistrée automatiquement par l'intégration.

Le fichier JavaScript est exposé par un chemin statique, puis ajouté comme ressource Lovelace
(mode stockage), comme la trakt-card : rien à installer à la main. Tout est protégé pour
qu'un échec ici ne bloque jamais la mise en place de l'intégration.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CHEMIN_BASE = "/cookbook_menu_static"
FICHIER = "cookbook-menu-card.js"
URL_CARTE = f"{CHEMIN_BASE}/{FICHIER}"


def version_carte() -> str:
    """Version pour forcer le rechargement du navigateur quand le fichier change."""
    return str(int((Path(__file__).parent / FICHIER).stat().st_mtime))


async def async_enregistrer_carte(hass: HomeAssistant) -> None:
    """Sert le fichier de la carte et l'enregistre comme ressource Lovelace (une seule fois)."""
    if getattr(hass, "http", None) is None or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CHEMIN_BASE, str(Path(__file__).parent), False)]
        )
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
        for element in ressources.async_items():
            if element.get("url", "").startswith(URL_CARTE):
                if element["url"] != url:
                    await ressources.async_update_item(element["id"], {"res_type": "module", "url": url})
                return
        await ressources.async_create_item({"res_type": "module", "url": url})
    except Exception as err:
        _LOGGER.warning("Impossible d'enregistrer la carte Cookbook Menu comme ressource : %s", err)
