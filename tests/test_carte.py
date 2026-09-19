"""Carte de tableau de bord : commande websocket, recipe_id et enregistrement de la ressource (story 2.7)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.nextcloud_cookbook_menu import frontend
from custom_components.nextcloud_cookbook_menu.const import DOMAIN

from .test_menu import elements


@pytest.fixture(autouse=True)
async def langue(hass: HomeAssistant) -> None:
    await hass.config.async_update(language="fr")


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def test_commande_recettes(hass: HomeAssistant, entree, hass_ws_client: WebSocketGenerator) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/recipes"})
    reponse = await client.receive_json()
    assert reponse["success"]
    resultat = reponse["result"]
    assert resultat["config_entry_id"] == entree.entry_id
    assert resultat["default_servings"] == 2
    assert resultat["menu_entity"] == "todo.valentin_cloud_exemple_fr_menu_de_la_semaine"
    assert resultat["shopping_entity"] == "todo.valentin_cloud_exemple_fr_liste_de_courses"
    assert {"id": "69603", "name": "Salade César au poulet"} in resultat["recipes"]
    assert len(resultat["recipes"]) == 57

    await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/recipes", "config_entry_id": "inconnue"})
    reponse = await client.receive_json()
    assert not reponse["success"]
    assert reponse["error"]["code"] == "not_found"


async def test_commande_catalogue(hass: HomeAssistant, entree, hass_ws_client: WebSocketGenerator) -> None:
    """Catalogue des recettes pour la carte de consultation (story 2.13)."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/catalog"})
    reponse = await client.receive_json()
    assert reponse["success"], reponse
    resultat = reponse["result"]
    assert (resultat["config_entry_id"], resultat["default_servings"]) == (entree.entry_id, 2)
    assert len(resultat["recipes"]) == 57
    noms = [r["name"] for r in resultat["recipes"]]
    assert noms == sorted(noms, key=lambda n: n.lower().replace("Œ", "oe")) or noms[0] < noms[-1]
    carry = next(r for r in resultat["recipes"] if r["id"] == "2176038")
    assert (carry["name"], carry["category"]) == ("Carry de poulet", "Plats principaux")
    assert carry["image"].startswith(f"/api/nextcloud_cookbook_menu/image/{entree.entry_id}/2176038/thumb?authSig=")
    assert "Plats principaux" in resultat["categories"] and "" not in resultat["categories"]
    assert all("total_minutes" in r and "servings" in r for r in resultat["recipes"])

    await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/catalog", "config_entry_id": "inconnue"})
    reponse = await client.receive_json()
    assert not reponse["success"] and reponse["error"]["code"] == "not_found"


async def test_ajout_par_identifiant(hass: HomeAssistant, entree) -> None:
    reponse = await hass.services.async_call(
        DOMAIN,
        "add_to_menu",
        {"recipe": "peu importe", "recipe_id": "1663568", "servings": 3},
        blocking=True,
        return_response=True,
    )
    assert reponse["dish"] == "Salade César végétarienne (façon Rachel)"
    [plat] = await elements(hass)
    assert plat["description"] == "3 couverts"


async def test_fichier_de_la_carte_present() -> None:
    assert frontend.version_carte().isdigit()


async def test_enregistrement_ignore_sans_serveur_http(hass: HomeAssistant) -> None:
    await frontend.async_enregistrer_carte(hass)  # pas de hass.http en test : rien ne se passe


def _hass_avec_ressources(ressources) -> MagicMock:
    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components = {"frontend"}
    hass.data = {"lovelace": SimpleNamespace(resources=ressources)}
    hass.async_add_executor_job = AsyncMock(return_value="42")
    return hass


async def test_creation_de_la_ressource() -> None:
    ressources = MagicMock(loaded=False)
    ressources.async_load = AsyncMock()
    ressources.async_items.return_value = []
    ressources.async_create_item = AsyncMock()
    with patch("homeassistant.components.http.StaticPathConfig"):
        await frontend.async_enregistrer_carte(_hass_avec_ressources(ressources))
    ressources.async_create_item.assert_awaited_once_with(
        {"res_type": "module", "url": "/nextcloud_cookbook_menu_static/cookbook-menu-card.js?v=42"}
    )


async def test_ancienne_ressource_supprimee() -> None:
    """Renommage du domaine : la ressource du domaine cookbook_menu est retirée (story 2.13)."""
    ressources = MagicMock(loaded=True)
    ressources.async_items.return_value = [
        {"id": "vieille", "url": "/cookbook_menu_static/cookbook-menu-card.js?v=1789716075"},
        {"id": "autre", "url": "/trakt_scrobbler/trakt-card.js?v=1.3.0-10"},
    ]
    ressources.async_delete_item = AsyncMock()
    ressources.async_create_item = AsyncMock()
    ressources.async_update_item = AsyncMock()
    await frontend.async_enregistrer_carte(_hass_avec_ressources(ressources))
    ressources.async_delete_item.assert_awaited_once_with("vieille")
    ressources.async_create_item.assert_awaited_once_with(
        {"res_type": "module", "url": "/nextcloud_cookbook_menu_static/cookbook-menu-card.js?v=42"}
    )
    ressources.async_update_item.assert_not_awaited()


async def test_mise_a_jour_de_la_version() -> None:
    ressources = MagicMock(loaded=True)
    ressources.async_items.return_value = [
        {"id": "r1", "url": "/nextcloud_cookbook_menu_static/cookbook-menu-card.js?v=1"}
    ]
    ressources.async_update_item = AsyncMock()
    await frontend.async_enregistrer_carte(_hass_avec_ressources(ressources))
    ressources.async_update_item.assert_awaited_once()

    ressources.async_update_item.reset_mock()
    ressources.async_items.return_value = [
        {"id": "r1", "url": "/nextcloud_cookbook_menu_static/cookbook-menu-card.js?v=42"}
    ]
    await frontend.async_enregistrer_carte(_hass_avec_ressources(ressources))
    ressources.async_update_item.assert_not_awaited()


async def test_mode_yaml_et_erreurs() -> None:
    hass = _hass_avec_ressources(None)
    with patch("homeassistant.components.frontend.add_extra_js_url") as ajouter:
        await frontend.async_enregistrer_carte(hass)
    ajouter.assert_called_once()

    ressources = MagicMock(loaded=True)
    ressources.async_items.side_effect = RuntimeError("stockage")
    hass = _hass_avec_ressources(ressources)
    hass.http.async_register_static_paths.side_effect = RuntimeError("déjà enregistré")
    await frontend.async_enregistrer_carte(hass)
