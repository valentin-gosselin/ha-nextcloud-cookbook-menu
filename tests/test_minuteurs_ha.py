"""Minuteurs de cuisson côté Home Assistant (story 2.14)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import async_capture_events, async_mock_service

from custom_components.nextcloud_cookbook_menu.const import (
    CONF_TIMER_DEVICE,
    CONF_TIMER_ENTITY,
    DOMAIN,
    EVENEMENT_MINUTEUR,
)

from .test_reserve import installer


async def lancer(hass: HomeAssistant, **donnees) -> None:
    await hass.services.async_call(
        DOMAIN, "start_timer", {"seconds": 1500, "name": "Étape 3 - Carry de poulet", **donnees}, blocking=True
    )
    await hass.async_block_till_done()


async def test_evenement_toujours_emis(hass: HomeAssistant, mock_client, config_entry) -> None:
    """Sans rien configurer, l'intégration émet un événement : les automatisations font le reste."""
    await installer(hass, config_entry)
    evenements = async_capture_events(hass, EVENEMENT_MINUTEUR)
    await lancer(hass)
    assert len(evenements) == 1
    assert evenements[0].data == {
        "config_entry_id": config_entry.entry_id,
        "name": "Étape 3 - Carry de poulet",
        "seconds": 1500,
        "timer": 1,
        "entity_id": None,
    }
    # Le minuteur occupe le premier capteur de l'intégration.
    gestionnaire = config_entry.runtime_data.timers
    assert gestionnaire.minuteurs[0].nom == "Étape 3 - Carry de poulet"
    assert hass.states.get("sensor.valentin_cloud_exemple_fr_timer_1").state != "unknown"


async def test_entites_minuteur(hass: HomeAssistant, mock_client, config_entry) -> None:
    """Plusieurs minuteurs à soi : on prend le premier au repos, puis le suivant."""
    await installer(hass, config_entry, **{CONF_TIMER_ENTITY: ["timer.cuisine", "timer.four"]})
    hass.states.async_set("timer.cuisine", "idle")
    hass.states.async_set("timer.four", "idle")
    appels = async_mock_service(hass, "timer", "start")
    annulations = async_mock_service(hass, "timer", "cancel")
    await lancer(hass)
    assert appels[0].data == {"entity_id": "timer.cuisine", "duration": "0:25:00"}

    hass.states.async_set("timer.cuisine", "active")
    await lancer(hass, seconds=60)
    assert appels[1].data == {"entity_id": "timer.four", "duration": "0:01:00"}
    gestionnaire = config_entry.runtime_data.timers
    assert [m.entite for m in gestionnaire.minuteurs] == ["timer.cuisine", "timer.four", None]

    # Arrêt du deuxième : son entité est annulée, le minuteur redevient libre.
    await hass.services.async_call(DOMAIN, "stop_timer", {"timer": 2}, blocking=True)
    assert annulations[0].data == {"entity_id": "timer.four"}
    assert gestionnaire.minuteurs[1].libre

    # Arrêt de tous.
    await hass.services.async_call(DOMAIN, "stop_timer", {}, blocking=True)
    assert all(m.libre for m in gestionnaire.minuteurs)


async def test_tous_les_minuteurs_occupes(hass: HomeAssistant, mock_client, config_entry) -> None:
    """Au-delà du nombre réglé, la carte garde son compte à rebours mais HA ne suit plus."""
    from custom_components.nextcloud_cookbook_menu.const import CONF_TIMERS_COUNT

    await installer(hass, config_entry, **{CONF_TIMERS_COUNT: 2})
    for _ in range(2):
        await lancer(hass)
    reponse = await hass.services.async_call(
        DOMAIN, "start_timer", {"seconds": 60}, blocking=True, return_response=True
    )
    assert reponse == {"timer": None, "entity_id": None}


async def test_appareil_vocal(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry, **{CONF_TIMER_DEVICE: "appareil-1"})
    with patch("homeassistant.helpers.intent.async_handle", new_callable=AsyncMock) as async_handle:
        await lancer(hass)
    assert async_handle.await_args.args[2] == intent.INTENT_START_TIMER
    assert async_handle.await_args.args[3] == {
        "seconds": {"value": 1500},
        "name": {"value": "Étape 3 - Carry de poulet"},
    }
    assert async_handle.await_args.kwargs["device_id"] == "appareil-1"


async def test_appareil_sans_minuteur(hass: HomeAssistant, mock_client, config_entry) -> None:
    """Un appareil qui ne sait pas tenir de minuteur ne doit pas passer inaperçu."""
    await installer(hass, config_entry, **{CONF_TIMER_DEVICE: "grille-pain"})
    with (
        patch(
            "homeassistant.helpers.intent.async_handle",
            new_callable=AsyncMock,
            side_effect=intent.IntentHandleError("pas de minuteur"),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await lancer(hass)


async def test_minuteur_sans_nom(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry, **{CONF_TIMER_DEVICE: "appareil-1"})
    with patch("homeassistant.helpers.intent.async_handle", new_callable=AsyncMock) as async_handle:
        await hass.services.async_call(DOMAIN, "start_timer", {"seconds": 60}, blocking=True)
    assert async_handle.await_args.args[3] == {"seconds": {"value": 60}}


async def test_fin_du_minuteur_libere_la_place(hass: HomeAssistant, mock_client, config_entry, freezer) -> None:
    """Une fois la durée écoulée, le minuteur se libère tout seul."""
    from datetime import timedelta

    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await installer(hass, config_entry)
    await lancer(hass, seconds=60)
    gestionnaire = config_entry.runtime_data.timers
    assert not gestionnaire.minuteurs[0].libre
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert gestionnaire.minuteurs[0].libre
    assert hass.states.get("sensor.valentin_cloud_exemple_fr_timer_1").state == "unknown"
    assert gestionnaire.async_arreter(99) is None
