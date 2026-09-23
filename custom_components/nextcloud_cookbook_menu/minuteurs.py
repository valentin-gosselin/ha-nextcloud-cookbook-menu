"""Minuteurs de cuisson tenus par l'intégration : trois en parallèle, pour suivre plusieurs plats."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class Minuteur:
    """Un minuteur en cours : ce que la fiche a lancé."""

    nom: str | None = None
    fin: datetime | None = None
    # Entité timer.* de l'utilisateur démarrée en même temps, s'il en a réglé.
    entite: str | None = None

    @property
    def libre(self) -> bool:
        return self.fin is None


class GestionnaireMinuteurs:
    """Les minuteurs de l'entrée (trois par défaut), exposés en capteurs et pilotés par les actions."""

    def __init__(self, hass: HomeAssistant, nombre: int) -> None:
        self.hass = hass
        self.minuteurs = [Minuteur() for _ in range(nombre)]
        self._ecouteurs: list[Callable[[], None]] = []
        self._fins: list[CALLBACK_TYPE | None] = [None] * nombre

    @callback
    def async_ecouter(self, rappel: Callable[[], None]) -> CALLBACK_TYPE:
        self._ecouteurs.append(rappel)

        def desabonner() -> None:
            self._ecouteurs.remove(rappel)

        return desabonner

    @callback
    def _signaler(self) -> None:
        for rappel in list(self._ecouteurs):
            rappel()

    @callback
    def async_demarrer(self, nom: str, secondes: int, entite: str | None = None) -> int | None:
        """Occupe le premier minuteur libre. Renvoie son numéro, ou None s'ils tournent tous."""
        index = next((i for i, m in enumerate(self.minuteurs) if m.libre), None)
        if index is None:
            return None
        self.minuteurs[index] = Minuteur(
            nom=nom or None, fin=dt_util.utcnow() + timedelta(seconds=secondes), entite=entite
        )

        @callback
        def _fini(_maintenant: datetime) -> None:
            self._fins[index] = None
            self.async_arreter(index + 1)

        self._fins[index] = async_call_later(self.hass, secondes, _fini)
        self._signaler()
        return index + 1

    @callback
    def async_arreter(self, numero: int) -> Minuteur | None:
        """Libère un minuteur (fin atteinte ou arrêt demandé). Renvoie ce qu'il contenait."""
        if not 1 <= numero <= len(self.minuteurs):
            return None
        index = numero - 1
        precedent = self.minuteurs[index]
        if annuler := self._fins[index]:
            annuler()
            self._fins[index] = None
        self.minuteurs[index] = Minuteur()
        self._signaler()
        return precedent if not precedent.libre else None

    @callback
    def async_tout_arreter(self) -> None:
        for numero in range(1, len(self.minuteurs) + 1):
            self.async_arreter(numero)
