"""Produits récurrents : ce qui se consomme hors menu (story 2.15)."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from .test_courses import cocher, courses
from .test_reserve import installer


@pytest.fixture(autouse=True)
async def contexte(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-09-16 12:00:00+02:00")
    await hass.config.async_update(language="fr", time_zone="Europe/Paris")


async def test_beurre_des_tartines(hass: HomeAssistant, mock_client, config_entry, freezer) -> None:
    """Le beurre ne vient d'aucune recette : il revient dans les courses à chaque période."""
    await installer(hass, config_entry)
    planificateur = config_entry.runtime_data.planner
    planificateur.async_recurrent_ajouter("Beurre")
    await hass.async_block_till_done()
    ligne = (await courses(hass))["Beurre (250 g)"]  # une plaquette, pas 10 g
    assert ligne["description"] == "à racheter chaque semaine"

    await cocher(hass, "Beurre (250 g)")
    donnees = planificateur.stockage.donnees
    assert donnees.frigo["beurre"]["quantites"] == {"g": 250}
    assert donnees.recurrents["beurre"]["dernier_achat"] == "2026-09-16"
    assert "Beurre (250 g)" not in await courses(hass)

    # Six jours plus tard, rien. Le septième, il revient malgré le stock resté au frigo.
    freezer.move_to("2026-09-22 09:00:00+02:00")
    async_fire_time_changed(hass)  # le passage à minuit recalcule la liste
    await hass.async_block_till_done()
    assert not any(libelle.startswith("Beurre") for libelle in await courses(hass))
    freezer.move_to("2026-09-23 09:00:00+02:00")
    async_fire_time_changed(hass)  # le passage à minuit recalcule la liste
    await hass.async_block_till_done()
    assert (await courses(hass))["Beurre (250 g)"]["status"] == "needs_action"


async def test_frequence_par_produit(hass: HomeAssistant, mock_client, config_entry, freezer) -> None:
    await installer(hass, config_entry)
    planificateur = config_entry.runtime_data.planner
    planificateur.async_recurrent_ajouter("Café", 3)
    await hass.async_block_till_done()
    await cocher(hass, "Café (1)")
    freezer.move_to("2026-10-01 09:00:00+02:00")  # 15 jours : pas encore
    async_fire_time_changed(hass)  # le passage à minuit recalcule la liste
    await hass.async_block_till_done()
    assert not any(libelle.startswith("Café") for libelle in await courses(hass))
    freezer.move_to("2026-10-07 09:00:00+02:00")  # 3 semaines
    async_fire_time_changed(hass)  # le passage à minuit recalcule la liste
    await hass.async_block_till_done()
    assert any(libelle.startswith("Café") for libelle in await courses(hass))
    [recurrent] = planificateur.recurrents()
    assert (recurrent["name"], recurrent["weeks"], recurrent["due"]) == ("Café", 3, True)

    planificateur.async_recurrent_retirer("cafe")
    await hass.async_block_till_done()
    assert planificateur.recurrents() == []
    assert not any(libelle.startswith("Café") for libelle in await courses(hass))
    with pytest.raises(ServiceValidationError):
        planificateur.async_recurrent_ajouter("  ")


async def test_websocket_recurrents(
    hass: HomeAssistant, mock_client, config_entry, hass_ws_client: WebSocketGenerator
) -> None:
    await installer(hass, config_entry)
    client = await hass_ws_client(hass)
    for message in (
        {"action": "recurring", "name": "Beurre", "weeks": 2},
        {"action": "recurring", "key": "lait"},
        {"action": "not_recurring", "key": "lait"},
    ):
        await client.send_json_auto_id({"type": "nextcloud_cookbook_menu/stock/update", **message})
        assert (await client.receive_json())["success"]
    planificateur = config_entry.runtime_data.planner
    [beurre] = planificateur.recurrents()
    assert (beurre["key"], beurre["weeks"], beurre["days_left"]) == ("beurre", 2, 0)
    assert planificateur.reserve()["recurring"] == [beurre]


async def test_dates_d_achat_memorisees(hass: HomeAssistant, mock_client, config_entry) -> None:
    """Les dates servent aux futures propositions de récurrence."""
    from .test_menu import ajouter

    await installer(hass, config_entry)
    await ajouter(hass, "salade cesar")
    await cocher(hass, "Citron (1)")
    assert config_entry.runtime_data.planner.stockage.donnees.achats["citron"] == ["2026-09-16"]
