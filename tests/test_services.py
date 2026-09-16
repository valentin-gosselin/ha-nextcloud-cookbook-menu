"""Actions de service (story 2.4)."""

from __future__ import annotations

from datetime import date

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cookbook_menu.const import DOMAIN
from custom_components.cookbook_menu.jours import lire_jour

from .test_courses import courses
from .test_menu import elements

JEUDI = date(2026, 9, 17)


@pytest.fixture(autouse=True)
async def langue_et_date(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-09-16 12:00:00+02:00")  # un mercredi
    await hass.config.async_update(language="fr", time_zone="Europe/Paris")


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def appeler(hass: HomeAssistant, action: str, reponse: bool = False, **donnees):
    return await hass.services.async_call(DOMAIN, action, donnees, blocking=True, return_response=reponse)


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        ("jeudi", JEUDI),
        ("Jeudi prochain", JEUDI),
        ("mercredi", date(2026, 9, 16)),
        ("mercredi prochain", date(2026, 9, 23)),
        ("le lundi", date(2026, 9, 21)),
        ("demain", JEUDI),
        ("aujourd'hui", date(2026, 9, 16)),
        ("ce soir", date(2026, 9, 16)),
        ("après-demain", date(2026, 9, 18)),
        ("Friday", date(2026, 9, 18)),
        ("2026-10-01", date(2026, 10, 1)),
        (date(2026, 1, 1), date(2026, 1, 1)),
        (None, None),
        ("  ", None),
    ],
)
def test_lire_jour(valeur, attendu) -> None:
    assert lire_jour(valeur, date(2026, 9, 16)) == attendu


def test_lire_jour_invalide() -> None:
    with pytest.raises(ValueError):
        lire_jour("un de ces quatre", date(2026, 9, 16))


async def test_ajouter_au_menu(hass: HomeAssistant, entree) -> None:
    reponse = await appeler(hass, "add_to_menu", True, recipe="salade cesar", day="jeudi", servings=4)
    assert reponse["dish"] == "Salade César au poulet"
    assert reponse["linked"] is True
    assert reponse["day"] == "2026-09-17"
    assert reponse["servings"] == 4
    assert "Salade César végétarienne (façon Rachel)" in reponse["alternatives"]
    assert "Citron (1)" in reponse["shopping_items_changed"]
    [plat] = await elements(hass)
    assert plat["due"] == "2026-09-17"


async def test_ajouter_ambigu_prend_la_meilleure(hass: HomeAssistant, entree) -> None:
    reponse = await appeler(hass, "add_to_menu", True, recipe="gratin")
    assert reponse["linked"] is True
    assert reponse["dish"].startswith("Gratin")
    assert len(reponse["alternatives"]) >= 2


async def test_ajouter_plat_libre(hass: HomeAssistant, entree) -> None:
    reponse = await appeler(hass, "add_to_menu", True, recipe="restes du frigo")
    assert reponse["linked"] is False
    assert reponse["recipe_id"] is None
    assert reponse["shopping_items_changed"] == []


async def test_jour_invalide(hass: HomeAssistant, entree) -> None:
    with pytest.raises(ServiceValidationError, match="un de ces quatre"):
        await appeler(hass, "add_to_menu", recipe="carry", day="un de ces quatre")


async def test_retirer_et_couverts(hass: HomeAssistant, entree) -> None:
    await appeler(hass, "add_to_menu", recipe="carry", day="jeudi")
    await appeler(hass, "add_to_menu", recipe="tartiflette")
    await appeler(hass, "set_servings", recipe="carry de poulet", servings=6)
    assert "Tomates (200 g)" in await courses(hass)
    [carry, tartiflette] = await elements(hass)
    assert carry["description"] == "6 couverts"

    await appeler(hass, "set_servings", uid=tartiflette["uid"], servings=3)
    await appeler(hass, "remove_from_menu", recipe="carry")
    assert [p["description"] for p in await elements(hass)] == ["3 couverts"]
    await appeler(hass, "remove_from_menu", uid=tartiflette["uid"])
    assert await elements(hass) == []

    with pytest.raises(ServiceValidationError):
        await appeler(hass, "remove_from_menu", recipe="couscous")


async def test_nouvelle_semaine(hass: HomeAssistant, entree) -> None:
    planificateur = entree.runtime_data.planner
    from datetime import date as _date

    planificateur.async_ajouter_plat("carry", jour=_date(2026, 9, 14))  # passé
    planificateur.async_ajouter_plat("tartiflette", jour=_date(2026, 9, 18))  # à venir
    planificateur.async_ajouter_plat("restes", fait=True)  # cuisiné, sans date
    planificateur.async_ajouter_plat("chili")  # sans date, pas cuisiné
    planificateur.async_ajouter_course("Pain", fait=True)
    planificateur.async_ajouter_course("Lessive")
    planificateur.stockage.donnees.historique.append(
        {"day": "2024-01-01", "summary": "Vieux plat", "recipe_id": None, "servings": 2}
    )
    reponse = await appeler(hass, "new_week", True)
    assert reponse["archived"] == [
        {"day": "2026-09-14", "recipe_id": "2176038", "summary": "Carry de poulet", "servings": 2},
        {"day": "2026-09-16", "recipe_id": None, "summary": "restes", "servings": 2},
    ]
    assert [p["summary"] for p in await elements(hass)] == ["Tartiflette", "Chili con carne"]
    assert "Lessive" in await courses(hass)
    assert "Pain" not in await courses(hass)
    assert [p["summary"] for p in planificateur.stockage.donnees.historique] == ["Carry de poulet", "restes"]

    historique = await appeler(hass, "get_history", True, recipe="carry")
    assert historique == {"history": [reponse["archived"][0]]}


async def test_chercher(hass: HomeAssistant, entree) -> None:
    reponse = await appeler(hass, "search_recipes", True, query="salade", limit=2)
    assert len(reponse["recipes"]) == 2
    assert all("Salade" in r["name"] for r in reponse["recipes"])
    assert {"id", "name", "category", "servings", "score"} <= set(reponse["recipes"][0])


async def test_plusieurs_entrees_exigent_un_identifiant(hass: HomeAssistant, entree, mock_client) -> None:
    autre = MockConfigEntry(
        domain=DOMAIN, unique_id="autre", data=dict(entree.data), options=dict(entree.options)
    )
    autre.add_to_hass(hass)
    assert await hass.config_entries.async_setup(autre.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError):
        await appeler(hass, "add_to_menu", recipe="carry")
    await appeler(hass, "add_to_menu", config_entry_id=autre.entry_id, recipe="carry")
    assert autre.runtime_data.planner.menu[0].summary == "Carry de poulet"
    assert entree.runtime_data.planner.menu == []
