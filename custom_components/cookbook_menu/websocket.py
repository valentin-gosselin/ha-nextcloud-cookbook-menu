"""Commandes websocket pour la carte de tableau de bord."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .fiche import fiche


@callback
def async_enregistrer_commandes(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_recettes)
    websocket_api.async_register_command(hass, ws_fiche)


@websocket_api.websocket_command(
    {vol.Required("type"): "cookbook_menu/recipes", vol.Optional("config_entry_id"): str}
)
@callback
def ws_recettes(
    hass: HomeAssistant, connexion: websocket_api.ActiveConnection, message: dict[str, Any]
) -> None:
    """Recettes proposables (libellé et identifiant) et entités de l'entrée, pour la carte."""
    entrees = [
        e
        for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if message.get("config_entry_id") in (None, e.entry_id)
    ]
    if not entrees:
        connexion.send_error(message["id"], "not_found", "Cookbook Menu is not set up")
        return
    entree = entrees[0]
    planificateur = entree.runtime_data.planner
    registre = er.async_get(hass)
    connexion.send_result(
        message["id"],
        {
            "config_entry_id": entree.entry_id,
            "default_servings": planificateur.couverts_par_defaut,
            "menu_entity": registre.async_get_entity_id("todo", DOMAIN, f"{entree.entry_id}_menu"),
            "shopping_entity": registre.async_get_entity_id("todo", DOMAIN, f"{entree.entry_id}_shopping"),
            "recipes": [
                {"id": identifiant, "name": libelle}
                for libelle, identifiant in planificateur.choix_recettes().items()
            ],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "cookbook_menu/recipe",
        vol.Optional("config_entry_id"): str,
        vol.Exclusive("recipe_id", "cible"): str,
        vol.Exclusive("uid", "cible"): str,
    }
)
@callback
def ws_fiche(hass: HomeAssistant, connexion: websocket_api.ActiveConnection, message: dict[str, Any]) -> None:
    """Fiche d'une recette, par identifiant ou par plat du menu (couverts du plat)."""
    entrees = [
        e
        for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if message.get("config_entry_id") in (None, e.entry_id)
    ]
    if not entrees:
        connexion.send_error(message["id"], "not_found", "Cookbook Menu is not set up")
        return
    entree = entrees[0]
    planificateur = entree.runtime_data.planner
    couverts = planificateur.couverts_par_defaut
    recette = None
    if "uid" in message:
        plat = next((p for p in planificateur.menu if p.uid == message["uid"]), None)
        if plat is not None:
            recette = planificateur.recette_du_plat(plat)
            couverts = plat.servings
    elif "recipe_id" in message:
        recette = planificateur.recettes.get(message["recipe_id"])
    if recette is None:
        connexion.send_error(message["id"], "not_found", "Recipe not found")
        return
    connexion.send_result(message["id"], fiche(hass, entree.entry_id, recette, couverts))
