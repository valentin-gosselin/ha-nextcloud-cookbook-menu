"""Liste « Menu de la semaine » et planificateur (story 2.1)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.cookbook_menu.api import CookbookConnectionError
from custom_components.cookbook_menu.planner import lire_couverts
from custom_components.cookbook_menu.store import DonneesPlanificateur, PlatMenu

MENU = "todo.valentin_cloud_exemple_fr_menu_de_la_semaine"


@pytest.fixture(autouse=True)
async def langue_francaise(hass: HomeAssistant) -> None:
    await hass.config.async_update(language="fr")


@pytest.fixture
async def entree(hass: HomeAssistant, mock_client, config_entry: MockConfigEntry) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def elements(hass: HomeAssistant, entite: str = MENU) -> list[dict[str, Any]]:
    reponse = await hass.services.async_call(
        TODO_DOMAIN, "get_items", {"entity_id": entite}, blocking=True, return_response=True
    )
    return reponse[entite]["items"]


async def ajouter(hass: HomeAssistant, texte: str, **extra: Any) -> None:
    await hass.services.async_call(
        TODO_DOMAIN, "add_item", {"entity_id": MENU, "item": texte, **extra}, blocking=True
    )


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("pour 4", 4),
        ("4 couverts", 4),
        ("4 personnes, sans recette", 4),
        ("6", 6),
        ("2 servings", 2),
        ("pour 0", None),
        ("beaucoup", None),
        ("", None),
        (None, None),
    ],
)
def test_lire_couverts(texte, attendu) -> None:
    assert lire_couverts(texte) == attendu


async def test_entite_creee(hass: HomeAssistant, entree) -> None:
    etat = hass.states.get(MENU)
    assert etat is not None
    assert etat.state == "0"


async def test_ajout_lie_a_une_recette(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "salade cesar")
    [plat] = await elements(hass)
    assert plat["summary"] == "Salade César au poulet"
    assert plat["description"] == "2 couverts"
    assert hass.states.get(MENU).state == "1"


async def test_ajout_plat_libre_avec_date_et_couverts(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "pizza surgelée", due_date="2026-09-18", description="pour 3")
    [plat] = await elements(hass)
    assert plat["summary"] == "pizza surgelée"
    assert plat["due"] == "2026-09-18"
    assert plat["description"] == "3 couverts, sans recette"


async def test_ordre_chronologique(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "tartiflette")
    await ajouter(hass, "carry", due_date="2026-09-20")
    await ajouter(hass, "chili", due_date="2026-09-18")
    await ajouter(hass, "taboulé", due_date="2026-09-18")
    assert [p["summary"] for p in await elements(hass)] == [
        "Chili con carne",
        "Taboulé",
        "Carry de poulet",
        "Tartiflette",
    ]


async def test_modification(hass: HomeAssistant, entree) -> None:
    await ajouter(hass, "carry", due_date="2026-09-20")
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": MENU, "item": "Carry de poulet", "rename": "tartiflette", "description": "pour 4"},
        blocking=True,
    )
    [plat] = await elements(hass)
    assert plat["summary"] == "Tartiflette"
    assert plat["description"] == "4 couverts"
    assert plat["due"] == "2026-09-20"

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": MENU, "item": "Tartiflette", "due_date": None, "status": "completed"},
        blocking=True,
    )
    [plat] = await elements(hass)
    assert "due" not in plat
    assert plat["status"] == "completed"
    assert hass.states.get(MENU).state == "0"

    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": MENU, "item": "Tartiflette", "rename": "fondue maison"},
        blocking=True,
    )
    [plat] = await elements(hass)
    assert plat["summary"] == "fondue maison"
    assert plat["description"] == "4 couverts, sans recette"


async def test_suppression_et_deplacement(
    hass: HomeAssistant, entree, hass_ws_client: WebSocketGenerator
) -> None:
    for texte in ("tartiflette", "carry", "chili"):
        await ajouter(hass, texte)
    uids = [p["uid"] for p in await elements(hass)]

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "todo/item/move", "entity_id": MENU, "uid": uids[2]})
    assert (await client.receive_json())["success"]
    await client.send_json_auto_id(
        {"type": "todo/item/move", "entity_id": MENU, "uid": uids[0], "previous_uid": uids[1]}
    )
    assert (await client.receive_json())["success"]
    assert [p["summary"] for p in await elements(hass)] == [
        "Chili con carne",
        "Carry de poulet",
        "Tartiflette",
    ]

    await hass.services.async_call(
        TODO_DOMAIN, "remove_item", {"entity_id": MENU, "item": ["Carry de poulet"]}, blocking=True
    )
    assert [p["summary"] for p in await elements(hass)] == ["Chili con carne", "Tartiflette"]


async def test_erreurs_du_planificateur(hass: HomeAssistant, entree) -> None:
    planificateur = entree.runtime_data.planner
    with pytest.raises(ServiceValidationError):
        planificateur.async_modifier_plat("inconnu", texte="x")
    with pytest.raises(ServiceValidationError):
        planificateur.async_supprimer_plats(["inconnu"])
    with pytest.raises(ServiceValidationError):
        planificateur.async_deplacer_plat(planificateur.async_ajouter_plat("carry").plat.uid, "inconnu")
    with pytest.raises(ServiceValidationError):
        planificateur.async_ajouter_plat("   ")
    with pytest.raises(ServiceValidationError):
        planificateur.async_ajouter_plat("", recipe_id="999999")
    resultat = planificateur.async_ajouter_plat("", recipe_id="6955", couverts=5)
    assert resultat.plat.summary == "Chili con carne"
    assert resultat.plat.servings == 5
    ambigu = planificateur.async_ajouter_plat("gratin")
    assert ambigu.ambigu
    assert ambigu.recette is None
    assert len(planificateur.chercher_recettes("salade", limite=3)) == 3


async def test_recette_disparue_puis_indisponible(hass: HomeAssistant, entree, mock_client, recettes) -> None:
    await ajouter(hass, "tartiflette")
    del recettes["2178937"]
    coordinateur = entree.runtime_data.coordinator
    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    [plat] = await elements(hass)
    assert plat["description"] == "2 couverts, recette introuvable"

    mock_client.async_get_recipes.side_effect = CookbookConnectionError("coupure")
    await coordinateur.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(MENU).state == "unavailable"


async def test_recette_dans_categorie_exclue_reste_connue(hass: HomeAssistant, entree) -> None:
    planificateur = entree.runtime_data.planner
    plat = PlatMenu(uid="x", summary="Lessive", servings=1, recipe_id="6958")
    assert planificateur.recette_du_plat(plat).name == "Lessive"


async def test_persistance(hass: HomeAssistant, mock_client, config_entry, hass_storage, freezer) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await ajouter(hass, "carry", due_date="2026-09-20", description="pour 6")
    freezer.tick(5)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    cle = f"cookbook_menu.{config_entry.entry_id}"
    assert hass_storage[cle]["data"]["menu"][0]["servings"] == 6

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    [plat] = await elements(hass)
    assert plat["summary"] == "Carry de poulet"
    assert plat["due"] == "2026-09-20"

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert cle not in hass_storage


def test_donnees_aller_retour() -> None:
    donnees = DonneesPlanificateur(
        menu=[
            PlatMenu(uid="a", summary="Carry", servings=4, recipe_id="1", day=date(2026, 9, 20), done=True)
        ],
        courses_manuelles=[{"uid": "m", "summary": "Pain"}],
        etat_courses={"citron": {"done": True}},
        placard_epuise=["huile olive"],
        historique=[{"day": "2026-09-01", "summary": "Chili"}],
    )
    assert DonneesPlanificateur.depuis_dict(donnees.en_dict()) == donnees
    assert DonneesPlanificateur.depuis_dict(None) == DonneesPlanificateur()
    assert PlatMenu.depuis_dict({"uid": 1, "servings": 0}).servings == 1
