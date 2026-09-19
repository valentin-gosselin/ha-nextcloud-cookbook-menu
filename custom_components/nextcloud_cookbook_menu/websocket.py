"""Commandes websocket pour la carte de tableau de bord."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .fiche import fiche, image_signee
from .ingredients.normalize import sans_accents


@callback
def async_enregistrer_commandes(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_recettes)
    websocket_api.async_register_command(hass, ws_catalogue)
    websocket_api.async_register_command(hass, ws_fiche)
    websocket_api.async_register_command(hass, ws_reserve)
    websocket_api.async_register_command(hass, ws_reserve_modifier)


@websocket_api.websocket_command(
    {vol.Required("type"): "nextcloud_cookbook_menu/recipes", vol.Optional("config_entry_id"): str}
)
@callback
def ws_recettes(hass: HomeAssistant, connexion: websocket_api.ActiveConnection, message: dict[str, Any]) -> None:
    """Recettes proposables (libellé et identifiant) et entités de l'entrée, pour la carte."""
    entrees = [
        e
        for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if message.get("config_entry_id") in (None, e.entry_id)
    ]
    if not entrees:
        connexion.send_error(message["id"], "not_found", "Nextcloud Cookbook Menu is not set up")
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
                {"id": identifiant, "name": libelle} for libelle, identifiant in planificateur.choix_recettes().items()
            ],
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "nextcloud_cookbook_menu/catalog", vol.Optional("config_entry_id"): str}
)
@callback
def ws_catalogue(hass: HomeAssistant, connexion: websocket_api.ActiveConnection, message: dict[str, Any]) -> None:
    """Toutes les recettes avec leur vignette et leur catégorie, pour la carte de consultation."""
    entree = _entree(hass, message)
    if entree is None:
        connexion.send_error(message["id"], "not_found", "Nextcloud Cookbook Menu is not set up")
        return
    planificateur = entree.runtime_data.planner
    recettes = sorted(planificateur.recettes.values(), key=lambda r: sans_accents(r.name))
    connexion.send_result(
        message["id"],
        {
            "config_entry_id": entree.entry_id,
            "default_servings": planificateur.couverts_par_defaut,
            "categories": sorted({r.category for r in recettes if r.category}, key=sans_accents),
            "recipes": [
                {
                    "id": recette.id,
                    "name": recette.name,
                    "category": recette.category,
                    "total_minutes": recette.total_minutes,
                    "servings": recette.servings,
                    "image": image_signee(hass, entree.entry_id, recette.id, "thumb"),
                }
                for recette in recettes
            ],
        },
    )


def _entree(hass: HomeAssistant, message: dict[str, Any]) -> Any:
    for entree in hass.config_entries.async_loaded_entries(DOMAIN):
        if message.get("config_entry_id") in (None, entree.entry_id):
            return entree
    return None


@websocket_api.websocket_command(
    {vol.Required("type"): "nextcloud_cookbook_menu/stock/subscribe", vol.Optional("config_entry_id"): str}
)
@callback
def ws_reserve(hass: HomeAssistant, connexion: websocket_api.ActiveConnection, message: dict[str, Any]) -> None:
    """Réserve (placard, frigo, maison), puis chaque changement."""
    entree = _entree(hass, message)
    if entree is None:
        connexion.send_error(message["id"], "not_found", "Nextcloud Cookbook Menu is not set up")
        return
    planificateur = entree.runtime_data.planner

    @callback
    def envoyer() -> None:
        # Les propositions de l'index ne servent qu'à la carte (pas à l'outil LLM `get_stock`).
        reserve = {**planificateur.reserve(), "suggestions": planificateur.propositions_placard()}
        connexion.send_message(websocket_api.event_message(message["id"], reserve))

    connexion.subscriptions[message["id"]] = planificateur.async_ecouter(envoyer)
    connexion.send_result(message["id"])
    envoyer()


@websocket_api.websocket_command(
    {
        vol.Required("type"): "nextcloud_cookbook_menu/stock/update",
        vol.Optional("config_entry_id"): str,
        vol.Required("action"): vol.In(["missing", "present", "remove", "check_pantry", "to_pantry"]),
        vol.Optional("key"): str,
        vol.Optional("name"): str,
        vol.Optional("names"): [str],
        vol.Optional("missing"): [str],
    }
)
@callback
def ws_reserve_modifier(
    hass: HomeAssistant, connexion: websocket_api.ActiveConnection, message: dict[str, Any]
) -> None:
    """« Il n'y en a plus », « j'en ai », « sortir de la réserve », « au placard », vérification."""
    entree = _entree(hass, message)
    if entree is None:
        connexion.send_error(message["id"], "not_found", "Nextcloud Cookbook Menu is not set up")
        return
    planificateur = entree.runtime_data.planner
    action = message["action"]
    try:
        if action == "check_pantry":
            planificateur.async_valider_placard(message.get("missing", []))
        elif action == "to_pantry" and ("name" in message or "names" in message):
            noms = message.get("names", []) + ([message["name"]] if "name" in message else [])
            planificateur.async_reserve_au_placard(noms=noms)
        elif "key" not in message:
            connexion.send_error(message["id"], "invalid_format", "key is required")
            return
        elif action == "missing":
            planificateur.async_reserve_manquant(message["key"])
        elif action == "present":
            planificateur.async_reserve_present(message["key"])
        elif action == "to_pantry":
            planificateur.async_reserve_au_placard(cle_produit=message["key"])
        else:
            planificateur.async_reserve_retirer(message["key"])
    except HomeAssistantError as err:
        connexion.send_error(message["id"], "not_found", str(err))
        return
    connexion.send_result(message["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "nextcloud_cookbook_menu/recipe",
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
        connexion.send_error(message["id"], "not_found", "Nextcloud Cookbook Menu is not set up")
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
