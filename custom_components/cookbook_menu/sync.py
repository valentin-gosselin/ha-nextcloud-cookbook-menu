"""Synchronisation en écriture seule vers des listes todo existantes (story 2.5).

Nos listes restent la source de vérité. On recopie leurs lignes dans la liste choisie par le
foyer (celle qu'on ouvre au magasin), en ne touchant JAMAIS aux lignes qu'on n'a pas créées.
Un cochage fait dans la liste cible est remonté dans la nôtre.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.components.todo import TodoListEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_SYNC_MENU_ENTITY, CONF_SYNC_SHOPPING_ENTITY
from .libelles import libelles
from .planner import Planificateur

_LOGGER = logging.getLogger(__name__)
DELAI = 1.0


@dataclass(frozen=True, slots=True)
class LigneSource:
    """Ce qu'on veut voir dans la liste cible pour une de nos lignes."""

    uid: str
    resume: str
    fait: bool
    description: str | None = None
    echeance: date | None = None


class Synchroniseur:
    """Recopie le menu et la liste de courses vers les entités todo choisies dans les options."""

    def __init__(self, hass: HomeAssistant, planificateur: Planificateur) -> None:
        self.hass = hass
        self.planificateur = planificateur
        self._desabonnements: list[CALLBACK_TYPE] = []
        self._debounce = Debouncer(
            hass, _LOGGER, cooldown=DELAI, immediate=False, function=self.async_synchroniser, background=True
        )

    @property
    def cibles(self) -> dict[str, str]:
        """Genre de liste ("menu" ou "courses") -> entité cible."""
        options = self.planificateur.coordinateur.config_entry.options
        cibles = {
            "menu": options.get(CONF_SYNC_MENU_ENTITY),
            "courses": options.get(CONF_SYNC_SHOPPING_ENTITY),
        }
        return {genre: entite for genre, entite in cibles.items() if entite}

    @callback
    def async_demarrer(self) -> None:
        if not self.cibles:
            return
        self._desabonnements.append(self.planificateur.async_ecouter(self._planifier))
        self._desabonnements.append(
            async_track_state_change_event(self.hass, list(self.cibles.values()), self._cible_modifiee)
        )
        self._planifier()

    @callback
    def async_arreter(self) -> None:
        for desabonner in self._desabonnements:
            desabonner()
        self._desabonnements.clear()
        self._debounce.async_shutdown()

    @callback
    def _planifier(self) -> None:
        self.hass.async_create_task(self._debounce.async_call(), eager_start=True)

    @callback
    def _cible_modifiee(self, _event: Event[EventStateChangedData]) -> None:
        self._planifier()

    def _sources(self, genre: str) -> list[LigneSource]:
        if genre == "menu":
            textes = libelles(self.hass)
            return [
                LigneSource(
                    uid=plat.uid,
                    resume=plat.summary,
                    fait=plat.done,
                    description=textes["un_couvert"]
                    if plat.servings == 1
                    else textes["couverts"].format(n=plat.servings),
                    echeance=plat.day,
                )
                for plat in self.planificateur.menu
            ]
        return [
            LigneSource(uid=ligne.uid, resume=ligne.libelle, fait=ligne.fait, description=ligne.description)
            for ligne in self.planificateur.liste_de_courses()
        ]

    async def _elements_cible(self, entite: str) -> dict[str, dict[str, Any]]:
        reponse = await self.hass.services.async_call(
            TODO_DOMAIN, "get_items", {"entity_id": entite}, blocking=True, return_response=True
        )
        return {element["uid"]: element for element in reponse[entite]["items"]}

    async def async_synchroniser(self) -> None:
        """Aligne chaque liste cible sur la nôtre."""
        for genre, entite in self.cibles.items():
            try:
                await self._synchroniser(genre, entite)
            except HomeAssistantError as err:
                _LOGGER.warning("Synchronisation vers %s impossible : %s", entite, err)

    async def _synchroniser(self, genre: str, entite: str) -> None:
        etat = self.hass.states.get(entite)
        if etat is None or etat.state == "unavailable":
            return
        fonctions = int(etat.attributes.get(ATTR_SUPPORTED_FEATURES, 0))
        avec_description = bool(fonctions & TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM)
        avec_echeance = bool(fonctions & TodoListEntityFeature.SET_DUE_DATE_ON_ITEM)

        # Correspondances mémorisées : notre uid -> {uid cible, dernier état poussé}.
        memoire: dict[str, dict[str, Any]] = self.planificateur.stockage.donnees.synchro.setdefault(
            entite, {}
        )
        cible = await self._elements_cible(entite)
        sources = {source.uid: source for source in self._sources(genre)}
        modifie = False

        # 1. Cochages faits dans la liste cible : remontés dans la nôtre.
        for uid, lien in memoire.items():
            element = cible.get(lien["uid"])
            source = sources.get(uid)
            if element is None or source is None:
                continue
            fait_cible = element["status"] == "completed"
            if fait_cible != lien["fait"] and fait_cible != source.fait:
                lien["fait"] = fait_cible
                self._remonter(genre, source, fait_cible)
                modifie = True
        if modifie:
            sources = {source.uid: source for source in self._sources(genre)}

        # 2. Lignes disparues chez nous : retirées de la cible (seulement celles qu'on a créées).
        a_retirer = [
            lien["uid"] for uid, lien in memoire.items() if uid not in sources and lien["uid"] in cible
        ]
        if a_retirer:
            await self._appeler("remove_item", entite, {"item": a_retirer})
        for uid in [uid for uid in memoire if uid not in sources]:
            del memoire[uid]

        # 3. Ajouts et mises à jour.
        for source in sources.values():
            donnees: dict[str, Any] = {}
            if avec_description:
                donnees["description"] = source.description or ""
            if avec_echeance and genre == "menu" and (source.echeance or source.uid in memoire):
                donnees["due_date"] = source.echeance
            lien = memoire.get(source.uid)
            element = cible.get(lien["uid"]) if lien else None
            statut = "completed" if source.fait else "needs_action"
            if element is None:
                await self._appeler("add_item", entite, {"item": source.resume, **donnees})
                nouveaux = {u: e for u, e in (await self._elements_cible(entite)).items() if u not in cible}
                uid_cible = next((u for u, e in nouveaux.items() if e["summary"] == source.resume), None)
                if uid_cible is None:  # pragma: no cover - liste cible qui réécrit les libellés
                    continue
                cible[uid_cible] = nouveaux[uid_cible]
                if source.fait:
                    await self._appeler("update_item", entite, {"item": uid_cible, "status": statut})
                memoire[source.uid] = {"uid": uid_cible, "fait": source.fait}
                modifie = True
                continue
            changements: dict[str, Any] = {}
            if element["summary"] != source.resume:
                changements["rename"] = source.resume
            if (element["status"] == "completed") != source.fait:
                changements["status"] = statut
            if avec_description and (element.get("description") or "") != donnees["description"]:
                changements["description"] = donnees["description"]
            if "due_date" in donnees:
                echeance = donnees["due_date"].isoformat() if donnees["due_date"] else None
                if element.get("due") != echeance:
                    changements["due_date"] = donnees["due_date"]
            if changements:
                await self._appeler("update_item", entite, {"item": lien["uid"], **changements})
            if lien["fait"] != source.fait:
                lien["fait"] = source.fait
                modifie = True
        if modifie or a_retirer:
            self.planificateur.stockage.planifier_sauvegarde()

    def _remonter(self, genre: str, source: LigneSource, fait: bool) -> None:
        if genre == "menu":
            self.planificateur.async_modifier_plat(source.uid, fait=fait)
        else:
            self.planificateur.async_modifier_course(
                source.uid, texte=None, description=source.description, fait=fait
            )

    async def _appeler(self, action: str, entite: str, donnees: dict[str, Any]) -> None:
        await self.hass.services.async_call(
            TODO_DOMAIN, action, {"entity_id": entite, **donnees}, blocking=True
        )
