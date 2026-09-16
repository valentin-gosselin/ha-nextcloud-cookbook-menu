"""Entités de sélection : recette, jour, couverts, bouton (story 2.6)."""

from __future__ import annotations

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.cookbook_menu.api import Recipe

from .test_courses import courses
from .test_menu import elements

RECETTE = "select.valentin_cloud_exemple_fr_recette_a_ajouter"
JOUR = "select.valentin_cloud_exemple_fr_jour"
COUVERTS = "number.valentin_cloud_exemple_fr_couverts"
BOUTON = "button.valentin_cloud_exemple_fr_ajouter_au_menu"


@pytest.fixture(autouse=True)
async def contexte(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-09-16 12:00:00+02:00")  # un mercredi
    await hass.config.async_update(language="fr", time_zone="Europe/Paris")


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def choisir(hass: HomeAssistant, entite: str, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entite, "option": option}, blocking=True
    )


async def test_liste_des_recettes_par_nom(hass: HomeAssistant, entree) -> None:
    etat = hass.states.get(RECETTE)
    options = etat.attributes["options"]
    assert len(options) == 57  # hors catégorie exclue « Produits Ménagers »
    assert options[:3] == [
        "Aperol Spritz",
        "Banana bread aux pépites de chocolat sans sucre ajouté",
        "Bœuf à la coréenne",
    ]
    assert "Lessive" not in options
    assert etat.state == "unknown"
    assert hass.states.get(JOUR).state == "sans_date"
    assert hass.states.get(COUVERTS).state == "2"


async def test_ajout_par_les_entites(hass: HomeAssistant, entree) -> None:
    await choisir(hass, RECETTE, "Salade César au poulet")
    await choisir(hass, JOUR, "vendredi")
    await hass.services.async_call("number", "set_value", {"entity_id": COUVERTS, "value": 4}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": BOUTON}, blocking=True)
    [plat] = await elements(hass)
    assert (plat["summary"], plat["due"], plat["description"]) == (
        "Salade César au poulet",
        "2026-09-18",
        "4 couverts",
    )
    assert "Escalope de poulet (2)" in await courses(hass)
    assert hass.states.get(RECETTE).state == "unknown"  # choix vidé pour éviter un double ajout
    assert hass.states.get(COUVERTS).state == "4"


@pytest.mark.parametrize(
    ("jour", "attendu"),
    [
        ("aujourd_hui", "2026-09-16"),
        ("demain", "2026-09-17"),
        ("mercredi", "2026-09-16"),
        ("lundi", "2026-09-21"),
        ("sans_date", None),
    ],
)
async def test_jours(hass: HomeAssistant, entree, jour, attendu) -> None:
    await choisir(hass, RECETTE, "Tartiflette")
    await choisir(hass, JOUR, jour)
    await hass.services.async_call("button", "press", {"entity_id": BOUTON}, blocking=True)
    [plat] = await elements(hass)
    assert plat.get("due") == attendu


async def test_bouton_sans_recette(hass: HomeAssistant, entree) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("button", "press", {"entity_id": BOUTON}, blocking=True)


async def test_homonymes_precises(hass: HomeAssistant, entree, recettes) -> None:
    recettes["999"] = Recipe(id="999", name="Tartiflette", category=None, servings=4, ingredients=())
    await entree.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    options = hass.states.get(RECETTE).attributes["options"]
    assert "Tartiflette" not in options
    assert {"Tartiflette (Plats principaux)", "Tartiflette (999)"} <= set(options)


async def test_indisponible_si_nextcloud_hors_ligne(hass: HomeAssistant, entree, mock_client) -> None:
    from custom_components.cookbook_menu.api import CookbookConnectionError

    mock_client.async_get_recipes.side_effect = CookbookConnectionError("coupure")
    await entree.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(BOUTON).state == "unavailable"
