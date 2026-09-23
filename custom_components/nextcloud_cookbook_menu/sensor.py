"""Capteurs des minuteurs de cuisson : heure de fin et étape en cours."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CookbookMenuConfigEntry
from .entity import info_appareil
from .minuteurs import GestionnaireMinuteurs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CookbookMenuConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Un capteur par minuteur, selon le nombre réglé dans les options."""
    gestionnaire = entry.runtime_data.timers
    nombre = len(gestionnaire.minuteurs)
    # Le nombre a pu baisser : on retire les capteurs devenus inutiles.
    registre = er.async_get(hass)
    for entree_registre in er.async_entries_for_config_entry(registre, entry.entry_id):
        identifiant = entree_registre.unique_id.removeprefix(f"{entry.entry_id}_timer_")
        if identifiant.isdigit() and int(identifiant) > nombre:
            registre.async_remove(entree_registre.entity_id)
    async_add_entities(MinuteurSensor(entry, gestionnaire, numero) for numero in range(1, nombre + 1))


class MinuteurSensor(SensorEntity):
    """Heure de fin du minuteur, vide quand il ne tourne pas."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "timer"

    def __init__(self, entry: CookbookMenuConfigEntry, gestionnaire: GestionnaireMinuteurs, numero: int) -> None:
        self._gestionnaire = gestionnaire
        self._numero = numero
        self._attr_translation_placeholders = {"number": str(numero)}
        self._attr_unique_id = f"{entry.entry_id}_timer_{numero}"
        self._attr_device_info = info_appareil(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._gestionnaire.async_ecouter(self.async_write_ha_state))

    @property
    def native_value(self) -> datetime | None:
        return self._gestionnaire.minuteurs[self._numero - 1].fin

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        minuteur = self._gestionnaire.minuteurs[self._numero - 1]
        return {"step": minuteur.nom, "timer_entity": minuteur.entite}
