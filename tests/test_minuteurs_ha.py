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
    }


async def test_entite_minuteur(hass: HomeAssistant, mock_client, config_entry) -> None:
    await installer(hass, config_entry, **{CONF_TIMER_ENTITY: "timer.cuisine"})
    appels = async_mock_service(hass, "timer", "start")
    await lancer(hass)
    assert len(appels) == 1
    assert appels[0].data == {"entity_id": "timer.cuisine", "duration": "0:25:00"}


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
