"""Tests for setup, the coordinator, and diagnostics."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.nextcloud_cookbook_menu.api import CookbookAuthError, CookbookConnectionError
from custom_components.nextcloud_cookbook_menu.const import DOMAIN
from custom_components.nextcloud_cookbook_menu.diagnostics import async_get_config_entry_diagnostics


async def test_setup_charge_les_recettes(hass: HomeAssistant, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.LOADED

    index = config_entry.runtime_data.coordinator.data
    assert len(index.recipes) == 57
    assert {r.name for r in index.excluded.values()} == {"Lessive", "Colle à papier-peint"}

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_identifiants_refuses(hass, mock_client, config_entry) -> None:
    mock_client.async_get_recipe_stubs.side_effect = CookbookAuthError
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flux = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flux] == [SOURCE_REAUTH]


async def test_setup_serveur_injoignable(hass, mock_client, config_entry) -> None:
    mock_client.async_get_recipes.side_effect = CookbookConnectionError("hors ligne")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_rafraichissement_transmet_le_cache(hass, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    coordinateur = config_entry.runtime_data.coordinator
    assert coordinateur.update_interval == timedelta(minutes=30)

    mock_client.async_get_recipes.side_effect = CookbookConnectionError("coupure")
    await coordinateur.async_refresh()
    assert not coordinateur.last_update_success

    mock_client.async_get_recipes.side_effect = None
    await coordinateur.async_refresh()
    assert coordinateur.last_update_success
    appel = mock_client.async_get_recipes.call_args
    assert len(appel.args[2]) == 59


@pytest.mark.parametrize("sans_ingredients", [0, 1])
async def test_diagnostics_sans_secret(hass, mock_client, config_entry, recettes, sans_ingredients) -> None:
    if sans_ingredients:
        premiere = next(iter(recettes))
        recettes[premiere] = recettes[premiere].__class__(
            **{**{f: getattr(recettes[premiere], f) for f in recettes[premiere].__slots__}, "ingredients": ()}
        )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    texte = str(diag)
    assert "mot-de-passe-application" not in texte
    assert "valentin" not in texte
    assert diag["recipes"]["available"] == 57
    assert diag["recipes"]["excluded"] == 2
    assert diag["recipes"]["without_ingredients"] >= sans_ingredients
    assert DOMAIN not in diag["entry"]["data"]


async def test_client_sans_cookies(hass: HomeAssistant) -> None:
    """The client must never keep the Nextcloud session cookie (see create_client)."""
    import aiohttp

    from custom_components.nextcloud_cookbook_menu import create_client

    from .conftest import DONNEES_ENTREE

    client = create_client(hass, dict(DONNEES_ENTREE))
    assert isinstance(client._session.cookie_jar, aiohttp.DummyCookieJar)


def _ecrire(chemin: Path, contenu: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")


async def test_reprise_de_l_ancien_domaine(hass: HomeAssistant, tmp_path: Path) -> None:
    """Renaming the domain in 1.0.0 must not lose the menu or the pantry."""
    from custom_components.nextcloud_cookbook_menu.store import ANCIEN_DOMAINE, StockagePlanificateur

    # Separate config folder: the other tests share the test library's own.
    hass.config.config_dir = str(tmp_path)
    dossier = tmp_path / ".storage"
    ancien = json.dumps(
        {
            "version": 1,
            "data": {
                "menu": [{"uid": "u1", "summary": "Carry de poulet", "servings": 4}],
                "placard_ajouts": {"ras el hanout": "Ras el hanout"},
            },
        }
    )
    await hass.async_add_executor_job(_ecrire, dossier / f"{ANCIEN_DOMAINE}.abc123", ancien)
    donnees = await StockagePlanificateur(hass, "nouvelle-entree").async_charger()
    assert [p.summary for p in donnees.menu] == ["Carry de poulet"]
    assert donnees.placard_ajouts == {"ras el hanout": "Ras el hanout"}

    # Two files (or none): we don't guess, we start fresh.
    await hass.async_add_executor_job(_ecrire, dossier / f"{ANCIEN_DOMAINE}.def456", "{}")
    assert (await StockagePlanificateur(hass, "autre").async_charger()).menu == []

    def nettoyer() -> None:
        for fichier in dossier.glob(f"{ANCIEN_DOMAINE}.*"):
            fichier.unlink()

    await hass.async_add_executor_job(nettoyer)
    assert (await StockagePlanificateur(hass, "encore").async_charger()).menu == []

    # Unreadable file: startup is not blocked.
    await hass.async_add_executor_job(_ecrire, dossier / f"{ANCIEN_DOMAINE}.ghi789", "pas du json")
    assert (await StockagePlanificateur(hass, "malgre-tout").async_charger()).menu == []
