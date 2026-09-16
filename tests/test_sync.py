"""Synchronisation vers des listes existantes (story 2.5)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.todo import (
    DOMAIN as TODO_DOMAIN,
)
from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    setup_test_component_platform,
)

from custom_components.cookbook_menu.sync import Synchroniseur

from .test_menu import ajouter

MENU_CIBLE = "todo.menu_du_foyer"
COURSES_CIBLE = "todo.liste_du_foyer"


class ListeSimulee(TodoListEntity):
    """Liste todo complète (description et échéance), stockée en mémoire."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, nom: str, complete: bool = True) -> None:
        self._attr_name = nom
        self._attr_unique_id = nom
        self._attr_todo_items = []
        self._compteur = 0
        if not complete:
            self._attr_supported_features = (
                TodoListEntityFeature.CREATE_TODO_ITEM
                | TodoListEntityFeature.UPDATE_TODO_ITEM
                | TodoListEntityFeature.DELETE_TODO_ITEM
            )

    async def async_create_todo_item(self, item: TodoItem) -> None:
        self._compteur += 1
        item.uid = f"{self._attr_name}-{self._compteur}"
        item.status = item.status or TodoItemStatus.NEEDS_ACTION
        self._attr_todo_items = [*self._attr_todo_items, item]
        self.async_write_ha_state()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        self._attr_todo_items = [item if i.uid == item.uid else i for i in self._attr_todo_items]
        self.async_write_ha_state()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        self._attr_todo_items = [i for i in self._attr_todo_items if i.uid not in uids]
        self.async_write_ha_state()


@pytest.fixture
async def listes(hass: HomeAssistant) -> tuple[ListeSimulee, ListeSimulee]:
    menu, courses = ListeSimulee("Menu du foyer"), ListeSimulee("Liste du foyer", complete=False)
    setup_test_component_platform(hass, TODO_DOMAIN, [menu, courses])
    assert await async_setup_component(hass, TODO_DOMAIN, {TODO_DOMAIN: {"platform": "test"}})
    await hass.async_block_till_done()
    return menu, courses


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry: MockConfigEntry, listes, freezer):
    await hass.config.async_update(language="fr")
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            "sync_menu_entity": MENU_CIBLE,
            "sync_shopping_entity": COURSES_CIBLE,
            "pantry_reminder": False,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def attendre(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    for _ in range(3):
        freezer.tick(timedelta(seconds=2))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


async def cible(hass: HomeAssistant, entite: str) -> dict[str, dict[str, Any]]:
    reponse = await hass.services.async_call(
        TODO_DOMAIN, "get_items", {"entity_id": entite}, blocking=True, return_response=True
    )
    return {e["summary"]: e for e in reponse[entite]["items"]}


async def test_recopie_menu_et_courses(hass: HomeAssistant, entree, freezer) -> None:
    await ajouter(hass, "salade cesar", due_date="2026-09-17")
    await attendre(hass, freezer)
    menu = await cible(hass, MENU_CIBLE)
    assert menu["Salade César au poulet"]["description"] == "2 couverts"
    assert menu["Salade César au poulet"]["due"] == "2026-09-17"
    courses = await cible(hass, COURSES_CIBLE)
    assert "Citron (1)" in courses
    assert "description" not in courses["Citron (1)"]  # liste sans description


async def test_lignes_du_foyer_jamais_touchees(hass: HomeAssistant, entree, freezer) -> None:
    await hass.services.async_call(
        TODO_DOMAIN, "add_item", {"entity_id": COURSES_CIBLE, "item": "Papier toilette"}, blocking=True
    )
    await ajouter(hass, "salade cesar")
    await attendre(hass, freezer)
    await hass.services.async_call(
        TODO_DOMAIN,
        "remove_item",
        {"entity_id": "todo.valentin_cloud_exemple_fr_menu_de_la_semaine", "item": "Salade César au poulet"},
        blocking=True,
    )
    await attendre(hass, freezer)
    assert list(await cible(hass, COURSES_CIBLE)) == ["Papier toilette"]
    assert await cible(hass, MENU_CIBLE) == {}


async def test_mise_a_jour_et_cochage_remonte(hass: HomeAssistant, entree, freezer) -> None:
    await ajouter(hass, "salade cesar")
    await attendre(hass, freezer)
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {
            "entity_id": "todo.valentin_cloud_exemple_fr_menu_de_la_semaine",
            "item": "Salade César au poulet",
            "description": "pour 8",
        },
        blocking=True,
    )
    await attendre(hass, freezer)
    courses = await cible(hass, COURSES_CIBLE)
    assert "Escalope de poulet (4)" in courses
    assert "Escalope de poulet (1)" not in courses
    assert (await cible(hass, MENU_CIBLE))["Salade César au poulet"]["description"] == "8 couverts"

    # Cochée au magasin, dans la liste du foyer.
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": COURSES_CIBLE, "item": "Citron (2)", "status": "completed"},
        blocking=True,
    )
    await attendre(hass, freezer)
    planificateur = entree.runtime_data.planner
    citron = next(ligne for ligne in planificateur.liste_de_courses() if ligne.libelle == "Citron (2)")
    assert citron.fait

    # Décochée chez nous : redescend dans la cible.
    planificateur.async_modifier_course(citron.uid, texte=None, description=None, fait=False)
    await attendre(hass, freezer)
    assert (await cible(hass, COURSES_CIBLE))["Citron (2)"]["status"] == "needs_action"

    # Plat marqué cuisiné dans la cible : remonté au menu.
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": MENU_CIBLE, "item": "Salade César au poulet", "status": "completed"},
        blocking=True,
    )
    await attendre(hass, freezer)
    assert planificateur.menu[0].done


async def test_ligne_cochee_d_emblee_et_date_retiree(hass: HomeAssistant, entree, freezer) -> None:
    planificateur = entree.runtime_data.planner
    planificateur.async_ajouter_course("Pain")
    plat = planificateur.async_ajouter_plat("carry", jour=None)
    # Déjà acheté avant la première synchronisation : la ligne arrive cochée.
    thym = next(ligne for ligne in planificateur.liste_de_courses() if ligne.libelle.startswith("Thym"))
    planificateur.async_modifier_course(thym.uid, texte=None, description=None, fait=True)
    await attendre(hass, freezer)
    assert (await cible(hass, COURSES_CIBLE))["Pain"]["status"] == "needs_action"
    assert (await cible(hass, COURSES_CIBLE))["Thym (1 branche)"]["status"] == "completed"
    assert "due" not in (await cible(hass, MENU_CIBLE))["Carry de poulet"]
    from datetime import date

    planificateur.async_modifier_plat(plat.plat.uid, jour=date(2026, 9, 20))
    await attendre(hass, freezer)
    assert (await cible(hass, MENU_CIBLE))["Carry de poulet"]["due"] == "2026-09-20"
    planificateur.async_modifier_plat(plat.plat.uid, jour=None)
    await attendre(hass, freezer)
    assert "due" not in (await cible(hass, MENU_CIBLE))["Carry de poulet"]


async def test_cible_indisponible_ou_erreur(hass: HomeAssistant, entree, freezer, caplog) -> None:
    synchro: Synchroniseur = entree.runtime_data.sync
    hass.states.async_set(MENU_CIBLE, "unavailable")
    hass.states.async_set("todo.fantome", "0")  # un état sans entité : get_items échoue
    hass.config_entries.async_update_entry(
        entree, options={**entree.options, "sync_shopping_entity": "todo.fantome"}
    )
    await ajouter(hass, "carry")
    await synchro.async_synchroniser()
    assert "Synchronisation vers todo.fantome impossible" in caplog.text


async def test_sans_cible_rien_ne_demarre(hass: HomeAssistant, mock_client, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert entree_sans_abonnement(config_entry)


def entree_sans_abonnement(config_entry) -> bool:
    return config_entry.runtime_data.sync._desabonnements == []


async def test_options_proposent_les_listes_sauf_les_notres(hass: HomeAssistant, entree) -> None:
    result = await hass.config_entries.options.async_init(entree.entry_id)
    selecteur = next(v for k, v in result["data_schema"].schema.items() if k == "sync_menu_entity")
    assert "todo.valentin_cloud_exemple_fr_menu_de_la_semaine" in selecteur.config["exclude_entities"]
